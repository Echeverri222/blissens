"""Las herramientas del asistente (PRD asistente, §5). Cada una reutiliza una función de dominio que ya existe.

Un manejador recibe `(conn, actor, args)` y devuelve un dict. Aplica en Python el alcance que la base no impone (RLS solo aísla
negocios): el hogar de un paciente o el profesional de un especialista. Un id fuera de ese alcance es `no_existe`, igual que
uno que no existe. Ningún manejador escribe: las propuestas solo describen lo que la persona puede confirmar.
"""
from datetime import date, datetime, timedelta
from typing import Literal

from psycopg.types.range import Range
from pydantic import Field

from .. import agenda, bandejas, clock, config, familia, fmt, horario, indicators, permisos
from ..lifecycle import ALIVE
from .actor import Actor
from .base import LECTURA, PROPUESTA, Entrada, ErrorHerramienta, herramienta

PAC = ("paciente",)
ESP = ("especialista",)
AUX = ("auxiliar", "operador")  # el operador local ve lo mismo que la auxiliar, solo lectura
MAX_DIAS_AGENDA = 42
MAX_FILAS = 50
MAX_ESPACIOS = 12
MAX_CITAS_PACIENTE = 20


# ----------------------------------------------------------------- utilidades

def _bogota(d: datetime) -> datetime:
    """Una hora sin zona se interpreta como hora de Bogotá (igual que `api.comun.a_bogota`)."""
    return d.replace(tzinfo=clock.TZ) if d.tzinfo is None else d.astimezone(clock.TZ)


def _iso(d: datetime | None) -> str | None:
    return d.astimezone(clock.TZ).isoformat() if d else None


def _cuando(d: datetime) -> str:
    return fmt.fecha_hora(d.astimezone(clock.TZ))


def _nombre(p: dict) -> str:
    return f"{p['nombres']} {p['apellidos']}".strip()


def _ultimos4(documento: str | None) -> str | None:
    return documento[-4:] if documento else None


def _inicio(c: dict) -> datetime | None:
    return c["rango"].lower if c.get("rango") else None


def _fin(c: dict) -> datetime | None:
    return c["rango"].upper if c.get("rango") else None


def _paciente(conn, actor: Actor) -> dict:
    p = conn.execute("select * from paciente where id=%s", (actor.paciente_id,)).fetchone()
    if p is None:
        raise permisos.NoExiste("No existe ese paciente")
    return p


def _rango_de_fechas(desde: date, hasta: date | None) -> date:
    hasta = hasta or desde
    if hasta < desde:
        raise ErrorHerramienta("datos_invalidos", "La fecha final no puede ser anterior a la inicial.")
    if (hasta - desde).days + 1 > MAX_DIAS_AGENDA:
        raise ErrorHerramienta("datos_invalidos", f"El rango no puede pasar de {MAX_DIAS_AGENDA} días.")
    return hasta


def _servicio(conn, servicio_id: int, solo_autoagendables: bool) -> dict:
    s = conn.execute("select id, nombre, duracion_min, autoagendable from servicio where id=%s and activo",
                     (servicio_id,)).fetchone()
    if s is None or (solo_autoagendables and not s["autoagendable"]):
        raise permisos.NoExiste("No existe ese servicio")
    return s


def _profesional(conn, profesional_id: int) -> dict:
    r = conn.execute("select id, nombre from profesional where id=%s and activo", (profesional_id,)).fetchone()
    if r is None:
        raise permisos.NoExiste("No existe ese profesional")
    return r


def _limitar(filas: list, n: int = MAX_FILAS) -> dict:
    return {"filas": filas[:n], "total": len(filas), "hay_mas": len(filas) > n}


def _cita_agenda(c: dict, u: dict, ahora: datetime, con_profesional: bool) -> dict:
    ini = _inicio(c)
    out = {"id": c["id"], "estado": c["estado"], "inicio": ini, "fin": _fin(c), "servicio": c["servicio"],
           "paciente": c["paciente"], "acciones": permisos.acciones_cita(u, c["estado"], ini, ahora)}
    if con_profesional:
        out["profesional_id"], out["profesional"] = c["profesional_id"], c["profesional"]
    return out


def _bloqueo(b: dict) -> dict:
    return {"id": b["id"], "profesional_id": b["profesional_id"], "inicio": b["rango"].lower, "fin": b["rango"].upper,
            "motivo": b["motivo"]}


