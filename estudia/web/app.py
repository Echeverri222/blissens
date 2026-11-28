"""Aplicación web: páginas del paciente, simulador de WhatsApp y API."""
import os
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import (
    agenda,
    arranque,
    canales,
    catalog,
    clock,
    config,
    db,
    familia,
    fmt,
    lifecycle,
    links,
    logs,
    messaging,
    privacidad,
    settings,
    solicitudes,
    tasks,
    usuarios,
)
from .. import correo as correo_mod
from ..api import registrar_errores
from ..api import router as api_router
from ..lifecycle import ALIVE
from . import copia, seo
from .limite import LimiteVentana
from .panel import router as panel_router

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["fecha"] = fmt.fecha
templates.env.filters["hora"] = fmt.hora
templates.env.filters["fecha_hora"] = fmt.fecha_hora
templates.env.filters["dia_corto"] = lambda d: fmt.DIAS[d.weekday()][:3].capitalize()
templates.env.filters["nombre"] = familia.primer_nombre  # primer nombre, sin fallar si viene vacío
templates.env.filters["local"] = lambda d: d.astimezone(clock.TZ) if d else d


def estatico(ruta: str) -> str:
    """`/static/...` con una huella del archivo: tras un cambio, el navegador no reutiliza la copia vieja de su caché."""
    try:
        huella = format(int((HERE / "static" / ruta).stat().st_mtime), "x")
    except OSError:
        return f"/static/{ruta}"
    return f"/static/{ruta}?v={huella}"


templates.env.globals["estatico"] = estatico


publico = APIRouter()
sim = APIRouter()
operacion = APIRouter()
operacion_salud = APIRouter()
canal_entrante = APIRouter()


