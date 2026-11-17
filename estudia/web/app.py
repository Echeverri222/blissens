"""Aplicación web: páginas del paciente, simulador de WhatsApp y API."""
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import psycopg
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import agenda, clock, config, db, fmt, links, messaging, tasks
from ..lifecycle import ALIVE

HERE = Path(__file__).parent
app = FastAPI(title="Estud-IA", description="Gestión inteligente de citas · Blissens Odontología")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["fecha"] = fmt.fecha
templates.env.filters["hora"] = fmt.hora
templates.env.filters["fecha_hora"] = fmt.fecha_hora
templates.env.filters["local"] = lambda d: d.astimezone(clock.TZ) if d else d


def linkify(text: str):
    from markupsafe import Markup, escape
    safe = str(escape(text))
    return Markup(re.sub(r"(https?://[^\s<]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', safe))


templates.env.filters["linkify"] = linkify


def get_conn():
    conn = db.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def patient_from_token(conn, token: str) -> dict:
    pid = links.read_token(token, config.get(conn, "vigencia_enlace_dias"))
    p = conn.execute("select * from paciente where id=%s", (pid,)).fetchone() if pid else None
    if p is None:
        raise HTTPException(404, "Este enlace no es válido o ya venció. Pide uno nuevo a la clínica.")
    return p


def render(request, name, **ctx):
    return templates.TemplateResponse(request, name, ctx)


# ----------------------------------------------------------------- Entrada pública

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/agendar")


@app.get("/agendar", response_class=HTMLResponse)
def agendar(request: Request, caso: int | None = None):
    return render(request, "identificar.html", error=None, nuevo=None, values={})


@app.post("/agendar/identificar", response_class=HTMLResponse)
def identificar(request: Request, documento: str = Form(...), celular: str = Form(...),
                nombres: str = Form(""), apellidos: str = Form(""), consentimiento: str = Form(""),
                conn=Depends(get_conn)):
    from ..data import normalize_phone
    documento = re.sub(r"\D", "", documento)
    phone = normalize_phone(celular)
    values = {"documento": documento, "celular": celular}
    if not documento or not phone:
        return render(request, "identificar.html", error="Revisa tu documento y tu celular (10 dígitos, empieza por 3).",
                      nuevo=None, values=values)
    p = conn.execute("select * from paciente where documento=%s", (documento,)).fetchone()
    if p and p["celular"] == phone:
        return RedirectResponse(f"/p/{links.make_token(p['id'])}", status_code=303)
    if p:  # No se revela nada: la clínica lo contactará y el caso aparece en el panel.
        conn.execute("insert into solicitud_contacto(documento, celular, nota, momento) values (%s,%s,%s,%s)",
                     (documento, phone, "Documento ya registrado con otro celular", clock.now(conn)))
        return render(request, "contacto.html")
    if not nombres.strip():
        return render(request, "identificar.html", error=None, nuevo=True, values=values)
    if not consentimiento:
        return render(request, "identificar.html",
                      error="Para registrarte necesitamos tu autorización para tratar tus datos.", nuevo=True,
                      values={**values, "nombres": nombres, "apellidos": apellidos})
    now = clock.now(conn)
    pid = conn.execute(
        "insert into paciente(nombres, apellidos, documento, celular, consentimiento_en, creado_en) "
        "values (%s,%s,%s,%s,%s,%s) returning id",
        (nombres.strip(), apellidos.strip(), documento, phone, now, now)).fetchone()["id"]
    return RedirectResponse(f"/p/{links.make_token(pid)}/nueva", status_code=303)


# ----------------------------------------------------------------- Mis citas

def _appointments(conn, patient_id: int):
    now = clock.now(conn)
    return conn.execute(
        "select c.*, p.nombre as profesional, s.nombre as servicio from cita c "
        "join profesional p on p.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "where c.paciente_id=%s and c.estado = any(%s) and (c.rango is null or upper(c.rango) > %s) order by c.dia, c.rango",
        (patient_id, list(ALIVE), now)).fetchall()


@app.get("/p/{token}", response_class=HTMLResponse)
def mis_citas(request: Request, token: str, aviso: str = "", conn=Depends(get_conn)):
    p = patient_from_token(conn, token)
    return render(request, "mis_citas.html", p=p, token=token, citas=_appointments(conn, p["id"]), aviso=aviso)


def _picker_context(conn, service_id, professional_id):
    services = conn.execute("select * from servicio where autoagendable order by id").fetchall()
    pros = conn.execute("select * from profesional where activo order by id").fetchall()
    sid = service_id or services[0]["id"]
    pid = professional_id or pros[0]["id"]
    slots = agenda.available_slots(conn, pid, sid)
    return {"services": services, "pros": pros, "sid": sid, "pid": pid, "slots": slots}


@app.get("/p/{token}/nueva", response_class=HTMLResponse)
@app.get("/p/{token}/agendar", response_class=HTMLResponse)
def nueva(request: Request, token: str, servicio: int | None = None, profesional: int | None = None,
          caso: int | None = None, conn=Depends(get_conn)):
    p = patient_from_token(conn, token)
    ctx = _picker_context(conn, servicio, profesional)
    return render(request, "elegir.html", p=p, token=token, modo="nueva", cita=None, error=None,
                  action=f"/p/{token}/agendar", **ctx)


@app.get("/p/{token}/espacios", response_class=HTMLResponse)
def espacios(request: Request, token: str, servicio: int, profesional: int, cita: int | None = None,
             modo: str = "nueva", error: str | None = None, conn=Depends(get_conn)):
    patient_from_token(conn, token)
    slots = agenda.available_slots(conn, profesional, servicio)
    return render(request, "_espacios.html", slots=slots, sid=servicio, pid=profesional, token=token, cita=cita,
                  modo=modo, error=error)


@app.post("/p/{token}/agendar", response_class=HTMLResponse)
def agendar_post(request: Request, token: str, servicio: int = Form(...), profesional: int = Form(...),
                 inicio: str = Form(...), conn=Depends(get_conn)):
    p = patient_from_token(conn, token)
    try:
        agenda.book(conn, p["id"], profesional, servicio, datetime.fromisoformat(inicio), "paciente", "paciente")
    except agenda.SlotTaken:
        slots = agenda.available_slots(conn, profesional, servicio)
        return render(request, "_espacios.html", slots=slots, sid=servicio, pid=profesional, token=token, cita=None,
                      modo="nueva", error="Ese espacio acaba de ocuparse. Esta es la lista actualizada.")
    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = f"/p/{token}?aviso=" + quote("Tu cita quedó agendada. Te enviamos la confirmación por WhatsApp.")
    return resp


@app.get("/p/{token}/cambiar/{cita_id}", response_class=HTMLResponse)
def cambiar(request: Request, token: str, cita_id: int, servicio: int | None = None, profesional: int | None = None,
            conn=Depends(get_conn)):
    p = patient_from_token(conn, token)
    c = conn.execute("select * from cita where id=%s and paciente_id=%s and estado = any(%s)",
                     (cita_id, p["id"], list(ALIVE))).fetchone()
    if c is None:
        raise HTTPException(404, "Esa cita ya no está vigente")
    ctx = _picker_context(conn, c["servicio_id"], c["profesional_id"])
    ctx["services"] = [s for s in ctx["services"] if s["id"] == c["servicio_id"]] or ctx["services"]
    if c["servicio_id"] not in [s["id"] for s in ctx["services"]]:
        ctx["services"] = conn.execute("select * from servicio where id=%s", (c["servicio_id"],)).fetchall()
    ctx["slots"] = agenda.available_slots(conn, c["profesional_id"], c["servicio_id"])
    ctx["sid"], ctx["pid"] = c["servicio_id"], c["profesional_id"]
    return render(request, "elegir.html", p=p, token=token, modo="cambiar", cita=cita_id, error=None,
                  action=f"/p/{token}/cambiar/{cita_id}", **ctx)


@app.post("/p/{token}/cambiar/{cita_id}", response_class=HTMLResponse)
def cambiar_post(request: Request, token: str, cita_id: int, inicio: str = Form(...), conn=Depends(get_conn)):
    p = patient_from_token(conn, token)
    c = conn.execute("select * from cita where id=%s and paciente_id=%s", (cita_id, p["id"])).fetchone()
    if c is None:
        raise HTTPException(404)
    try:
        agenda.reschedule(conn, cita_id, datetime.fromisoformat(inicio), "paciente")
    except agenda.SlotTaken:
        slots = agenda.available_slots(conn, c["profesional_id"], c["servicio_id"])
        return render(request, "_espacios.html", slots=slots, sid=c["servicio_id"], pid=c["profesional_id"], token=token,
                      cita=cita_id, modo="cambiar", error="Ese espacio acaba de ocuparse. Esta es la lista actualizada.")
    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = f"/p/{token}?aviso=" + quote("Cambiamos la fecha de tu cita.")
    return resp


@app.get("/p/{token}/cancelar/{cita_id}", response_class=HTMLResponse)
def cancelar(request: Request, token: str, cita_id: int, conn=Depends(get_conn)):
    p = patient_from_token(conn, token)
    c = conn.execute("select * from cita where id=%s and paciente_id=%s and estado = any(%s)",
                     (cita_id, p["id"], list(ALIVE))).fetchone()
    if c is None:
        raise HTTPException(404, "Esa cita ya no está vigente")
    motivos = conn.execute("select * from motivo_cancelacion order by orden").fetchall()
    return render(request, "cancelar.html", p=p, token=token, cita_id=cita_id, motivos=motivos)


@app.post("/p/{token}/cancelar/{cita_id}", response_class=HTMLResponse)
def cancelar_post(request: Request, token: str, cita_id: int, motivo: int = Form(...), conn=Depends(get_conn)):
    p = patient_from_token(conn, token)
    c = conn.execute("select * from cita where id=%s and paciente_id=%s", (cita_id, p["id"])).fetchone()
    if c is None:
        raise HTTPException(404)
    agenda.cancel(conn, cita_id, "paciente", "enlace", reason_id=motivo)
    # Tras cancelar se ofrecen espacios de inmediato.
    ctx = _picker_context(conn, c["servicio_id"], c["profesional_id"])
    if c["servicio_id"] not in [s["id"] for s in ctx["services"]]:
        ctx["services"] = conn.execute("select * from servicio where id=%s", (c["servicio_id"],)).fetchall()
    ctx["sid"], ctx["pid"] = c["servicio_id"], c["profesional_id"]
    ctx["slots"] = agenda.available_slots(conn, c["profesional_id"], c["servicio_id"])
    return render(request, "elegir.html", p=p, token=token, modo="nueva", cita=None, error=None,
                  action=f"/p/{token}/agendar", cancelada=True, **ctx)


# ----------------------------------------------------------------- Simulador de WhatsApp

def _clock_info(conn):
    return {"ahora": clock.now(conn), "demo": config.get(conn, "demo_mode")}


@app.get("/simulador", response_class=HTMLResponse)
def simulador(request: Request, paciente: int | None = None, q: str = "", conn=Depends(get_conn)):
    like = f"%{q.strip()}%"
    pacientes = conn.execute(
        "select p.id, p.nombres, p.apellidos, (select max(momento) from mensaje m where m.paciente_id=p.id) as ultimo, "
        "(select count(*) from mensaje m where m.paciente_id=p.id and m.estado_entrega='entregado') as n "
        "from paciente p where %s = '' or p.nombres ilike %s or p.apellidos ilike %s or p.documento like %s "
        "order by ultimo desc nulls last, p.id limit 40", (q.strip(), like, like, like)).fetchall()
    sel = paciente or (pacientes[0]["id"] if pacientes else None)
    return render(request, "simulador.html", pacientes=pacientes, sel=sel, q=q, **_clock_info(conn),
                  chat=_chat_ctx(conn, sel))


def _chat_ctx(conn, patient_id):
    if not patient_id:
        return None
    p = conn.execute("select * from paciente where id=%s", (patient_id,)).fetchone()
    msgs = conn.execute("select * from mensaje where paciente_id=%s and estado_entrega='entregado' order by momento, id",
                        (patient_id,)).fetchall()
    citas = conn.execute(
        "select c.id, c.estado, c.rango, pr.nombre as profesional from cita c join profesional pr on pr.id=c.profesional_id "
        "where c.paciente_id=%s and c.estado = any(%s) and c.rango is not null order by lower(c.rango)",
        (patient_id, list(ALIVE))).fetchall()
    return {"p": p, "msgs": msgs, "citas": citas}


@app.get("/simulador/burbujas/{patient_id}", response_class=HTMLResponse)
def burbujas(request: Request, patient_id: int, conn=Depends(get_conn)):
    return render(request, "_burbujas.html", chat=_chat_ctx(conn, patient_id))


@app.post("/simulador/boton", response_class=HTMLResponse)
def boton(request: Request, paciente: int = Form(...), boton: str = Form(...), conn=Depends(get_conn)):
    messaging.receive(conn, paciente, button_id=boton)
    conn.commit()
    tasks.cycle()
    return RedirectResponse(f"/simulador?paciente={paciente}", status_code=303)


@app.post("/simulador/texto", response_class=HTMLResponse)
def texto(request: Request, paciente: int = Form(...), texto: str = Form(...), conn=Depends(get_conn)):
    messaging.receive(conn, paciente, text=texto)
    return RedirectResponse(f"/simulador?paciente={paciente}", status_code=303)


@app.post("/simulador/reloj", response_class=HTMLResponse)
def reloj(request: Request, accion: str = Form(...), paciente: int | None = Form(None), cita: int | None = Form(None),
          conn=Depends(get_conn)):
    if accion == "1h":
        clock.shift(conn, timedelta(hours=1))
    elif accion == "1d":
        clock.shift(conn, timedelta(days=1))
    elif accion == "3d":
        clock.shift(conn, timedelta(days=3))
    elif accion in ("48h", "24h") and cita:
        c = conn.execute("select rango from cita where id=%s", (cita,)).fetchone()
        target = c["rango"].lower - timedelta(hours=int(accion[:2]), minutes=-1)
        if target > clock.now(conn):
            clock.jump_to(conn, target)
    elif accion == "real":
        clock.reset(conn)
    conn.commit()
    tasks.cycle()
    return RedirectResponse(f"/simulador?paciente={paciente}" if paciente else "/simulador", status_code=303)


# ----------------------------------------------------------------- Operación

@app.post("/tick")
def tick():
    """Ejecuta el mismo ciclo que el trabajador; para que más adelante lo invoque un programador externo."""
    return tasks.cycle()


@app.get("/salud")
def salud(conn=Depends(get_conn)):
    conn.execute("select 1")
    return {"ok": True}