def _agenda(conn, u: dict, desde: date, hasta: date | None, profesional_id: int | None, con_profesional: bool) -> dict:
    hasta = _rango_de_fechas(desde, hasta)
    if profesional_id is not None:
        _profesional(conn, profesional_id)
    r = agenda.range_agenda(conn, desde, hasta, profesional_id)
    ahora = clock.now(conn)
    return {"desde": desde, "hasta": hasta,
            "citas": [_cita_agenda(c, u, ahora, con_profesional) for c in r["citas"]],
            "citas_sin_hora": [_cita_agenda(c, u, ahora, con_profesional) for c in r["citas_sin_hora"]],
            "bloqueos": [_bloqueo(b) for b in r["bloqueos"]],
            "cupos_liberados": [{"inicio": c["rango"].lower, "fin": c["rango"].upper, "estado": c["estado"]}
                                for c in r["cupos"]]}


def _propuesta(tipo: str, parametros: dict, resumen: str) -> dict:
    return {"propuesta": {"tipo": tipo, "parametros": parametros, "resumen": resumen}}


# ----------------------------------------------------------------- lecturas compartidas

class SinEntrada(Entrada):
    pass


class MisCitas(Entrada):
    para: int | None = Field(None, ge=1, description="Id de un familiar (de `hogar`) para ver solo sus citas. Sin él, las de todo el hogar.")


@herramienta("mis_citas", "Las citas próximas del hogar de quien pregunta: nombre de pila, servicio, profesional, fecha, hora y estado. "
             "Devuelve también las personas del hogar con su id.", MisCitas, PAC, LECTURA, auditoria="asistente:mis_citas")
def mis_citas(conn, actor, a: MisCitas) -> dict:
    p = _paciente(conn, actor)
    ids = [familia.sujeto(conn, p, a.para)["id"]] if a.para else familia.ids_del_hogar(conn, p)
    filas = conn.execute(
        "select c.id, c.estado, c.rango, pa.id as persona_id, pa.nombres, pr.nombre as profesional, s.nombre as servicio "
        "from cita c join profesional pr on pr.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "join paciente pa on pa.id=c.paciente_id "
        "where c.paciente_id = any(%s) and c.estado = any(%s) and (c.rango is null or upper(c.rango) > %s) "
        "order by c.dia, c.rango limit %s", (ids, list(ALIVE), clock.now(conn), MAX_CITAS_PACIENTE)).fetchall()
    hogar = [p] + familia.familiares(conn, p["id"])
    return {"citas": [{"id": c["id"], "persona_id": c["persona_id"], "nombre": familia.primer_nombre(c["nombres"]),
                       "servicio": c["servicio"], "profesional": c["profesional"], "inicio": _inicio(c),
                       "cuando": _cuando(_inicio(c)) if c["rango"] else "por confirmar", "estado": c["estado"]} for c in filas],
            "hogar": [{"id": x["id"], "nombre": familia.primer_nombre(x), "es_quien_pregunta": x["id"] == p["id"]} for x in hogar]}


@herramienta("servicios", "Los servicios que ofrece el negocio, con su duración en minutos.", SinEntrada,
             PAC + ("especialista", "auxiliar", "operador"), LECTURA)
def servicios(conn, actor, a) -> dict:
    # El paciente solo ve lo que su página de agendar ofrece; el valor del servicio nunca sale (es un promedio interno).
    filas = conn.execute("select id, nombre, duracion_min, autoagendable from servicio where activo "
                         + ("and autoagendable " if actor.perfil == "paciente" else "") + "order by id").fetchall()
    quitar = ("autoagendable",) if actor.perfil == "paciente" else ()
    return {"servicios": [{k: v for k, v in f.items() if k not in quitar} for f in filas]}


class EspaciosLibres(Entrada):
    servicio_id: int = Field(ge=1)
    profesional_id: int | None = Field(None, ge=1, description="Sin él, se ofrecen las horas de cualquier especialista.")
    desde: date | None = Field(None, description="Primer día a mostrar (AAAA-MM-DD). Por defecto, hoy.")
    dias: int = Field(14, ge=1, le=60, description="Cuántos días hacia adelante buscar.")