def linkify(text: str):
    from markupsafe import Markup, escape
    safe = str(escape(text))
    return Markup(re.sub(r"(https?://[^\s<]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', safe))


templates.env.filters["linkify"] = linkify


get_conn = db.request_conn  # sin negocio: solo para /salud


def _con_conexion(conn):
    """Confirma al terminar bien, deshace si algo falla y siempre cierra (como `db.request_conn`)."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _fijar_negocio(request: Request, conn, negocio: dict | None, prefijo: str = "") -> None:
    if negocio is None or not negocio["activo"]:
        raise HTTPException(404, "Este enlace no es válido o ya venció. Pida uno nuevo a la clínica.")
    db.fijar(conn, negocio["id"])
    request.state.negocio_id = negocio["id"]
    request.state.negocio = negocio
    request.state.prefijo = prefijo
    request.state.termino = config.get(conn, "termino_negocio")
    request.state.asistente_nombre = config.get(conn, "asistente_nombre")
    request.state.consentimiento = config.get(conn, "texto_consentimiento").format(nombre=negocio["nombre"])


def conn_publica(request: Request, nombre: str | None = None):
    """Páginas públicas sin enlace: el negocio por defecto, o el del prefijo `/n/<nombre-corto>`."""
    conn = db.connect(negocio=None)
    try:
        corto = nombre or settings.NEGOCIO_POR_DEFECTO
        _fijar_negocio(request, conn, conn.execute("select * from negocio_de_nombre(%s)", (corto,)).fetchone(),
                       f"/n/{corto}" if nombre else "")
    except Exception:
        conn.close()
        raise
    yield from _con_conexion(conn)


def conn_enlace(request: Request, token: str):
    """`/p/<token>`: el negocio va firmado dentro del enlace; si no sirve, el mismo 404 de enlace vencido."""
    conn = db.connect(negocio=None)
    try:
        nid = links.negocio_del_token(token)
        if nid is None:
            raise HTTPException(404, "Este enlace no es válido o ya venció. Pida uno nuevo a la clínica.")
        db.fijar(conn, nid)
        _fijar_negocio(request, conn, conn.execute("select * from negocio where id=%s", (nid,)).fetchone())
    except Exception:
        conn.close()
        raise
    yield from _con_conexion(conn)


def conn_baja(request: Request, token: str):
    """`/correo/baja/<token>`: el negocio va firmado en el enlace de baja del correo."""
    conn = db.connect(negocio=None)
    try:
        v = correo_mod.leer_token_baja(token)
        if v is None:
            raise HTTPException(404, "Este enlace no es válido. Pida ayuda a la clínica.")
        db.fijar(conn, v[0])
        _fijar_negocio(request, conn, conn.execute("select * from negocio where id=%s", (v[0],)).fetchone())
        request.state.paciente_baja = v[1]
    except Exception:
        conn.close()
        raise
    yield from _con_conexion(conn)


def conn_simulador(request: Request):
    """Simulador: en `local`, como `/agendar`; en `demo`, con sesión de auxiliar (en producción la ruta no existe)."""
    if request.app.state.entorno == "local":
        yield from conn_publica(request)
        return
    conn = db.connect(negocio=None)
    try:
        u = usuarios.usuario_de_sesion(conn, request.cookies.get("estudia_sesion"))
        if u is None or u["negocio_id"] is None:
            raise HTTPException(401, "Inicia sesión como auxiliar en el panel para usar el simulador.")
        if u["rol"] != "auxiliar":
            raise HTTPException(403, "El simulador es solo para recepción.")
        if u.get("debe_cambiar_clave"):
            raise HTTPException(403, "Cambia tu clave antes de usar el simulador.")
        request.state.negocio = conn.execute("select * from negocio where id=%s", (u["negocio_id"],)).fetchone()
        request.state.prefijo = ""
    except Exception:
        conn.close()
        raise
    yield from _con_conexion(conn)


def mismo_origen(request: Request) -> None:
    """Los POST del simulador solo valen desde esta misma página (defensa contra CSRF además de SameSite)."""
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(403, "Origen no permitido")
    origen = request.headers.get("origin")
    if origen and origen != "null" and urlparse(origen).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "Origen no permitido")
    if origen == "null":
        raise HTTPException(403, "Origen no permitido")


def patient_from_token(conn, token: str) -> dict:
    pid = links.read_token(token, config.get(conn, "vigencia_enlace_dias"))
    p = conn.execute("select * from paciente where id=%s", (pid,)).fetchone() if pid else None
    if p is not None and p["documento"] is None and p["nombres"] == privacidad.ANONIMO:
        p = None  # anonimizado: sus enlaces dejan de servir (hay pacientes importados sin documento que sí son reales)
    if p is not None:
        huella = links.huella_del_token(token, config.get(conn, "vigencia_enlace_dias"))
        if huella is not None and huella not in links.huellas_validas(p["celular"], p["correo"]):
            p = None
    if p is None:
        raise HTTPException(404, "Este enlace no es válido o ya venció. Pida uno nuevo a la clínica.")
    return p


AVISO_PROSPECTO = ("Todavía no tiene documento registrado, así que las citas presenciales las agenda la clínica cuando "
                   "usted llegue. Aquí puede ver su solicitud y agregarle fotos o radiografías.")


def _sin_citas(request: Request, token: str, p: dict):
    """Un prospecto (sin documento) no agenda, cambia ni cancela citas presenciales: vuelve a su página con un aviso."""
    if p["etapa"] != "prospecto":
        return None
    url = f"/p/{token}?aviso=" + quote(AVISO_PROSPECTO)
    if request.headers.get("HX-Request"):
        return HTMLResponse("", headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def render(request, name, status_code: int = 200, **ctx):
    st = request.state
    ctx.setdefault("negocio", getattr(st, "negocio", None))
    ctx.setdefault("prefijo", getattr(st, "prefijo", ""))
    ctx.setdefault("termino", getattr(st, "termino", "la clínica"))
    ctx.setdefault("asistente_nombre", getattr(st, "asistente_nombre", "Bliss"))
    ctx.setdefault("consentimiento", getattr(st, "consentimiento", ""))
    ctx.setdefault("lang", "es")
    ctx.setdefault("t", copia.COPIA[ctx["lang"]])
    ctx.setdefault("sitio", copia)
    ctx.setdefault("base_url", settings.BASE_URL.rstrip("/"))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


# ----------------------------------------------------------------- Entrada pública

# 5 solicitudes del sitio por IP cada 10 minutos (en memoria: se reinicia con el proceso y no se comparte entre procesos).
limite_solicitudes = LimiteVentana(maximo=5, segundos=600)
# Identificación y alta de familiares (enumeración de documentos): por IP y por documento, 10 minutos. El cupo del
# documento solo se gasta con intentos que no coinciden: así nadie puede bloquearle la entrada al paciente real.
limite_identificacion = LimiteVentana(maximo=15, segundos=600)
limite_documento = LimiteVentana(maximo=10, segundos=600)


def reiniciar_limites_identificacion() -> None:
    limite_identificacion.reiniciar()
    limite_documento.reiniciar()


def _identificacion_permitida(request: Request, documento: str | None = None) -> bool:
    """Cuenta el intento y dice si todavía cabe en la cuota de la IP (y del documento, si se pasa)."""
    ip = _ip_cliente(request)
    ok = limite_identificacion.disponible(ip) and (documento is None or limite_documento.disponible(documento or "-"))
    if ok:
        limite_identificacion.registrar(ip)
        if documento is not None:
            limite_documento.registrar(documento or "-")
    return ok


def _fallo_de_documento_permitido(documento: str) -> bool:
    """Un intento con un documento que existe pero otro celular: gasta el cupo de ese documento."""
    if not limite_documento.disponible(documento):
        return False
    limite_documento.registrar(documento)
    return True


def _landing(request, lang: str):
    """Texto estático: no abre conexión a la base de datos, así que la landing sirve aunque falte el negocio."""
    return render(
        request, "sitio.html", lang=lang, values={}, error=None, hecho=False,
        json_ld=seo.json_ld(settings.BASE_URL.rstrip("/"), lang),
    )


@publico.get("/", response_class=HTMLResponse, include_in_schema=False)
def inicio(request: Request):
    """La landing pública (español). El panel del personal vive en `/panel`."""
    return _landing(request, "es")


@publico.get("/en", response_class=HTMLResponse, include_in_schema=False)
def inicio_en(request: Request):
    return _landing(request, "en")


@publico.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots_txt():
    return PlainTextResponse(seo.robots_txt(settings.BASE_URL))


@publico.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    return Response(seo.sitemap_xml(settings.BASE_URL), media_type="application/xml; charset=utf-8")


@publico.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=False)
def llms_txt():
    return PlainTextResponse(seo.llms_txt(settings.BASE_URL))


def _ip_cliente(request: Request) -> str:
    """La IP del socket. No se lee X-Forwarded-For: el repositorio no declara proxies de confianza, y cualquiera
    podría falsificar la cabecera para saltarse el límite."""
    return request.client.host if request.client else "?"


def _uid(panel: str) -> str:
    """El sufijo de ids de un formulario del asistente (`-asistente`, `-chat1`...), o vacío. Solo letras, dígitos y guion."""
    return f"-{panel}" if re.fullmatch(r"[a-z0-9]{1,20}", panel or "") else ""


def _celular_de_sitio(raw: str) -> str:
    """Un celular colombiano se normaliza; uno del exterior se conserva (solo dígitos, + y separadores). Vacío si no
    parece un teléfono (7 a 15 dígitos, como E.164)."""
    from ..pacientes import normalizar_celular
    raw = raw.strip()
    limpio = normalizar_celular(raw) or re.sub(r"[^\d+()\- ]", "", raw)[:30].strip()
    return limpio if 7 <= len(re.sub(r"\D", "", limpio)) <= 15 else ""


@publico.post("/sitio/solicitud", response_class=HTMLResponse, include_in_schema=False)
def solicitud_sitio(request: Request, interes: str = Form(...), idioma: str = Form("es"), nombre: str = Form(""),
                    correo: str = Form(""), celular: str = Form(""), pais: str = Form(""), paquete: str = Form(""),
                    mensaje: str = Form(""), consentimiento: str = Form(""), web: str = Form(""), panel: str = Form(""),
                    fotos: list[UploadFile | str] = File(default=[]), conn=Depends(conn_publica)):
    """Formularios de la landing (evaluación virtual, experiencias, contacto): crean una solicitud que la auxiliar ve en
    Bandejas, con fotos o PDF opcionales, y programan el aviso por correo a la clínica y el acuse a quien la envió."""
    if interes not in copia.INTERESES:
        raise HTTPException(422, "Interés desconocido")
    lang = idioma if idioma in copia.COPIA else "es"
    t = copia.COPIA[lang]
    f = t["form"]
    uid = _uid(panel)  # dentro del asistente el formulario lleva otros ids que el de la sección de la landing
    nombre, correo, celular, pais, mensaje = (x.strip() for x in (nombre, correo, celular, pais, mensaje))
    values = {"nombre": nombre, "correo": correo, "celular": celular, "pais": pais, "paquete": paquete,
              "mensaje": mensaje, "consentimiento": consentimiento}
    error = None
    if not limite_solicitudes.disponible(_ip_cliente(request)):
        return render(request, "_solicitud.html" if request.headers.get("HX-Request") else "solicitud.html",
                      lang=lang, interes=interes, values=values, error=f["err_limite"], hecho=False,
                      uid=uid, status_code=429)
    if web:  # campo trampa para robots: se responde como si hubiera salido bien, sin guardar nada
        return render(request, "_solicitud.html", lang=lang, interes=interes, values={}, error=None, hecho=True,
                      horas=config.get(conn, "plazo_respuesta_solicitud_horas"), con_correo=False, uid=uid)
    tel = _celular_de_sitio(celular)
    if not nombre:
        error = f["err_nombre"]
    elif not (tel or (correo and correo_mod.es_direccion(correo))) or (correo and not correo_mod.es_direccion(correo)):
        error = f["err_contacto"]
    elif interes == "experiencia" and paquete not in copia.PAQUETES:
        error = f["err_paquete"]
    elif not consentimiento:
        error = f["err_consent"]
    archivos: list[tuple[str, str, bytes]] = []
    if error is None:
        # Se lee un byte de más para saber si se pasa del máximo sin cargar en memoria un archivo enorme.
        # Un campo de archivo vacío llega como texto vacío (o como archivo sin nombre): no cuenta.
        con_nombre = [u for u in fotos if not isinstance(u, str) and u.filename]
        try:
            if len(con_nombre) > solicitudes.MAX_ADJUNTOS:
                raise solicitudes.AdjuntoInvalido("cantidad")
            subidos = [solicitudes.Adjunto(u.filename or "", u.file.read(solicitudes.MAX_BYTES + 1)) for u in con_nombre]
            archivos = solicitudes.validar_adjuntos([a for a in subidos if a.datos])
        except solicitudes.AdjuntoInvalido as e:
            error = f[f"err_adjunto_{e}"]
    hecho = error is None
    if hecho:
        limite_solicitudes.registrar(_ip_cliente(request))
        solicitudes.crear(conn, interes=interes, idioma=lang, nombre=nombre[:120], correo=correo[:120].lower() or None,
                          celular=tel, pais=pais[:80] or None, paquete=paquete if interes == "experiencia" else None,
                          mensaje=mensaje[:2000] or None, adjuntos=archivos)
    ctx = dict(lang=lang, interes=interes, values=values if not hecho else {}, error=error, hecho=hecho, uid=uid,
               horas=config.get(conn, "plazo_respuesta_solicitud_horas"), con_correo=bool(correo))
    if request.headers.get("HX-Request"):
        return render(request, "_solicitud.html", **ctx)
    return render(request, "solicitud.html", **ctx)


@publico.get("/agendar", response_class=HTMLResponse)
@publico.get("/n/{nombre}/agendar", response_class=HTMLResponse)
def agendar(request: Request, nombre: str | None = None, caso: int | None = None, idioma: str = "es", conn=Depends(conn_publica)):
    return render(request, "identificar.html", lang=idioma if idioma in copia.COPIA else "es", error=None, nuevo=None, values={})


def _pagina_solicitud(request: Request, interes: str, idioma: str, paquete: str = ""):
    """El formulario de solicitud en página aparte: el respaldo sin JavaScript de los botones que abren el asistente.
    No abre la base de datos; el envío es el mismo `POST /sitio/solicitud`."""
    lang = idioma if idioma in copia.COPIA else "es"
    t = copia.COPIA[lang]
    titulo = {"evaluacion_virtual": t["evaluacion"]["form_titulo"], "experiencia": t["experiencias"]["form_titulo"],
              "contacto": t["contacto"]["titulo"]}[interes]
    values = {"paquete": paquete if paquete in copia.PAQUETES else ""}
    return render(request, "solicitud.html", lang=lang, interes=interes, titulo=titulo, values=values, error=None, hecho=False)


@publico.get("/evaluacion", response_class=HTMLResponse, include_in_schema=False)
def pagina_evaluacion(request: Request, idioma: str = "es"):
    return _pagina_solicitud(request, "evaluacion_virtual", idioma)


@publico.get("/experiencia", response_class=HTMLResponse, include_in_schema=False)
def pagina_experiencia(request: Request, idioma: str = "es", paquete: str = ""):
    return _pagina_solicitud(request, "experiencia", idioma, paquete)


@publico.get("/contacto", response_class=HTMLResponse, include_in_schema=False)
def pagina_contacto(request: Request, idioma: str = "es"):
    return _pagina_solicitud(request, "contacto", idioma)


@publico.post("/agendar/identificar", response_class=HTMLResponse)
@publico.post("/n/{nombre}/agendar/identificar", response_class=HTMLResponse)
def identificar(request: Request, nombre: str | None = None, documento: str = Form(...), celular: str = Form(...),
                nombres: str = Form(""), apellidos: str = Form(""), consentimiento: str = Form(""),
                correo: str = Form(""), acepta_correo: str = Form(""), idioma: str = Form("es"),
                servicio: str = Form(""), profesional: str = Form(""), desde: str = Form(""), panel: str = Form(""),
                conn=Depends(conn_publica)):
    from ..pacientes import normalizar_celular
    lang = idioma if idioma in copia.COPIA else "es"
    i = copia.COPIA[lang]["ident"]
    hx = bool(request.headers.get("HX-Request"))  # la landing pide solo el formulario y recibe solo el formulario
    uid = _uid(panel)
    # Lo que la tarjeta del asistente ya eligió (servicio, profesional y hora) llega oculto y se valida aquí: solo enteros y una hora
    # sin zona. Si no sirve se descarta; el calendario valida lo demás.
    pre = {"servicio": servicio if re.fullmatch(r"[1-9][0-9]{0,8}", servicio) else "",
           "profesional": profesional if re.fullmatch(r"[1-9][0-9]{0,8}", profesional) else "",
           "desde": desde if re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d", desde) else ""}
    pre = {k: v for k, v in pre.items() if v}

    def pagina(**ctx):
        return render(request, "_identificar.html" if hx else "identificar.html", lang=lang, uid=uid, pre=pre, **ctx)

    def ir(url):
        if hx:
            return HTMLResponse("", headers={"HX-Redirect": url})
        return RedirectResponse(url, status_code=303)

    documento = re.sub(r"\D", "", documento)
    phone = normalizar_celular(celular)
    values = {"documento": documento, "celular": celular}
    if not documento or not phone:
        return pagina(error=i["err_datos"],
                      nuevo=None, values=values)
    def limite():
        return render(request, "_identificar.html" if hx else "identificar.html", lang=lang, nuevo=None, values=values,
                      uid=uid, pre=pre, error=copia.COPIA[lang]["form"]["err_limite"], status_code=429)
    if not _identificacion_permitida(request):
        return limite()
    p = conn.execute("select * from paciente where documento=%s", (documento,)).fetchone()
    if p and p["celular"] == phone:
        return ir(f"/p/{links.make_token(p['id'], conn=conn, celular=p['celular'])}")
    if p and not _fallo_de_documento_permitido(documento):
        return limite()
    if p:  # No se revela nada: la clínica lo contactará y el caso aparece en el panel.
        familia.solicitar_contacto(conn, documento, phone, "Documento ya registrado con otro celular")
        return render(request, "_contacto.html" if hx else "contacto.html", lang=lang)
    if not nombres.strip():
        return pagina(error=None, nuevo=True, values=values)
    if not consentimiento:
        return pagina(error=i["err_consent"], nuevo=True,
                      values={**values, "nombres": nombres, "apellidos": apellidos, "correo": correo,
                              "acepta_correo": acepta_correo})
    if (correo.strip() and not correo_mod.es_direccion(correo)) or (acepta_correo and not correo.strip()):
        return pagina(nuevo=True,
                      error=i["err_correo"],
                      values={**values, "nombres": nombres, "apellidos": apellidos, "correo": correo,
                              "acepta_correo": acepta_correo, "consentimiento": consentimiento})
    now = clock.now(conn)
    en_ingles = lang == "en"  # quien se registra en el sitio en inglés queda marcado como internacional (la recepción lo revisa)
    pid = conn.execute(
        "insert into paciente(nombres, apellidos, documento, celular, consentimiento_en, consentimiento_version, creado_en, "
        "internacional, segmento_origen, segmento_marcado_en) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
        (nombres.strip(), apellidos.strip(), documento, phone, now, config.get(conn, "consentimiento_version"),
         now, en_ingles, "sitio_en" if en_ingles else None, now if en_ingles else None)).fetchone()["id"]
    if correo.strip():
        correo_mod.registrar_consentimiento(conn, pid, correo, bool(acepta_correo))
    return ir(f"/p/{links.make_token(pid, conn=conn, celular=phone)}/nueva" + (f"?{urlencode(pre)}" if pre else ""))


# ----------------------------------------------------------------- Mis citas

def _appointments(conn, patient_ids: list[int]):
    now = clock.now(conn)
    return conn.execute(
        "select c.*, p.nombre as profesional, s.nombre as servicio, pa.nombres as paciente_nombres from cita c "
        "join profesional p on p.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "join paciente pa on pa.id=c.paciente_id "
        "where c.paciente_id = any(%s) and c.estado = any(%s) and (c.rango is null or upper(c.rango) > %s) "
        "order by c.dia, c.rango",
        (patient_ids, list(ALIVE), now)).fetchall()


def _cita_del_hogar(conn, p: dict, cita_id: int, vivas: bool = True) -> dict:
    """Una cita del paciente o de sus familiares; cualquier otra es 404."""
    c = conn.execute("select * from cita where id=%s and paciente_id = any(%s)" + (" and estado = any(%s)" if vivas else ""),
                     (cita_id, familia.ids_del_hogar(conn, p)) + ((list(ALIVE),) if vivas else ())).fetchone()
    if c is None:
        raise HTTPException(404, "Esa cita ya no está vigente")
    return c


def _sujeto(conn, p: dict, para: int | None) -> dict:
    try:
        return familia.sujeto(conn, p, para)
    except familia.NoEsDeLaFamilia:
        raise HTTPException(404, "Esa persona no está en su familia") from None


def _primer_nombre(p: dict) -> str:
    return familia.primer_nombre(p)


def _siguientes(conn, p: dict, familiares: list[dict], cita_id: int | None) -> dict | None:
    """Tras agendar: botones «Agendar a X justo después» para el resto del hogar (mismo día y servicio)."""
    if not cita_id or not familiares:
        return None
    c = conn.execute("select * from cita where id=%s and paciente_id = any(%s) and rango is not null",
                     (cita_id, familia.ids_del_hogar(conn, p))).fetchone()
    if c is None:
        return None
    hogar = [p] + familiares
    # Solo quienes aún no tienen cita ese día.
    ocupados = {r["paciente_id"] for r in conn.execute(
        "select paciente_id from cita where paciente_id = any(%s) and dia=%s and estado = any(%s)",
        ([x["id"] for x in hogar], c["dia"], list(ALIVE))).fetchall()}
    otros = [{"id": x["id"], "texto": "Agendarme justo después" if x["id"] == p["id"] else
              f"Agendar a {_primer_nombre(x)} justo después"} for x in hogar if x["id"] not in ocupados]
    if not otros:
        return None
    fin = c["rango"].upper.astimezone(clock.TZ)
    return {"personas": otros, "servicio": c["servicio_id"], "desde": fin.strftime("%Y-%m-%dT%H:%M")}


@publico.get("/p/{token}", response_class=HTMLResponse)
def mis_citas(request: Request, token: str, aviso: str = "", cita: int | None = None, conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if p["etapa"] == "prospecto":
        return _pagina_prospecto(request, conn, token, p, aviso)
    fams = familia.familiares(conn, p["id"])
    responsable = familia.responsable_de(conn, p)
    hoy = clock.now(conn).astimezone(clock.TZ).date()
    # El acceso al asistente solo existe si sus rutas están registradas y el negocio lo encendió para los pacientes.
    asistente = bool(request.app.state.asistente) and bool(config.get(conn, "asistente_pacientes"))
    citas = _appointments(conn, familia.ids_del_hogar(conn, p))
    ahora = clock.now(conn)
    return render(request, "mis_citas.html", p=p, token=token, asistente=asistente, citas=citas,
                  confirmables={c["id"] for c in citas if _confirmable(c, ahora)}, aviso=aviso, familiares=fams, responsable=responsable, siguientes=_siguientes(conn, p, fams, cita),
                  menor=familia.es_menor(p["fecha_nacimiento"], hoy))


def _pagina_prospecto(request: Request, conn, token: str, p: dict, aviso: str = "", status_code: int = 200):
    """Un prospecto ve el estado de sus solicitudes y puede agregarles archivos; no agenda citas presenciales."""
    sols = conn.execute(
        "select s.id, s.momento, s.interes, s.idioma, s.gestionada, (select count(*) from solicitud_adjunto a "
        "where a.solicitud_id=s.id) as adjuntos from solicitud_contacto s where s.paciente_id=%s and s.origen='sitio' "
        "order by s.id desc", (p["id"],)).fetchall()
    lang = sols[0]["idioma"] if sols and sols[0]["idioma"] in copia.COPIA else "es"
    return render(request, "prospecto.html", p=p, token=token, solicitudes=sols, aviso=aviso, lang=lang,
                  interes_texto=solicitudes.INTERESES, status_code=status_code)


@publico.post("/p/{token}/adjuntos", response_class=HTMLResponse)
def prospecto_adjuntos(request: Request, token: str, fotos: list[UploadFile | str] = File(default=[]),
                       conn=Depends(conn_enlace)):
    """Agrega fotos o PDF a la última solicitud del prospecto, con las mismas reglas que el formulario del sitio."""
    p = patient_from_token(conn, token)
    ultima = conn.execute("select id, idioma from solicitud_contacto where paciente_id=%s and origen='sitio' "
                          "order by id desc limit 1", (p["id"],)).fetchone() if p["etapa"] == "prospecto" else None
    if ultima is None:
        return RedirectResponse(f"/p/{token}", status_code=303)
    lang = ultima["idioma"] if ultima["idioma"] in copia.COPIA else "es"
    f = copia.COPIA[lang]["form"]
    try:
        con_nombre = [u for u in fotos if not isinstance(u, str) and u.filename]
        if len(con_nombre) > solicitudes.MAX_ADJUNTOS:
            raise solicitudes.AdjuntoInvalido("cantidad")
        subidos = [solicitudes.Adjunto(u.filename or "", u.file.read(solicitudes.MAX_BYTES + 1)) for u in con_nombre]
        archivos = solicitudes.validar_adjuntos([a for a in subidos if a.datos])
        if not archivos:
            return RedirectResponse(f"/p/{token}", status_code=303)
        solicitudes.agregar_adjuntos(conn, ultima["id"], archivos)
    except solicitudes.AdjuntoInvalido as e:
        return _pagina_prospecto(request, conn, token, p, aviso=f[f"err_adjunto_{e}"], status_code=422)
    aviso = "Files added. Thank you!" if lang == "en" else "Listo, agregamos los archivos a su solicitud."
    return RedirectResponse(f"/p/{token}?aviso=" + quote(aviso), status_code=303)


@publico.get("/p/{token}/familia/agregar", response_class=HTMLResponse)
def familia_form(request: Request, token: str, conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    return render(request, "familia.html", p=p, token=token, error=None, values={}, parentescos=familia.PARENTESCOS,
                  responsable=familia.responsable_de(conn, p))


@publico.post("/p/{token}/familia/agregar", response_class=HTMLResponse)
def familia_agregar(request: Request, token: str, documento: str = Form(""), nombres: str = Form(""),
                    apellidos: str = Form(""), nacimiento: str = Form(""), parentesco: str = Form(""),
                    consentimiento: str = Form(""), conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    values = {"documento": documento, "nombres": nombres, "apellidos": apellidos, "nacimiento": nacimiento,
              "parentesco": parentesco}
    if not _identificacion_permitida(request, "".join(ch for ch in documento if ch.isdigit())):
        return render(request, "familia.html", p=p, token=token, error=copia.COPIA["es"]["form"]["err_limite"],
                      values=values, parentescos=familia.PARENTESCOS, responsable=familia.responsable_de(conn, p),
                      status_code=429)
    try:
        fid, ya_estaba = familia.agregar(conn, p, documento, nombres, apellidos, nacimiento, parentesco, bool(consentimiento))
    except familia.DatosInvalidos as e:
        return render(request, "familia.html", p=p, token=token, error=str(e), values=values,
                      parentescos=familia.PARENTESCOS, responsable=familia.responsable_de(conn, p), status_code=422)
    except familia.NoSePuede:
        return render(request, "familia.html", p=p, token=token, contacto=True, responsable=None)
    f = conn.execute("select nombres from paciente where id=%s", (fid,)).fetchone()
    aviso = f"{_primer_nombre(f)} ya estaba en su familia." if ya_estaba else \
        f"Agregamos a {_primer_nombre(f)} a su familia. Ya puede agendarle citas."
    return RedirectResponse(f"/p/{token}?aviso=" + quote(aviso), status_code=303)


@publico.post("/p/{token}/dejar-de-compartir", response_class=HTMLResponse)
def dejar_de_compartir(request: Request, token: str, conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if not p["responsable_id"]:
        return RedirectResponse(f"/p/{token}", status_code=303)
    try:
        familia.dejar_de_compartir(conn, p)
    except familia.DatosInvalidos as e:
        return RedirectResponse(f"/p/{token}?aviso=" + quote(str(e)), status_code=303)
    return RedirectResponse(f"/p/{token}?aviso=" + quote("Listo: sus citas ya no se comparten."), status_code=303)


def _slots(conn, professional_id, service_id):
    """`professional_id` 0 o None = «cualquier especialista»."""
    return agenda.available_slots(conn, professional_id, service_id) if professional_id else agenda.any_slots(conn, service_id)


DIAS_POR_PAGINA = 5


HORAS_POR_PAGINA = 9


def _vista(slots, dia=None, pag=0, hpag=0, desde: datetime | None = None):
    """Qué muestra la agenda a un toque: 5 días con espacios por página, el día elegido y sus horas.

    `desde` (agendar a un familiar justo después): abre el día y la página de horas del primer espacio a esa hora o
    después, y lo deja preseleccionado."""
    dias = list(slots)
    preseleccion = None
    if desde is not None:
        dia_d = desde.date()
        siguiente = next((t for t in slots.get(dia_d, []) if t >= desde), None)
        if siguiente is not None:
            preseleccion, dia = siguiente, dia_d
            pag = dias.index(dia_d) // DIAS_POR_PAGINA
            hpag = slots[dia_d].index(siguiente) // HORAS_POR_PAGINA
    pag = max(0, min(pag, max(0, (len(dias) - 1) // DIAS_POR_PAGINA)))
    pagina = dias[pag * DIAS_POR_PAGINA:(pag + 1) * DIAS_POR_PAGINA]
    elegido = dia if dia in pagina else (pagina[0] if pagina else None)
    todas = slots.get(elegido, [])
    hpag = hpag if 0 <= hpag <= max(0, (len(todas) - 1) // HORAS_POR_PAGINA) else 0
    return {"dias_pagina": pagina, "dia": elegido, "pag": pag, "hpag": hpag, "preseleccion": preseleccion,
            "horas": todas[hpag * HORAS_POR_PAGINA:(hpag + 1) * HORAS_POR_PAGINA],
            "hpag_sig": (hpag + 1) % max(1, -(-len(todas) // HORAS_POR_PAGINA)), "hay_mas_horas": len(todas) > HORAS_POR_PAGINA,
            "hay_anterior": pag > 0, "hay_siguiente": (pag + 1) * DIAS_POR_PAGINA < len(dias)}


def _espacios_resp(request, dia=None, pag=0, hpag=0, **ctx):
    return render(request, "_espacios.html", **ctx, **_vista(ctx["slots"], dia, pag, hpag))


def _picker_context(conn, service_id, professional_id, any_default=True, desde: datetime | None = None):
    services = conn.execute("select * from servicio where autoagendable order by id").fetchall()
    pros = conn.execute("select * from profesional where activo order by id").fetchall()
    if service_id not in [s["id"] for s in services]:
        service_id = None
    sid = service_id or services[0]["id"]
    pid = professional_id if professional_id is not None else (0 if any_default else pros[0]["id"])
    slots = _slots(conn, pid, sid)
    return {"services": services, "pros": pros, "sid": sid, "pid": pid, "slots": slots, **_vista(slots, desde=desde)}


def _hogar(conn, p: dict) -> list[dict]:
    """Personas para «¿Para quién es la cita?»: vacío si el paciente no gestiona a nadie."""
    fams = familia.familiares(conn, p["id"])
    if not fams:
        return []
    return [{"id": p["id"], "nombre": f"{_primer_nombre(p)} (usted)"}] + [{"id": f["id"], "nombre": _primer_nombre(f)} for f in fams]


def _desde(valor: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(valor).replace(tzinfo=clock.TZ) if valor else None
    except ValueError:
        return None


@publico.get("/p/{token}/nueva", response_class=HTMLResponse)
@publico.get("/p/{token}/agendar", response_class=HTMLResponse)
def nueva(request: Request, token: str, servicio: int | None = None, profesional: int | None = None,
          caso: int | None = None, para: int | None = None, desde: str | None = None, conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    s = _sujeto(conn, p, para)
    ctx = _picker_context(conn, servicio, profesional, desde=_desde(desde))
    return render(request, "elegir.html", p=p, token=token, modo="nueva", cita=None, error=None,
                  action=f"/p/{token}/agendar", hogar=_hogar(conn, p), para=s["id"], **ctx)


@publico.get("/p/{token}/espacios", response_class=HTMLResponse)
def espacios(request: Request, token: str, servicio: int, profesional: int = 0, cita: int | None = None,
             modo: str = "nueva", error: str | None = None, dia: str | None = None, pag: int = 0,
             hpag: int = 0, para: int | None = None, conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    s = _sujeto(conn, p, para)
    slots = _slots(conn, profesional, servicio)
    d = date.fromisoformat(dia) if dia else None
    return _espacios_resp(request, dia=d, pag=pag, hpag=hpag, slots=slots, sid=servicio, pid=profesional, token=token, cita=cita,
                          modo=modo, error=error, para=s["id"])


@publico.post("/p/{token}/agendar", response_class=HTMLResponse)
def agendar_post(request: Request, token: str, servicio: int = Form(...), profesional: int = Form(0),
                 inicio: str = Form(...), para: int | None = Form(None), conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    s = _sujeto(conn, p, para)
    try:
        cita_id = agenda.book(conn, s["id"], profesional or None, servicio, datetime.fromisoformat(inicio), "paciente",
                              "paciente")
    except agenda.SlotTaken:
        slots = _slots(conn, profesional, servicio)
        return _espacios_resp(request, slots=slots, sid=servicio, pid=profesional, token=token, cita=None, para=s["id"],
                              modo="nueva", error="Ese espacio acaba de ocuparse. Esta es la lista actualizada.")
    quien = "Su cita" if s["id"] == p["id"] else f"La cita de {_primer_nombre(s)}"
    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = f"/p/{token}?cita={cita_id}&aviso=" + quote(
        f"{quien} quedó agendada. Le enviamos la confirmación por WhatsApp.")
    return resp


@publico.get("/p/{token}/cambiar/{cita_id}", response_class=HTMLResponse)
def cambiar(request: Request, token: str, cita_id: int, servicio: int | None = None, profesional: int | None = None,
            conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    c = _cita_del_hogar(conn, p, cita_id)
    ctx = _picker_context(conn, c["servicio_id"], c["profesional_id"])
    ctx["services"] = [s for s in ctx["services"] if s["id"] == c["servicio_id"]] or ctx["services"]
    if c["servicio_id"] not in [s["id"] for s in ctx["services"]]:
        ctx["services"] = conn.execute("select * from servicio where id=%s", (c["servicio_id"],)).fetchall()
    ctx["slots"] = agenda.available_slots(conn, c["profesional_id"], c["servicio_id"])
    ctx.update(_vista(ctx["slots"]))
    ctx["sid"], ctx["pid"] = c["servicio_id"], c["profesional_id"]
    s = _sujeto(conn, p, c["paciente_id"])
    return render(request, "elegir.html", p=p, token=token, modo="cambiar", cita=cita_id, error=None,
                  action=f"/p/{token}/cambiar/{cita_id}", hogar=[], para=s["id"],
                  para_nombre=None if s["id"] == p["id"] else _primer_nombre(s), **ctx)


@publico.post("/p/{token}/cambiar/{cita_id}", response_class=HTMLResponse)
def cambiar_post(request: Request, token: str, cita_id: int, inicio: str = Form(...), conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    c = _cita_del_hogar(conn, p, cita_id, vivas=False)
    try:
        agenda.reschedule(conn, cita_id, datetime.fromisoformat(inicio), "paciente")
    except agenda.SlotTaken:
        slots = agenda.available_slots(conn, c["profesional_id"], c["servicio_id"])
        return _espacios_resp(request, slots=slots, sid=c["servicio_id"], pid=c["profesional_id"], token=token,
                              cita=cita_id, modo="cambiar", para=c["paciente_id"],
                              error="Ese espacio acaba de ocuparse. Esta es la lista actualizada.")
    s = _sujeto(conn, p, c["paciente_id"])
    quien = "su cita" if s["id"] == p["id"] else f"la cita de {_primer_nombre(s)}"
    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = f"/p/{token}?aviso=" + quote(f"Cambiamos la fecha de {quien}.")
    return resp


def _confirmable(c: dict, ahora: datetime) -> bool:
    """Una cita que la persona puede confirmar desde su enlace: viva, sin confirmar y que aún no empieza."""
    return c["estado"] in ("programada", "no_confirmada") and c["rango"] is not None and c["rango"].lower > ahora


@publico.post("/p/{token}/confirmar/{cita_id}", response_class=HTMLResponse)
def confirmar(request: Request, token: str, cita_id: int, conn=Depends(conn_enlace)):
    """«Sí, asistiré» desde el enlace: el mismo paso que el botón del recordatorio, sin mensaje de vuelta (lo ve en pantalla)."""
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    c = _cita_del_hogar(conn, p, cita_id)
    s = _sujeto(conn, p, c["paciente_id"])
    quien = "su cita" if s["id"] == p["id"] else f"la cita de {_primer_nombre(s)}"
    if c["estado"] == "confirmada":
        aviso = f"{quien[0].upper()}{quien[1:]} ya estaba confirmada."
    elif not _confirmable(c, clock.now(conn)):
        aviso = f"{quien[0].upper()}{quien[1:]} ya empezó: no se puede confirmar."
    else:
        lifecycle.transition(conn, cita_id, "confirmada", "paciente", "Confirmó desde su enlace")
        aviso = f"Listo: confirmamos {quien}. ¡Le esperamos!"
    if request.headers.get("HX-Request") == "true":
        return render(request, "_asistente_contacto.html", aviso=aviso)
    return RedirectResponse(f"/p/{token}?aviso=" + quote(aviso), status_code=303)


@publico.get("/p/{token}/cancelar/{cita_id}", response_class=HTMLResponse)
def cancelar(request: Request, token: str, cita_id: int, conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    c = _cita_del_hogar(conn, p, cita_id)
    s = _sujeto(conn, p, c["paciente_id"])
    motivos = catalog.motivos_activos(conn)
    return render(request, "cancelar.html", p=p, token=token, cita_id=cita_id, motivos=motivos,
                  para_nombre=None if s["id"] == p["id"] else _primer_nombre(s))


@publico.post("/p/{token}/cancelar/{cita_id}", response_class=HTMLResponse)
def cancelar_post(request: Request, token: str, cita_id: int, motivo: int = Form(...), conn=Depends(conn_enlace)):
    p = patient_from_token(conn, token)
    if (r := _sin_citas(request, token, p)):
        return r
    c = _cita_del_hogar(conn, p, cita_id, vivas=False)
    agenda.cancel(conn, cita_id, "paciente", "enlace", reason_id=motivo)
    # Tras cancelar se ofrecen espacios de inmediato, para la misma persona.
    ctx = _picker_context(conn, c["servicio_id"], c["profesional_id"])
    if c["servicio_id"] not in [s["id"] for s in ctx["services"]]:
        ctx["services"] = conn.execute("select * from servicio where id=%s", (c["servicio_id"],)).fetchall()
    ctx["sid"], ctx["pid"] = c["servicio_id"], c["profesional_id"]
    ctx["slots"] = agenda.available_slots(conn, c["profesional_id"], c["servicio_id"])
    ctx.update(_vista(ctx["slots"]))
    s = _sujeto(conn, p, c["paciente_id"])
    return render(request, "elegir.html", p=p, token=token, modo="nueva", cita=None, error=None,
                  action=f"/p/{token}/agendar", cancelada=True, hogar=[], para=s["id"],
                  para_nombre=None if s["id"] == p["id"] else _primer_nombre(s), **ctx)


@publico.get("/correo/baja/{token}", response_class=HTMLResponse)
def baja_correo_pagina(request: Request, token: str, conn=Depends(conn_baja)):
    """Pide confirmar: un GET no cambia nada (los escáneres de enlaces precargan los correos)."""
    return render(request, "baja_correo.html", token=token, hecha=False)


@publico.post("/correo/baja/{token}", response_class=HTMLResponse)
def baja_correo(request: Request, token: str, conn=Depends(conn_baja)):
    """Da de baja SOLO el correo (idempotente). La baja de WhatsApp es otra y no se toca. También atiende la baja de un
    clic de los clientes de correo (`List-Unsubscribe-Post`)."""
    correo_mod.dar_de_baja(conn, request.state.paciente_baja)
    return render(request, "baja_correo.html", token=token, hecha=True)


# ----------------------------------------------------------------- Simulador de WhatsApp

def _clock_info(conn):
    return {"ahora": clock.now(conn), "demo": config.get(conn, "demo_mode")}


@sim.get("/simulador", response_class=HTMLResponse)
def simulador(request: Request, paciente: int | None = None, q: str = "", conn=Depends(conn_simulador)):
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
    msgs = conn.execute("select * from mensaje where paciente_id=%s and estado_entrega='entregado' and canal <> 'correo' "
                        "order by momento, id", (patient_id,)).fetchall()
    correos = conn.execute("select * from mensaje where paciente_id=%s and canal='correo' and direccion='saliente' "
                           "order by momento, id", (patient_id,)).fetchall()
    citas = conn.execute(
        "select c.id, c.estado, c.rango, pr.nombre as profesional from cita c join profesional pr on pr.id=c.profesional_id "
        "where c.paciente_id=%s and c.estado = any(%s) and c.rango is not null order by lower(c.rango)",
        (patient_id, list(ALIVE))).fetchall()
    return {"p": p, "msgs": msgs, "citas": citas, "correos": correos}


@sim.get("/simulador/burbujas/{patient_id}", response_class=HTMLResponse)
def burbujas(request: Request, patient_id: int, conn=Depends(conn_simulador)):
    return render(request, "_burbujas.html", chat=_chat_ctx(conn, patient_id))


@sim.post("/simulador/boton", response_class=HTMLResponse, dependencies=[Depends(mismo_origen)])
def boton(request: Request, paciente: int = Form(...), boton: str = Form(...), conn=Depends(conn_simulador)):
    messaging.receive(conn, paciente, button_id=boton)
    conn.commit()
    tasks.cycle()
    return RedirectResponse(f"/simulador?paciente={paciente}", status_code=303)


@sim.post("/simulador/texto", response_class=HTMLResponse, dependencies=[Depends(mismo_origen)])
def texto(request: Request, paciente: int = Form(...), texto: str = Form(...), conn=Depends(conn_simulador)):
    messaging.receive(conn, paciente, text=texto)
    return RedirectResponse(f"/simulador?paciente={paciente}", status_code=303)


@sim.post("/simulador/reloj", response_class=HTMLResponse, dependencies=[Depends(mismo_origen)])
def reloj(request: Request, accion: str = Form(...), paciente: int | None = Form(None), cita: int | None = Form(None),
          conn=Depends(conn_simulador)):
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

MAX_CUERPO_WEBHOOK = 256 * 1024


@canal_entrante.post("/canales/{tipo}/webhook", include_in_schema=False)
async def webhook_canal(tipo: str, request: Request):
    """Entrada de mensajes de un proveedor: se resuelve el negocio por el canal, se verifica la firma con el secreto
    de ESE canal, se fija el contexto y se procesa como cualquier mensaje entrante (sin repetir reenvíos)."""
    from ..pacientes import normalizar_celular
    a = canales.adaptador(tipo)
    if a is None:
        raise HTTPException(404, "Canal desconocido")
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > MAX_CUERPO_WEBHOOK:
        raise HTTPException(413, "Cuerpo demasiado grande")
    trozos, total = [], 0
    async for trozo in request.stream():
        total += len(trozo)
        if total > MAX_CUERPO_WEBHOOK:
            raise HTTPException(413, "Cuerpo demasiado grande")
        trozos.append(trozo)
    crudo = b"".join(trozos)
    cuerpo = canales.cuerpo_json(crudo)
    if cuerpo is None:
        raise HTTPException(404, "Canal desconocido")
    id_canal = a.identificar(cuerpo)
    conn = db.connect(negocio=None)
    try:
        nid = conn.execute("select negocio_de_canal(%s,%s) n", (tipo, id_canal)).fetchone()["n"] if id_canal else None
        if nid is None:
            raise HTTPException(404, "Canal desconocido")
        db.fijar(conn, nid)
        canal = conn.execute("select * from canal_negocio where tipo=%s and id_externo=%s and activo", (tipo, id_canal)).fetchone()
        secreto = canales.secreto_de(canal) if canal else None
        if not secreto or not a.verificar(crudo, request.headers, secreto):
            raise HTTPException(401, "Firma inválida")
        ent = a.traducir(cuerpo)
        if ent is None:
            raise HTTPException(422, "Mensaje no entendido")
        if conn.execute("select 1 from mensaje where canal=%s and id_externo=%s", (tipo, ent.id_mensaje)).fetchone():
            return {"estado": "repetido"}
        celular = normalizar_celular(ent.celular)
        # Un celular compartido por un solo hogar es del responsable: a él van los avisos agrupados (docs/prd-familia.md
        # R9). Compartido por pacientes sin relación, sigue ambiguo (queda para el PRD de WhatsApp).
        hogares = conn.execute("select distinct coalesce(responsable_id, id) as raiz from paciente where celular=%s",
                               (celular,)).fetchall() if celular else []
        if not hogares:
            return {"estado": "sin_paciente"}
        raiz = hogares[0]["raiz"] if len(hogares) == 1 else _hogar_del_ultimo_mensaje(conn, celular)
        if raiz is None:
            return {"estado": "ambiguo"}
        messaging.receive(conn, raiz, button_id=ent.boton, text=ent.texto, channel=tipo, id_externo=ent.id_mensaje)
        conn.commit()
        return {"estado": "recibido"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _hogar_del_ultimo_mensaje(conn, celular: str) -> int | None:
    """Un celular que quedó en dos hogares (alguien dejó de compartir y conservó el número): la respuesta es del hogar
    al que se le escribió por última vez en los últimos 7 días. Si a ninguno, sigue ambigua."""
    r = conn.execute(
        "select coalesce(p.responsable_id, p.id) as raiz from mensaje m join paciente p on p.id=m.paciente_id "
        "where p.celular=%s and m.direccion='saliente' and m.estado_entrega='entregado' and m.momento > %s "
        "order by m.momento desc, m.id desc limit 1", (celular, clock.now(conn) - timedelta(days=7))).fetchone()
    return r["raiz"] if r else None


def exigir_tick(request: Request, x_tick_secreto: str = Header("")) -> None:
    """`/tick` sin protección en `local`; con el secreto en `demo`; y solo si hay secreto configurado en producción."""
    if request.app.state.entorno == "local":
        return
    esperado = settings.TICK_SECRETO
    if not esperado or not secrets.compare_digest(x_tick_secreto.encode(), esperado.encode()):
        raise HTTPException(401, "Falta el secreto del ciclo de tareas")


@operacion.post("/tick", include_in_schema=False)
def tick(_=Depends(exigir_tick)):
    """Ejecuta el mismo ciclo que el trabajador (para un programador externo, como `pg_cron`)."""
    return tasks.cycle()


@operacion_salud.get("/salud")
def salud(conn=Depends(get_conn)):
    conn.execute("select 1")
    return {"ok": True}


CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
SIN_CACHE = ("/p/", "/correo/baja/", "/api/v1/", "/simulador")
NOINDEX_NOFOLLOW = ("/p/", "/panel", "/simulador", "/correo/baja/", "/api/", "/sitio/")


async def cabeceras_de_seguridad(request: Request, call_next):
    """Cabeceras de defensa en profundidad en todas las respuestas (H-08)."""
    resp = await call_next(request)
    ruta = request.url.path
    h = resp.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    # En `local` Swagger/ReDoc cargan recursos de un CDN: solo ahí se omite la CSP.
    if not (request.app.state.entorno == "local" and ruta in ("/docs", "/redoc")):
        h["Content-Security-Policy"] = CSP
    if settings.BASE_URL.startswith("https://"):
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if ruta.startswith(SIN_CACHE):
        h["Cache-Control"] = "no-store"
    elif ruta.startswith("/static/"):
        if "v" in request.query_params:
            h["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            h["Cache-Control"] = "public, max-age=604800"
    if ruta == "/agendar" or ruta.startswith("/agendar/"):
        h["X-Robots-Tag"] = "noindex, follow"
    elif ruta.startswith(NOINDEX_NOFOLLOW):
        h["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def crear_app(entorno: str | None = None, asistente: bool | None = None) -> FastAPI:
    """Construye la aplicación del entorno: lo que ese entorno no permite NO se registra como ruta (PRD #4, D7).

    `asistente`: sin la clave de la API (`ANTHROPIC_API_KEY`) las rutas del asistente no existen. El generador del esquema
    OpenAPI lo pide siempre (`True`) para que el contrato las incluya.
    """
    entorno = entorno or settings.ENTORNO
    if asistente is None:
        asistente = settings.asistente_configurado()
    if entorno != "local" and not os.environ.get("PYTEST_CURRENT_TEST"):
        arranque.exigir(entorno)
    sin_docs = {} if entorno == "local" else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Estud-IA", description="Gestión inteligente de citas", **sin_docs)
    app.state.entorno = entorno
    app.state.asistente = bool(asistente)
    registrar_errores(app)
    logs.instalar(app)
    app.middleware("http")(cabeceras_de_seguridad)
    app.include_router(api_router)
    from . import asistente_visitante
    app.include_router(asistente_visitante.pasos)  # los botones del sitio no llaman al modelo: existen sin clave
    if asistente:
        from ..api.asistente import router as asistente_router
        app.include_router(asistente_router)
        from .asistente_paciente import router as asistente_paciente_router
        app.include_router(asistente_paciente_router)
        app.include_router(asistente_visitante.router)
    app.include_router(panel_router)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.include_router(publico)
    if entorno != "produccion":
        app.include_router(sim)
    app.include_router(operacion_salud)
    app.include_router(canal_entrante)
    if entorno != "produccion" or settings.TICK_SECRETO:
        app.include_router(operacion)
    return app


app = crear_app()