@herramienta("espacios_libres", f"Horas libres para agendar un servicio, con un profesional o con cualquiera. Máximo {MAX_ESPACIOS} por llamada, "
             "en orden. Usa `desde` para ver más adelante.", EspaciosLibres, PAC + ("auxiliar", "operador"), LECTURA)
def espacios_libres(conn, actor, a: EspaciosLibres) -> dict:
    srv = _servicio(conn, a.servicio_id, actor.perfil == "paciente")
    pro = _profesional(conn, a.profesional_id) if a.profesional_id else None
    hoy = clock.now(conn).date()
    dias = min(90, (max(a.desde, hoy) - hoy).days + a.dias) if a.desde else a.dias
    por_dia = (agenda.available_slots(conn, pro["id"], srv["id"], days=dias) if pro
               else agenda.any_slots(conn, srv["id"], days=dias))
    horas = [h for d, hs in por_dia.items() if not a.desde or d >= a.desde for h in hs]
    return {"servicio": srv["nombre"], "duracion_min": srv["duracion_min"], "profesional": pro["nombre"] if pro else "cualquiera",
            "espacios": [{"inicio": h, "cuando": _cuando(h)} for h in horas[:MAX_ESPACIOS]], "hay_mas": len(horas) > MAX_ESPACIOS}


@herramienta("datos_del_negocio", "Nombre y dirección del negocio y su horario de atención por día de la semana.", SinEntrada,
             PAC + ("especialista", "auxiliar", "operador"), LECTURA)
def datos_del_negocio(conn, actor, a) -> dict:
    n = conn.execute("select nombre from negocio where id=%s", (actor.negocio_id,)).fetchone()
    filas = conn.execute(
        "select h.dia_semana, min(h.desde) as desde, max(h.hasta) as hasta from horario_atencion h "
        "join profesional p on p.id=h.profesional_id where p.activo group by h.dia_semana order by h.dia_semana").fetchall()
    return {"nombre": n["nombre"] if n else None, "direccion": config.get(conn, "direccion"),
            "horario": [{"dia": fmt.DIAS[f["dia_semana"]], "desde": f["desde"], "hasta": f["hasta"]} for f in filas]}


# ----------------------------------------------------------------- agenda y citas del equipo

class RangoAgenda(Entrada):
    desde: date = Field(description="Primer día (AAAA-MM-DD).")
    hasta: date | None = Field(None, description=f"Último día, inclusive. Por defecto el mismo día. Máximo {MAX_DIAS_AGENDA} días.")


class AgendaDe(RangoAgenda):
    profesional_id: int | None = Field(None, ge=1, description="Sin él, la agenda de todos los profesionales.")


def _profesional_propio(u: dict) -> int:
    if not u.get("profesional_id"):  # sin esto, `alcance_profesional` devolvería None y la agenda se ampliaría a todos
        raise permisos.NoExiste("No existe ese profesional")
    return permisos.alcance_profesional(u, None)


@herramienta("mi_agenda", "Tu agenda: citas, bloqueos y cupos liberados entre dos fechas. Solo la tuya.", RangoAgenda, ESP, LECTURA)
def mi_agenda(conn, actor, a: RangoAgenda) -> dict:
    return _agenda(conn, actor.usuario, a.desde, a.hasta, _profesional_propio(actor.usuario), con_profesional=False)


@herramienta("agenda", "Agenda del negocio entre dos fechas: citas, bloqueos y cupos liberados, de todos los profesionales o de uno.",
             AgendaDe, AUX, LECTURA)
def agenda_del_negocio(conn, actor, a: AgendaDe) -> dict:
    return _agenda(conn, actor.usuario_de_alcance, a.desde, a.hasta, a.profesional_id, con_profesional=True)


class CitaId(Entrada):
    cita_id: int = Field(ge=1, description="Id de la cita.")


@herramienta("detalle_cita", "Detalle de una cita: estado, hora, servicio, profesional, paciente, acciones posibles e historial. "
             "El especialista solo ve las suyas.", CitaId, ("especialista", "auxiliar", "operador"), LECTURA, auditoria="ver_cita")
def detalle_cita(conn, actor, a: CitaId) -> dict:
    u = actor.usuario_de_alcance
    permisos.cita_visible(conn, u, a.cita_id)
    c = conn.execute(
        "select c.id, c.estado, c.dia, c.rango, c.profesional_id, pr.nombre as profesional, s.nombre as servicio, "
        "p.id as paciente_id, p.nombres || ' ' || p.apellidos as paciente from cita c "
        "join profesional pr on pr.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "join paciente p on p.id=c.paciente_id where c.id=%s", (a.cita_id,)).fetchone()
    hist = conn.execute(
        "select h.estado_anterior, h.estado_nuevo, h.actor, h.detalle, h.momento from historial_estado h "
        "where h.cita_id=%s order by h.momento, h.id", (a.cita_id,)).fetchall()
    return {"id": c["id"], "estado": c["estado"], "dia": c["dia"], "inicio": _inicio(c), "fin": _fin(c),
            "profesional": c["profesional"], "servicio": c["servicio"],
            "paciente": {"id": c["paciente_id"], "nombre": c["paciente"]},
            "acciones": permisos.acciones_cita(u, c["estado"], _inicio(c), clock.now(conn)), "historial": hist}


class MiHorario(Entrada):
    dias: int = Field(30, ge=1, le=90, description="Cuántos días hacia adelante listar bloqueos.")


@herramienta("mi_horario", "Tu horario semanal de atención y tus bloqueos próximos.", MiHorario, ESP, LECTURA)
def mi_horario(conn, actor, a: MiHorario) -> dict:
    pro = _profesional_propio(actor.usuario)
    hoy = clock.now(conn).date()
    return {"franjas": [{"dia": fmt.DIAS[f["dia_semana"]], "desde": f["desde"], "hasta": f["hasta"]}
                        for f in horario.schedule(conn, pro)],
            "bloqueos": [_bloqueo(b) for b in horario.list_blocks(conn, pro, hoy, hoy + timedelta(days=a.dias))]}


# ----------------------------------------------------------------- pacientes y bandejas (auxiliar)

class BuscarPacientes(Entrada):
    q: str = Field(min_length=1, max_length=80, description="Parte del nombre, apellido, documento o celular.")


@herramienta("buscar_pacientes", "Busca pacientes por nombre, documento o celular. Máximo 10: id, nombre y últimos 4 dígitos del documento.",
             BuscarPacientes, AUX, LECTURA, auditoria="buscar_paciente")
def buscar_pacientes(conn, actor, a: BuscarPacientes) -> dict:
    filas = bandejas.find_patients(conn, a.q)
    return {"pacientes": [{"id": f["id"], "nombre": _nombre(f), "documento_ultimos4": _ultimos4(f["documento"])}
                          for f in filas[:10]], "hay_mas": len(filas) > 10}


class PacienteId(Entrada):
    paciente_id: int = Field(ge=1, description="Id del paciente (sale de `buscar_pacientes`).")


@herramienta("ficha_paciente", "Resumen de un paciente: nombre, últimos 4 del documento, consentimientos, sus últimas 20 citas, "
             "casos de seguimiento abiertos y sus últimos 10 mensajes. Sin teléfono, correo ni fecha de nacimiento.",
             PacienteId, AUX, LECTURA, auditoria="ver_ficha")
def ficha_paciente(conn, actor, a: PacienteId) -> dict:
    if not conn.execute("select 1 from paciente where id=%s", (a.paciente_id,)).fetchone():
        raise permisos.NoExiste("No existe ese paciente")
    r = bandejas.patient_record(conn, a.paciente_id)
    p = r["paciente"]
    return {
        "paciente": {"id": p["id"], "nombre": _nombre(p), "documento_ultimos4": _ultimos4(p["documento"]),
                     "acepta_mensajes": p["acepta_mensajes"], "acepta_correo": p["acepta_correo"]},
        "citas": [{"id": c["id"], "estado": c["estado"], "dia": c["dia"], "inicio": _inicio(c), "servicio": c["servicio"],
                   "profesional": c["profesional"]} for c in r["citas"][:20]],
        "casos_abiertos": [{"id": c["id"], "tipo": c["tipo"], "escalado": c["escalado"], "abierto_en": c["abierto_en"],
                            "intentos": len(c["intentos"] or [])} for c in r["casos"] if c["estado"] == "abierto"],
        "mensajes": [{"direccion": m["direccion"], "momento": m["momento"], "texto": m["texto"], "respuesta": m["respuesta"]}
                     for m in r["mensajes"][-10:]]}


@herramienta("resumen_dia", "Los cuatro contadores del día: citas de hoy, sin confirmar, mensajes sin interpretar y citas por cerrar.",
             SinEntrada, AUX, LECTURA)
def resumen_dia(conn, actor, a) -> dict:
    return bandejas.resumen_dia(conn)


BANDEJAS = {
    "no_confirmadas": bandejas.no_confirmadas, "seguimientos": bandejas.seguimientos, "en_riesgo": bandejas.en_riesgo,
    "cupos_libres": bandejas.cupos_libres, "sin_desenlace": bandejas.sin_desenlace, "sin_interpretar": bandejas.sin_interpretar,
    "contactos": bandejas.contactos_pendientes, "dados_de_baja": bandejas.dados_de_baja,
}


class Bandeja(Entrada):
    bandeja: Literal["no_confirmadas", "seguimientos", "en_riesgo", "cupos_libres", "sin_desenlace", "sin_interpretar",
                     "contactos", "dados_de_baja"] = Field(description="Cuál lista de trabajo de recepción.")


@herramienta("bandeja", f"Una lista de trabajo de recepción (máximo {MAX_FILAS} filas): citas sin confirmar, seguimientos, pacientes en riesgo, "
             "cupos libres, citas sin desenlace, mensajes sin interpretar, solicitudes de contacto o pacientes dados de baja.",
             Bandeja, AUX, LECTURA)
def bandeja(conn, actor, a: Bandeja) -> dict:
    return {"bandeja": a.bandeja, **_limitar(BANDEJAS[a.bandeja](conn))}


def _tiempo_entre_citas(conn, f):
    return {"por_servicio": indicators.time_between(conn, f), "por_paciente_dias": indicators.time_between_patient(conn, f)}


REPORTES = {
    "resumen": indicators.summary, "tendencia": indicators.trend, "tendencia_semanal": indicators.weekly_trend,
    "por_profesional": lambda c, f: indicators.by_dimension(c, f, "profesional"),
    "por_servicio": lambda c, f: indicators.by_dimension(c, f, "servicio"),
    "motivos": indicators.reasons, "tiempo_entre_citas": _tiempo_entre_citas, "faltas_repetidas": indicators.repeat_no_shows,
    "citas_perdidas": lambda c, f: indicators.missed_appointments(c, f, limite=MAX_FILAS + 1),
    "recordatorios": indicators.reminders, "pendientes": indicators.pending_followthrough,
    "reagendamiento": indicators.rebooking, "dia_hora": indicators.weekday_hour,
}


class Indicadores(Entrada):
    reporte: Literal["resumen", "tendencia", "tendencia_semanal", "por_profesional", "por_servicio", "motivos",
                     "tiempo_entre_citas", "faltas_repetidas", "citas_perdidas", "recordatorios", "pendientes",
                     "reagendamiento", "dia_hora"] = Field(description="Cuál indicador del tablero.")
    desde: date = Field(description="Primer día del periodo (AAAA-MM-DD).")
    hasta: date = Field(description="Último día del periodo, inclusive.")
    profesional_id: int | None = Field(None, ge=1)
    servicio_id: int | None = Field(None, ge=1)


@herramienta("indicadores", "Indicadores del tablero de gestión de un periodo: inasistencia, asistencia, dinero perdido, motivos, "
             f"pendientes del equipo y más. Listas de máximo {MAX_FILAS} filas.", Indicadores, AUX, LECTURA)
def indicadores(conn, actor, a: Indicadores) -> dict:
    if a.hasta < a.desde:
        raise ErrorHerramienta("datos_invalidos", "La fecha final no puede ser anterior a la inicial.")
    if (a.hasta - a.desde).days > 731:
        raise ErrorHerramienta("datos_invalidos", "El periodo no puede pasar de dos años.")
    f = {"desde": a.desde, "hasta": a.hasta, "profesional_id": a.profesional_id, "servicio_id": a.servicio_id}
    datos = REPORTES[a.reporte](conn, f)
    return {"reporte": a.reporte, **(_limitar(datos) if isinstance(datos, list) else {"datos": datos})}


# ----------------------------------------------------------------- propuestas
# Una propuesta describe lo que la persona confirma; el cliente la ejecuta con el endpoint o formulario que ya existe,
# con sus propias validaciones. Aquí solo se valida, sin escribir, lo que se puede ver ahora.

def _espacio_libre(conn, profesional_id: int | None, servicio_id: int, inicio: datetime) -> None:
    ahora = clock.now(conn)
    if profesional_id:
        libre = inicio in agenda.day_slots(conn, profesional_id, servicio_id, inicio.date(), ahora)
    else:
        try:
            agenda.assign_professional(conn, servicio_id, inicio)  # solo lee; SlotTaken si nadie lo tiene
            libre = True
        except agenda.SlotTaken:
            libre = False
    if not libre:
        raise ErrorHerramienta("espacio_ocupado", "Ese espacio no está libre. Busca otro con `espacios_libres`.")


def _cita_con_nombres(conn, cita_id: int) -> dict:
    return conn.execute(
        "select c.*, pr.nombre as profesional, s.nombre as servicio, p.nombres || ' ' || p.apellidos as paciente "
        "from cita c join profesional pr on pr.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "join paciente p on p.id=c.paciente_id where c.id=%s", (cita_id,)).fetchone()


def _cita_del_hogar(conn, actor: Actor, cita_id: int) -> tuple[dict, dict]:
    """La cita viva y próxima de un miembro del hogar, tal como la lista «Mis citas»; cualquier otra es `no_existe`."""
    p = _paciente(conn, actor)
    c = conn.execute("select * from cita where id=%s and paciente_id = any(%s) and estado = any(%s) "
                     "and (rango is null or upper(rango) > %s)",
                     (cita_id, familia.ids_del_hogar(conn, p), list(ALIVE), clock.now(conn))).fetchone()
    if c is None:
        raise permisos.NoExiste("Esa cita ya no está vigente")
    return p, _cita_con_nombres(conn, c["id"])


def _de_quien(p: dict, c: dict) -> str:
    return "tu cita" if c["paciente_id"] == p["id"] else f"la cita de {familia.primer_nombre(c['paciente'])}"


def _cita_del_equipo(conn, actor: Actor, cita_id: int, accion: str) -> dict:
    """La cita dentro del alcance del usuario y con esa acción permitida hoy (`permisos.acciones_cita`)."""
    u = actor.usuario_de_alcance
    c = permisos.cita_visible(conn, u, cita_id)
    if accion not in permisos.acciones_cita(u, c["estado"], _inicio(c), clock.now(conn)):
        raise ErrorHerramienta("accion_no_permitida", f"Con la cita en estado {c['estado']} no se puede hacer eso ahora.")
    return _cita_con_nombres(conn, cita_id)


def _descripcion(c: dict) -> str:
    return f"{c['servicio']} de {c['paciente']} del {_cuando(_inicio(c))}" if c["rango"] else f"{c['servicio']} de {c['paciente']}"


class AgendarPaciente(Entrada):
    servicio_id: int = Field(ge=1)
    profesional_id: int | None = Field(None, ge=1, description="Sin él, cualquier especialista libre.")
    inicio: datetime = Field(description="Inicio de la cita, ISO 8601 (hora de Bogotá). Debe salir de `espacios_libres`.")
    para: int | None = Field(None, ge=1, description="Id de un familiar (de `mis_citas.hogar`). Sin él, quien pregunta.")


class AgendarEquipo(Entrada):
    paciente_id: int = Field(ge=1, description="Id del paciente (de `buscar_pacientes`).")
    servicio_id: int = Field(ge=1)
    profesional_id: int = Field(ge=1)
    inicio: datetime = Field(description="Inicio de la cita, ISO 8601 (hora de Bogotá). Debe salir de `espacios_libres`.")


@herramienta("proponer_agendar", "Prepara agendar una cita. No agenda: la persona debe confirmar. Antes revisa el espacio con `espacios_libres`.",
             AgendarEquipo, PAC + ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta", modelos={"paciente": AgendarPaciente})
def proponer_agendar(conn, actor, a) -> dict:
    inicio = _bogota(a.inicio)
    if actor.perfil == "paciente":
        s = familia.sujeto(conn, _paciente(conn, actor), a.para)
        srv = _servicio(conn, a.servicio_id, True)
        pro = _profesional(conn, a.profesional_id) if a.profesional_id else None
        _espacio_libre(conn, a.profesional_id, srv["id"], inicio)
        resumen = (f"Agendar {srv['nombre']} para {familia.primer_nombre(s)} el {_cuando(inicio)}"
                   + (f" con {pro['nombre']}." if pro else "."))
        # Los campos del formulario `POST /p/{token}/agendar`; `profesional` 0 es «cualquier especialista».
        return _propuesta("agendar", {"servicio": srv["id"], "profesional": a.profesional_id or 0, "inicio": _iso(inicio),
                                      "para": s["id"]}, resumen)
    p = conn.execute("select id, nombres, apellidos from paciente where id=%s", (a.paciente_id,)).fetchone()
    if p is None:
        raise permisos.NoExiste("No existe ese paciente")
    srv = _servicio(conn, a.servicio_id, False)
    pro = _profesional(conn, a.profesional_id)
    _espacio_libre(conn, pro["id"], srv["id"], inicio)
    # El cuerpo de `POST /citas`.
    return _propuesta("agendar", {"paciente_id": p["id"], "profesional_id": pro["id"], "servicio_id": srv["id"],
                                  "inicio": _iso(inicio)},
                      f"Agendar {srv['nombre']} para {_nombre(p)} el {_cuando(inicio)} con {pro['nombre']}.")


class CambiarFecha(Entrada):
    cita_id: int = Field(ge=1)
    inicio: datetime = Field(description="Nueva hora de inicio, ISO 8601 (hora de Bogotá). Debe salir de `espacios_libres`.")


@herramienta("proponer_cambiar_fecha", "Prepara cambiar la fecha de una cita, con el mismo profesional y servicio. No la cambia: "
             "la persona debe confirmar.", CambiarFecha, PAC + ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta")
def proponer_cambiar_fecha(conn, actor, a: CambiarFecha) -> dict:
    inicio = _bogota(a.inicio)
    if actor.perfil == "paciente":
        p, c = _cita_del_hogar(conn, actor, a.cita_id)
        sujeto = _de_quien(p, c)
    else:
        c = _cita_del_equipo(conn, actor, a.cita_id, "cambiar_fecha")
        sujeto = f"la cita de {c['paciente']}"
    _espacio_libre(conn, c["profesional_id"], c["servicio_id"], inicio)
    actual = f" del {_cuando(_inicio(c))}" if c["rango"] else ""
    # `POST /p/{token}/cambiar/{cita_id}` y `POST /citas/{cita_id}/cambiar-fecha`: el id va en la ruta y la hora en el cuerpo.
    return _propuesta("cambiar_fecha", {"cita_id": c["id"], "inicio": _iso(inicio)},
                      f"Cambiar {sujeto} de {c['servicio']}{actual} al {_cuando(inicio)}.")


class CancelarPaciente(Entrada):
    cita_id: int = Field(ge=1)


class CancelarEquipo(CancelarPaciente):
    motivo_id: int = Field(ge=1, description="Id del motivo de cancelación.")
    texto: str | None = Field(None, max_length=300, description="Detalle opcional.")


@herramienta("proponer_cancelar", "Prepara cancelar una cita. No la cancela: la persona debe confirmar.", CancelarEquipo,
             PAC + ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta", modelos={"paciente": CancelarPaciente})
def proponer_cancelar(conn, actor, a) -> dict:
    if actor.perfil == "paciente":
        p, c = _cita_del_hogar(conn, actor, a.cita_id)
        # La pantalla `/p/{token}/cancelar/{cita_id}` pide el motivo: solo hace falta el id.
        return _propuesta("cancelar", {"cita_id": c["id"]}, f"Cancelar {_de_quien(p, c)} de {c['servicio']}"
                          + (f" del {_cuando(_inicio(c))}." if c["rango"] else "."))
    c = _cita_del_equipo(conn, actor, a.cita_id, "cancelar")
    m = conn.execute("select etiqueta from motivo_cancelacion where id=%s", (a.motivo_id,)).fetchone()
    if m is None:
        raise permisos.NoExiste("No existe ese motivo")
    # El cuerpo de `POST /citas/{cita_id}/cancelar`.
    return _propuesta("cancelar", {"cita_id": c["id"], "motivo_id": a.motivo_id, "texto": a.texto},
                      f"Cancelar la cita de {_descripcion(c)} (motivo: {m['etiqueta']}).")


@herramienta("proponer_confirmar_telefono", "Prepara registrar que el paciente confirmó su cita por teléfono. No la confirma: "
             "recepción debe confirmar.", CitaId, ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta")
def proponer_confirmar_telefono(conn, actor, a: CitaId) -> dict:
    c = _cita_del_equipo(conn, actor, a.cita_id, "confirmar")
    return _propuesta("confirmar_telefono", {"cita_id": c["id"]},  # `POST /citas/{cita_id}/confirmar`
                      f"Registrar que {c['paciente']} confirmó por teléfono su cita de {_descripcion(c)}.")


class DesenlaceCita(CitaId):
    desenlace: Literal["atendida", "no_asistio"] = Field(description="Si el paciente fue atendido o no asistió.")


@herramienta("proponer_desenlace", "Prepara registrar si el paciente fue atendido o no asistió. Solo desde la hora de inicio de la cita. "
             "No lo registra: la persona debe confirmar. El especialista solo con sus citas.", DesenlaceCita,
             ESP + ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta")
def proponer_desenlace(conn, actor, a: DesenlaceCita) -> dict:
    c = _cita_del_equipo(conn, actor, a.cita_id, "desenlace")
    dijo = "fue atendido" if a.desenlace == "atendida" else "no asistió"
    return _propuesta("desenlace", {"cita_id": c["id"], "desenlace": a.desenlace},  # `POST /citas/{cita_id}/desenlace`
                      f"Registrar que {c['paciente']} {dijo} a su cita de {_descripcion(c)}.")


class BloqueoPropio(Entrada):
    inicio: datetime = Field(description="Inicio del bloqueo, ISO 8601 (hora de Bogotá).")
    fin: datetime = Field(description="Fin del bloqueo, ISO 8601 (hora de Bogotá). Debe ser posterior al inicio y futuro.")
    motivo: str = Field("", max_length=200)


class BloqueoDe(BloqueoPropio):
    profesional_id: int = Field(ge=1, description="Id del profesional cuya agenda se bloquea.")


@herramienta("proponer_bloqueo", "Prepara bloquear la agenda de un profesional entre dos horas. No la bloquea: la persona debe confirmar. "
             "Se rechaza si cruza citas vivas. El especialista solo bloquea la suya.", BloqueoDe, ESP + ("auxiliar",), PROPUESTA,
             auditoria="asistente:propuesta", modelos={"especialista": BloqueoPropio})
def proponer_bloqueo(conn, actor, a) -> dict:
    u = actor.usuario
    pro_id = _profesional_propio(u) if actor.perfil == "especialista" else a.profesional_id
    permisos.exigir_profesional(u, pro_id)
    pro = _profesional(conn, pro_id)
    inicio, fin = _bogota(a.inicio), _bogota(a.fin)
    if fin <= inicio:
        raise ErrorHerramienta("datos_invalidos", "El fin del bloqueo debe ser posterior al inicio.")
    if fin <= clock.now(conn):
        raise ErrorHerramienta("datos_invalidos", "El bloqueo debe terminar en el futuro.")
    cruzadas = horario.conflicting_appointments(conn, pro["id"], Range(inicio, fin, "[)"))
    if cruzadas:
        raise ErrorHerramienta("accion_no_permitida", f"Ese rango se cruza con {len(cruzadas)} cita(s) viva(s) "
                               f"(ids {', '.join(str(x['id']) for x in cruzadas[:10])}): hay que moverlas antes.")
    motivo = a.motivo.strip()
    return _propuesta("bloqueo", {"profesional_id": pro["id"], "inicio": _iso(inicio), "fin": _iso(fin), "motivo": motivo},  # `POST /bloqueos`
                      f"Bloquear la agenda de {pro['nombre']} desde el {_cuando(inicio)} hasta el {_cuando(fin)}"
                      + (f" (motivo: {motivo})." if motivo else "."))


@herramienta("pedir_contacto", "Prepara pedir que la clínica contacte a quien pregunta. No la avisa: la persona debe confirmar.",
             SinEntrada, PAC, PROPUESTA, auditoria="asistente:propuesta")
def pedir_contacto(conn, actor, a) -> dict:
    _paciente(conn, actor)
    termino = config.get(conn, "termino_negocio")
    # `POST /p/{token}/contacto` (PRD §7): no necesita campos.
    return _propuesta("contacto", {}, f"Pedir que {termino} te contacte.")
