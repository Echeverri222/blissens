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
from ..pacientes import DatosInvalidos
from .actor import Actor
from .base import LECTURA, PROPUESTA, Entrada, ErrorHerramienta, herramienta

PAC = ("paciente",)
VIS = ("visitante",)  # quien escribe desde el sitio público: anónimo, solo lecturas del catálogo público y tarjetas con formulario
WEB = PAC + VIS       # perfiles que solo ven lo que la página de agendar ofrece (servicios autoagendables, sin valor)
ESP = ("especialista",)
AUX = ("auxiliar", "operador")  # el operador local ve lo mismo que la auxiliar, solo lectura
MAX_DIAS_AGENDA = 42
MAX_FILAS = 50
MAX_FILAS_BANDEJA = 15  # ya vienen en orden de prioridad; con el total, el modelo sabe cuántas quedan
MAX_ESPACIOS = 12
MAX_CITAS_PACIENTE = 20
MAX_HISTORIAL = 10


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
    ini = b["rango"].lower
    return {"id": b["id"], "profesional_id": b["profesional_id"], "inicio": ini, "fin": b["rango"].upper,
            "dia": fmt.DIAS[ini.astimezone(clock.TZ).weekday()], "motivo": b["motivo"]}


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
             WEB + ("especialista", "auxiliar", "operador"), LECTURA)
def servicios(conn, actor, a) -> dict:
    # El paciente y el visitante solo ven lo que la página de agendar ofrece; el valor del servicio nunca sale (es un promedio interno).
    filas = conn.execute("select id, nombre, duracion_min, autoagendable from servicio where activo "
                         + ("and autoagendable " if actor.perfil in WEB else "") + "order by id").fetchall()
    quitar = ("autoagendable",) if actor.perfil in WEB else ()
    return {"servicios": [{k: v for k, v in f.items() if k not in quitar} for f in filas]}


class EspaciosLibres(Entrada):
    servicio_id: int | None = Field(None, ge=1, description="El servicio a agendar. Para cambiar la fecha de una cita usa `cita_id`.")
    cita_id: int | None = Field(None, ge=1, description="Para cambiar la fecha de una cita: busca con su servicio y su profesional.")
    profesional_id: int | None = Field(None, ge=1, description="Sin él, se ofrecen las horas de cualquier especialista.")
    desde: date | None = Field(None, description="Primer día a mostrar (AAAA-MM-DD). Por defecto, hoy.")
    dias: int = Field(14, ge=1, le=60, description="Cuántos días hacia adelante buscar.")


class EspaciosLibresVisitante(Entrada):
    """Sin `cita_id`: un visitante no tiene citas que cambiar."""
    servicio_id: int = Field(ge=1, description="El servicio a agendar (de `servicios`).")
    profesional_id: int | None = Field(None, ge=1, description="Sin él, se ofrecen las horas de cualquier especialista.")
    desde: date | None = Field(None, description="Primer día a mostrar (AAAA-MM-DD). Por defecto, hoy.")
    dias: int = Field(14, ge=1, le=60, description="Cuántos días hacia adelante buscar.")


def _cita_para_cambiar(conn, actor: Actor, cita_id: int) -> dict:
    """La cita cuyo cambio de fecha se busca: del hogar para el paciente, del alcance del usuario para el equipo."""
    if actor.perfil == "paciente":
        return _cita_del_hogar(conn, actor, cita_id)[1]
    permisos.cita_visible(conn, actor.usuario_de_alcance, cita_id)
    c = _cita_con_nombres(conn, cita_id)
    if c["estado"] not in ALIVE:
        raise ErrorHerramienta("accion_no_permitida", f"La cita está en estado {c['estado']}: no se le puede cambiar la fecha.")
    return c


@herramienta("espacios_libres", f"Horas libres para agendar un servicio, con un profesional o con cualquiera (cada hora dice con quién). "
             f"Para cambiar la fecha de una cita, pasa `cita_id`: busca con su servicio y su profesional. Máximo {MAX_ESPACIOS} "
             "por llamada, en orden. Usa `desde` para ver más adelante.", EspaciosLibres, WEB + ("auxiliar", "operador"), LECTURA,
             modelos={"visitante": EspaciosLibresVisitante})
def espacios_libres(conn, actor, a: EspaciosLibres) -> dict:
    if getattr(a, "cita_id", None):
        # El servicio de una cita propia vale aunque no sea autoagendable: «Mis citas» deja cambiarle la fecha igual.
        c = _cita_para_cambiar(conn, actor, a.cita_id)
        srv = _servicio(conn, c["servicio_id"], False)
        pro = _profesional(conn, c["profesional_id"])
    elif a.servicio_id:
        srv = _servicio(conn, a.servicio_id, actor.perfil in WEB)
        pro = _profesional(conn, a.profesional_id) if a.profesional_id else None
    else:
        raise ErrorHerramienta("datos_invalidos", "Indica `servicio_id` o, para cambiar la fecha de una cita, `cita_id`.")
    hoy = clock.now(conn).date()
    dias = min(90, (max(a.desde, hoy) - hoy).days + a.dias) if a.desde else a.dias
    por_dia = (agenda.available_slots(conn, pro["id"], srv["id"], days=dias) if pro
               else agenda.any_slots(conn, srv["id"], days=dias))
    horas = [h for d, hs in por_dia.items() if not a.desde or d >= a.desde for h in hs]
    espacios = []
    for h in horas[:MAX_ESPACIOS]:
        e = {"inicio": h, "cuando": _cuando(h)}
        if pro is None:  # con quién quedaría (la misma regla que al agendar con «cualquiera»); el equipo lo necesita para agendar
            try:
                quien = _profesional(conn, agenda.assign_professional(conn, srv["id"], h))
            except agenda.SlotTaken:
                continue
            e.update(profesional_id=quien["id"], profesional=quien["nombre"])
        espacios.append(e)
    return {"servicio": srv["nombre"], "duracion_min": srv["duracion_min"], "profesional": pro["nombre"] if pro else "cualquiera",
            **({"profesional_id": pro["id"]} if pro else {}), "espacios": espacios, "hay_mas": len(horas) > MAX_ESPACIOS}


def _juntar(franjas: list[tuple]) -> list[tuple]:
    """Une franjas que se tocan o se cruzan: el horario del negocio es la unión del de sus profesionales."""
    out: list[list] = []
    for desde, hasta in sorted(franjas):
        if out and desde <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hasta)
        else:
            out.append([desde, hasta])
    return [tuple(x) for x in out]


@herramienta("datos_del_negocio", "Nombre y dirección del negocio, su horario de atención por día de la semana (con sus franjas: "
             "si cierra al mediodía, son dos) y sus profesionales con su id.", SinEntrada,
             WEB + ("especialista", "auxiliar", "operador"), LECTURA)
def datos_del_negocio(conn, actor, a) -> dict:
    n = conn.execute("select nombre from negocio where id=%s", (actor.negocio_id,)).fetchone()
    filas = conn.execute(
        "select distinct h.dia_semana, h.desde, h.hasta from horario_atencion h "
        "join profesional p on p.id=h.profesional_id where p.activo order by 1, 2").fetchall()
    dias: dict[int, list] = {}
    for f in filas:
        dias.setdefault(f["dia_semana"], []).append((f["desde"], f["hasta"]))
    pros = conn.execute("select id, nombre, especialidad from profesional where activo order by nombre").fetchall()
    return {"nombre": n["nombre"] if n else None, "direccion": config.get(conn, "direccion"),
            "horario": [{"dia": fmt.DIAS[d], "franjas": [{"desde": x, "hasta": y} for x, y in _juntar(fr)]}
                        for d, fr in sorted(dias.items())],
            "dias_sin_atencion": [fmt.DIAS[d] for d in range(7) if d not in dias],
            "profesionales": [dict(p) for p in pros]}


@herramienta("motivos_cancelacion", "Los motivos de cancelación con su id (`proponer_cancelar` pide uno).", SinEntrada, AUX, LECTURA)
def motivos_cancelacion(conn, actor, a) -> dict:
    return {"motivos": conn.execute("select id, etiqueta from motivo_cancelacion order by orden").fetchall()}


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


class MiDia(Entrada):
    dia: date | None = Field(None, description="El día (AAAA-MM-DD). Por defecto, hoy.")


MIN_HUECO = 15  # minutos: un hueco más corto no sirve para ninguna cita


def _restar(franja: tuple, ocupados: list[tuple]) -> list[tuple]:
    """Lo que queda libre de una franja tras quitarle los rangos ocupados."""
    libres, ini, fin = [], *franja
    for a, b in sorted(ocupados):
        if b <= ini or a >= fin:
            continue
        if a > ini:
            libres.append((ini, a))
        ini = max(ini, b)
    if ini < fin:
        libres.append((ini, fin))
    return [(a, b) for a, b in libres if (b - a).total_seconds() >= MIN_HUECO * 60]


@herramienta("mi_dia", "Tu día de un vistazo: cuántas citas por estado, la que sigue (o la que está en curso), las que ya "
             "empezaron y siguen sin desenlace, tus huecos libres y tus bloqueos. Solo lo tuyo.", MiDia, ESP, LECTURA)
def mi_dia(conn, actor, a: MiDia) -> dict:
    pro = _profesional_propio(actor.usuario)
    ahora = clock.now(conn)
    dia = a.dia or ahora.date()
    r = agenda.range_agenda(conn, dia, dia, pro)
    citas = [c for c in r["citas"] if c["estado"] != "cancelada"]
    conteo: dict[str, int] = {}
    for c in citas:
        conteo[c["estado"]] = conteo.get(c["estado"], 0) + 1
    vivas = [c for c in citas if c["estado"] in ALIVE]
    en_curso = next((c for c in vivas if _inicio(c) <= ahora < _fin(c)), None)
    siguiente = next((c for c in vivas if _inicio(c) > ahora), None)
    ocupados = [(_inicio(c), _fin(c)) for c in citas] + [(b["rango"].lower, b["rango"].upper) for b in r["bloqueos"]]
    huecos = []
    for f in r["franjas"]:
        franja = (max(f["inicio"], ahora), f["fin"]) if dia == ahora.date() else (f["inicio"], f["fin"])
        if franja[0] < franja[1]:
            huecos += [{"desde": x, "hasta": y} for x, y in _restar(franja, ocupados)]

    def corta(c):
        return {"id": c["id"], "inicio": _inicio(c), "servicio": c["servicio"], "paciente": c["paciente"], "estado": c["estado"]}

    return {"dia": dia, "dia_semana": fmt.DIAS[dia.weekday()], "total": len(citas), "por_estado": conteo,
            "en_curso": corta(en_curso) if en_curso else None, "siguiente": corta(siguiente) if siguiente else None,
            "quedan_por_empezar": sum(1 for c in vivas if _inicio(c) > ahora),
            "sin_desenlace": [corta(c) for c in vivas if _inicio(c) <= ahora],
            "citas": [corta(c) for c in citas], "huecos_libres": huecos, "bloqueos": [_bloqueo(b) for b in r["bloqueos"]]}


DIAS_SIN_DESENLACE = 30


@herramienta("citas_sin_desenlace", f"Tus citas que ya empezaron y siguen sin registrar si el paciente fue atendido o no asistió, de "
             f"los últimos {DIAS_SIN_DESENLACE} días (máximo {MAX_FILAS}). Solo las tuyas.", SinEntrada, ESP, LECTURA)
def citas_sin_desenlace(conn, actor, a) -> dict:
    pro = _profesional_propio(actor.usuario)
    ahora = clock.now(conn)
    filas = conn.execute(
        "select c.id, c.estado, c.rango, s.nombre as servicio, p.nombres || ' ' || p.apellidos as paciente from cita c "
        "join servicio s on s.id=c.servicio_id join paciente p on p.id=c.paciente_id "
        "where c.profesional_id=%s and c.estado = any(%s) and c.rango is not null and lower(c.rango) <= %s "
        "and lower(c.rango) >= %s order by lower(c.rango) limit %s",
        (pro, list(ALIVE), ahora, ahora - timedelta(days=DIAS_SIN_DESENLACE), MAX_FILAS + 1)).fetchall()
    return {"desde_hace_dias": DIAS_SIN_DESENLACE, **_limitar(
        [{"id": c["id"], "inicio": _inicio(c), "cuando": _cuando(_inicio(c)), "servicio": c["servicio"],
          "paciente": c["paciente"], "estado": c["estado"]} for c in filas])}


# ----------------------------------------------------------------- pacientes y bandejas (auxiliar)

class BuscarPacientes(Entrada):
    q: str = Field(min_length=1, max_length=80, description="Parte del nombre, apellido, documento o celular.")


@herramienta("buscar_pacientes", "Busca pacientes por nombre, documento, celular o correo. Máximo 10: id, nombre, últimos 4 dígitos del documento y etapa (`prospecto`: escribió desde el sitio y aún no tiene documento; `paciente`).",
             BuscarPacientes, AUX, LECTURA, auditoria="buscar_paciente")
def buscar_pacientes(conn, actor, a: BuscarPacientes) -> dict:
    filas = bandejas.find_patients(conn, a.q)
    return {"pacientes": [{"id": f["id"], "nombre": _nombre(f), "documento_ultimos4": _ultimos4(f["documento"]),
                           "etapa": f["etapa"]} for f in filas[:10]], "hay_mas": len(filas) > 10}


class PacienteId(Entrada):
    paciente_id: int = Field(ge=1, description="Id del paciente (sale de `buscar_pacientes`).")


@herramienta("ficha_paciente", "Resumen de un paciente: nombre, últimos 4 del documento, etapa (prospecto o paciente), consentimientos, sus últimas 20 citas, "
             "casos de seguimiento abiertos y sus últimos 10 mensajes. Sin teléfono, correo ni fecha de nacimiento.",
             PacienteId, AUX, LECTURA, auditoria="ver_ficha")
def ficha_paciente(conn, actor, a: PacienteId) -> dict:
    if not conn.execute("select 1 from paciente where id=%s", (a.paciente_id,)).fetchone():
        raise permisos.NoExiste("No existe ese paciente")
    r = bandejas.patient_record(conn, a.paciente_id)
    p = r["paciente"]
    estados = {c["id"]: c["estado"] for c in r["citas"]}
    return {
        "paciente": {"id": p["id"], "nombre": _nombre(p), "documento_ultimos4": _ultimos4(p["documento"]),
                     "etapa": p["etapa"], "acepta_mensajes": p["acepta_mensajes"], "acepta_correo": p["acepta_correo"]},
        "citas": [{"id": c["id"], "estado": c["estado"], "dia": c["dia"], "inicio": _inicio(c), "servicio": c["servicio"],
                   "profesional": c["profesional"]} for c in r["citas"][:20]],
        "casos_abiertos": [{"id": c["id"], "tipo": c["tipo"], "escalado": c["escalado"], "abierto_en": c["abierto_en"],
                            "intentos": len(c["intentos"] or [])} for c in r["casos"] if c["estado"] == "abierto"],
        # Los últimos movimientos de estado, con su id para `proponer_revertir` (la ficha del panel muestra el mismo botón).
        "historial": [{"id": h["id"], "cita_id": h["cita_id"], "momento": h["momento"], "de": h["estado_anterior"],
                       "a": h["estado_nuevo"], "revertido": h["revertido"],
                       "reversible": permisos.puede_revertir(actor.usuario_de_alcance, h, estados[h["cita_id"]])}
                      for h in r["historial"][:MAX_HISTORIAL]],
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


@herramienta("bandeja", f"Una lista de trabajo de recepción, en orden de prioridad (las {MAX_FILAS_BANDEJA} primeras y el total): citas sin confirmar, seguimientos, pacientes en riesgo, "
             "cupos libres, citas sin desenlace, mensajes sin interpretar, solicitudes de contacto o pacientes dados de baja.",
             Bandeja, AUX, LECTURA)
def bandeja(conn, actor, a: Bandeja) -> dict:
    filas = BANDEJAS[a.bandeja](conn)
    if a.bandeja == "contactos":
        filas = [_contacto(conn, f) for f in filas]
    elif a.bandeja == "dados_de_baja":  # a quién hay que llamar: el número completo está en el panel, aquí sus últimos 4
        filas = [{**f, "celular_ultimos4": _ultimos4(f["celular"])} for f in filas]
    return {"bandeja": a.bandeja, **_limitar([_compacta(f) for f in filas], MAX_FILAS_BANDEJA)}


def _compacta(f: dict) -> dict:
    """Una fila de bandeja sin lo que no dice nada (campos vacíos o en falso) y con la hora al minuto: cada fila viaja al
    modelo en cada vuelta, y en una bandeja larga eso es la mayor parte de lo que se paga."""
    out = {}
    for k, v in f.items():
        if v is None or v is False:
            continue
        out[k] = v.strftime("%Y-%m-%dT%H:%M") if isinstance(v, datetime) else v
    return out


def _contacto(conn, f: dict) -> dict:
    """Una solicitud de contacto que recepción pueda reconocer: sin documento ni celular completos (se quitan a la salida),
    con sus últimos 4 y, si el documento es de un paciente, quién es."""
    p = conn.execute("select id, nombres, apellidos from paciente where id=%s", (f["paciente_id"],)).fetchone() \
        if f.get("paciente_id") else conn.execute("select id, nombres, apellidos from paciente where documento=%s",
                                                  (f["documento"],)).fetchone()
    return {"id": f["id"], "momento": f["momento"], "nota": f["nota"], "documento_ultimos4": _ultimos4(f["documento"]),
            "celular_ultimos4": _ultimos4(f["celular"]),
            "paciente": {"id": p["id"], "nombre": _nombre(p)} if p else None}


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

def _espacio_libre(conn, profesional_id: int | None, servicio_id: int, inicio: datetime, duracion_min: int | None = None) -> None:
    ahora = clock.now(conn)
    if profesional_id:
        libre = inicio in agenda.day_slots(conn, profesional_id, servicio_id, inicio.date(), ahora, duracion_min)
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
    duracion_min: int | None = Field(None, ge=15, le=240, description="Minutos de esta cita (15 a 240, de 15 en 15) si no es "
                                     "la del servicio. Sin él, la del servicio.")


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
    try:
        agenda.validar_duracion(a.duracion_min)
    except DatosInvalidos as e:
        raise ErrorHerramienta("datos_invalidos", str(e)) from None
    _espacio_libre(conn, pro["id"], srv["id"], inicio, a.duracion_min)
    # El cuerpo de `POST /citas`.
    parametros = {"paciente_id": p["id"], "profesional_id": pro["id"], "servicio_id": srv["id"], "inicio": _iso(inicio)}
    duracion = f" ({a.duracion_min} min)" if a.duracion_min else ""
    if a.duracion_min:
        parametros["duracion_min"] = a.duracion_min
    return _propuesta("agendar", parametros,
                      f"Agendar {srv['nombre']}{duracion} para {_nombre(p)} el {_cuando(inicio)} con {pro['nombre']}.")


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


@herramienta("proponer_confirmar", "Prepara confirmar que la persona (o su familiar) asistirá a una cita próxima. No la confirma: "
             "la persona debe tocar el botón.", CancelarPaciente, PAC, PROPUESTA, auditoria="asistente:propuesta")
def proponer_confirmar(conn, actor, a: CancelarPaciente) -> dict:
    p, c = _cita_del_hogar(conn, actor, a.cita_id)
    if c["estado"] == "confirmada":
        raise ErrorHerramienta("accion_no_permitida", "Esa cita ya está confirmada.")
    if not c["rango"] or _inicio(c) <= clock.now(conn):
        raise ErrorHerramienta("accion_no_permitida", "Esa cita ya empezó o no tiene hora: no se puede confirmar.")
    # `POST /p/{token}/confirmar/{cita_id}`: el mismo paso que el botón «Sí, asistiré» del recordatorio.
    return _propuesta("confirmar", {"cita_id": c["id"]},
                      f"Confirmar que asistirás a {_de_quien(p, c)} de {c['servicio']} del {_cuando(_inicio(c))}."
                      if c["paciente_id"] == p["id"] else
                      f"Confirmar {_de_quien(p, c)} de {c['servicio']} del {_cuando(_inicio(c))}.")


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


class BloqueoId(Entrada):
    bloqueo_id: int = Field(ge=1, description="Id del bloqueo (sale de `agenda`).")


@herramienta("proponer_eliminar_bloqueo", "Prepara eliminar un bloqueo de agenda que aún no terminó. No lo elimina: la persona "
             "debe confirmar.", BloqueoId, ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta")
def proponer_eliminar_bloqueo(conn, actor, a: BloqueoId) -> dict:
    b = horario.get_block(conn, a.bloqueo_id)
    if b is None:
        raise permisos.NoExiste("No existe ese bloqueo")
    permisos.exigir_profesional(actor.usuario, b["profesional_id"])
    if b["rango"].upper <= clock.now(conn):
        raise ErrorHerramienta("accion_no_permitida", "Ese bloqueo ya terminó: no se puede eliminar.")
    pro = conn.execute("select nombre from profesional where id=%s", (b["profesional_id"],)).fetchone()
    return _propuesta("eliminar_bloqueo", {"bloqueo_id": b["id"]},  # `DELETE /bloqueos/{bloqueo_id}`
                      f"Eliminar el bloqueo de {pro['nombre']} del {_cuando(b['rango'].lower)} al {_cuando(b['rango'].upper)}.")


class NuevoPaciente(Entrada):
    nombres: str = Field(min_length=1, max_length=100)
    apellidos: str = Field("", max_length=100)


@herramienta("proponer_crear_paciente", "Prepara crear un paciente nuevo con su nombre. El documento, el celular y la "
             "autorización de datos los escribe la persona en la tarjeta, nunca en el chat. Antes revisa con `buscar_pacientes` "
             "que no exista.", NuevoPaciente, ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta")
def proponer_crear_paciente(conn, actor, a: NuevoPaciente) -> dict:
    # Sin documento ni celular: esos datos no pasan por el modelo (P5). La tarjeta los pide y llama a `POST /pacientes`.
    return _propuesta("crear_paciente", {"nombres": a.nombres, "apellidos": a.apellidos},
                      f"Crear el paciente {a.nombres} {a.apellidos}".strip() + ".")


class SegmentosPaciente(PacienteId):
    internacional: bool = Field(description="Paciente internacional.")
    deportista: bool = Field(description="Deportista de alto nivel.")


@herramienta("proponer_segmentos", "Prepara marcar o desmarcar a un paciente como internacional o deportista de alto nivel "
             "(los dos valores, como deben quedar). No lo marca: la persona debe confirmar.", SegmentosPaciente, ("auxiliar",),
             PROPUESTA, auditoria="asistente:propuesta")
def proponer_segmentos(conn, actor, a: SegmentosPaciente) -> dict:
    p = conn.execute("select id, nombres, apellidos from paciente where id=%s", (a.paciente_id,)).fetchone()
    if p is None:
        raise permisos.NoExiste("No existe ese paciente")
    marcas = [n for n, v in (("internacional", a.internacional), ("deportista de alto nivel", a.deportista)) if v]
    return _propuesta("segmentos", {"paciente_id": p["id"], "internacional": a.internacional, "deportista": a.deportista},
                      f"Dejar a {_nombre(p)} como " + (" y ".join(marcas) if marcas else "sin marcas de alto valor") + ".")


class GestionSeguimiento(Entrada):
    caso_id: int = Field(ge=1, description="Id del caso (de `bandeja` seguimientos o de `ficha_paciente`).")
    resultado: Literal["acepto", "rechazo", "sin_respuesta"] = Field(description="Cómo terminó la llamada.")
    detalle: str = Field("", max_length=300)


RESULTADOS = {"acepto": "aceptó", "rechazo": "no quiso", "sin_respuesta": "no contestó"}


@herramienta("proponer_gestion_seguimiento", "Prepara registrar la llamada de un seguimiento: si el paciente aceptó, no quiso o "
             "no contestó. No la registra: la persona debe confirmar.", GestionSeguimiento, ("auxiliar",), PROPUESTA,
             auditoria="asistente:propuesta")
def proponer_gestion_seguimiento(conn, actor, a: GestionSeguimiento) -> dict:
    c = conn.execute("select cs.id, cs.estado, cs.tipo, p.nombres, p.apellidos from caso_seguimiento cs "
                     "join paciente p on p.id=cs.paciente_id where cs.id=%s", (a.caso_id,)).fetchone()
    if c is None:
        raise permisos.NoExiste("No existe ese seguimiento")
    if c["estado"] not in ("abierto", "agotado"):
        raise ErrorHerramienta("accion_no_permitida", "Ese seguimiento ya está cerrado.")
    detalle = a.detalle.strip()
    return _propuesta("gestion_seguimiento", {"caso_id": c["id"], "resultado": a.resultado, "detalle": detalle},
                      f"Registrar que {_nombre(c)} {RESULTADOS[a.resultado]} en el seguimiento ({c['tipo']})"
                      + (f": {detalle}." if detalle else "."))


class MensajeId(Entrada):
    mensaje_id: int = Field(ge=1, description="Id del mensaje (de `bandeja` sin_interpretar).")


@herramienta("proponer_gestionar_mensaje", "Prepara marcar como gestionado un mensaje entrante sin interpretar. No lo marca: la "
             "persona debe confirmar.", MensajeId, ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta")
def proponer_gestionar_mensaje(conn, actor, a: MensajeId) -> dict:
    m = conn.execute("select m.id, m.gestionado, p.nombres, p.apellidos from mensaje m join paciente p on p.id=m.paciente_id "
                     "where m.id=%s and m.direccion='entrante'", (a.mensaje_id,)).fetchone()
    if m is None:
        raise permisos.NoExiste("No existe ese mensaje")
    if m["gestionado"]:
        raise ErrorHerramienta("accion_no_permitida", "Ese mensaje ya está gestionado.")
    return _propuesta("gestionar_mensaje", {"mensaje_id": m["id"]},  # `POST /mensajes/{mensaje_id}/gestionar`
                      f"Marcar como gestionado el mensaje de {_nombre(m)}.")


class SolicitudId(Entrada):
    solicitud_id: int = Field(ge=1, description="Id de la solicitud (de `bandeja` contactos).")


def _solicitud(conn, solicitud_id: int) -> dict:
    s = conn.execute("select id, gestionada, nombre from solicitud_contacto where id=%s", (solicitud_id,)).fetchone()
    if s is None:
        raise permisos.NoExiste("No existe esa solicitud")
    return s


@herramienta("proponer_gestionar_contacto", "Prepara marcar como gestionada una solicitud de contacto. No la marca: la persona "
             "debe confirmar.", SolicitudId, ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta")
def proponer_gestionar_contacto(conn, actor, a: SolicitudId) -> dict:
    s = _solicitud(conn, a.solicitud_id)
    if s["gestionada"]:
        raise ErrorHerramienta("accion_no_permitida", "Esa solicitud ya está gestionada.")
    return _propuesta("gestionar_contacto", {"solicitud_id": s["id"]},  # `POST /contactos/{solicitud_id}/gestionar`
                      "Marcar como gestionada la solicitud de contacto" + (f" de {s['nombre']}." if s["nombre"] else "."))


class VincularContacto(SolicitudId):
    paciente_id: int = Field(ge=1, description="Id del paciente (de `buscar_pacientes`).")


@herramienta("proponer_vincular_contacto", "Prepara vincular una solicitud de contacto del sitio web a un paciente. No la "
             "vincula: la persona debe confirmar.", VincularContacto, ("auxiliar",), PROPUESTA, auditoria="asistente:propuesta")
def proponer_vincular_contacto(conn, actor, a: VincularContacto) -> dict:
    s = _solicitud(conn, a.solicitud_id)
    p = conn.execute("select id, nombres, apellidos from paciente where id=%s", (a.paciente_id,)).fetchone()
    if p is None:
        raise permisos.NoExiste("No existe ese paciente")
    return _propuesta("vincular_contacto", {"solicitud_id": s["id"], "paciente_id": p["id"]},  # `POST /contactos/{id}/paciente`
                      "Vincular la solicitud de contacto" + (f" de {s['nombre']}" if s["nombre"] else "") + f" a {_nombre(p)}.")


class HistorialId(Entrada):
    historial_id: int = Field(ge=1, description="Id del movimiento (de `ficha_paciente.historial`, con `reversible`).")


@herramienta("proponer_revertir", "Prepara deshacer el último movimiento de estado de una cita (una cancelación, un cambio de "
             "fecha, un desenlace...). No lo deshace: la persona debe confirmar.", HistorialId, ("auxiliar",), PROPUESTA,
             auditoria="asistente:propuesta")
def proponer_revertir(conn, actor, a: HistorialId) -> dict:
    h = conn.execute("select h.id, h.cita_id, h.estado_anterior, h.estado_nuevo, h.revierte_id, "
                     "exists(select 1 from historial_estado r where r.revierte_id=h.id) as revertido "
                     "from historial_estado h where h.id=%s", (a.historial_id,)).fetchone()
    if h is None:
        raise permisos.NoExiste("No existe ese movimiento")
    c = permisos.cita_visible(conn, actor.usuario, h["cita_id"])
    if not permisos.puede_revertir(actor.usuario, h, c["estado"]):
        raise ErrorHerramienta("accion_no_permitida", "Ese movimiento no se puede deshacer: solo el último de la cita, si no se "
                               "deshizo ya.")
    c = _cita_con_nombres(conn, h["cita_id"])
    return _propuesta("revertir", {"historial_id": h["id"]},  # `POST /historial/{historial_id}/revertir`
                      f"Deshacer el paso de {h['estado_anterior']} a {h['estado_nuevo']} en la cita de {_descripcion(c)}.")


@herramienta("pedir_contacto","Prepara pedir que la clínica contacte a quien pregunta. No la avisa: la persona debe confirmar.",
             SinEntrada, PAC, PROPUESTA, auditoria="asistente:propuesta")
def pedir_contacto(conn, actor, a) -> dict:
    _paciente(conn, actor)
    termino = config.get(conn, "termino_negocio")
    # `POST /p/{token}/contacto` (PRD §7): no necesita campos.
    return _propuesta("contacto", {}, f"Pedir que {termino} te contacte.")


# ----------------------------------------------------------------- sitio público (perfil visitante)

class InfoClinica(Entrada):
    idioma: Literal["es", "en"] = Field("es", description="El idioma de la página: `es` o `en`.")


@herramienta("info_clinica", "Texto fijo de la clínica, el mismo del sitio web: qué hace cada servicio, la evaluación virtual, las "
             "experiencias (paquetes de viaje), la atención a pacientes internacionales y el equipo. En el idioma pedido.",
             InfoClinica, VIS, LECTURA)
def info_clinica(conn, actor, a: InfoClinica) -> dict:
    from ..web import copia  # texto estático: no toca la base
    t = copia.COPIA[a.idioma]
    return {"servicios": [{"nombre": n, "descripcion": d} for n, d in t["servicios"]["lista"]],
            "diseno_de_sonrisa": t["servicios"]["texto"],
            "evaluacion_virtual": {"texto": t["evaluacion"]["texto"], "pasos": list(t["evaluacion"]["pasos"])},
            "experiencias": {"texto": t["experiencias"]["texto"],
                             "paquetes": [{"clave": c, "nombre": n, "incluye": tipo} for c, n, tipo, _ in t["experiencias"]["paquetes"]]},
            "pacientes_internacionales": t["confort"]["texto"],
            "equipo": [{"nombre": n, "especialidad": c} for n, c, *_ in t["equipo"]["personas"]]}


class ProponerRegistro(Entrada):
    servicio_id: int | None = Field(None, ge=1, description="El servicio, de `servicios`. Opcional.")
    profesional_id: int | None = Field(None, ge=1, description="El profesional, de `espacios_libres`. Opcional.")
    inicio: datetime | None = Field(None, description="La hora que eligió la persona, tal como viene de `espacios_libres`. Pide `servicio_id`.")


@herramienta("proponer_registro", "Prepara la tarjeta para agendar en Colombia: un formulario donde la persona pone su documento y "
             "su celular (si ya es paciente entra a su página; si no, se registra) y sigue al calendario, con el servicio, el "
             "profesional y la hora ya elegidos. No agenda nada. No pidas esos datos en el chat.",
             ProponerRegistro, VIS, PROPUESTA)
def proponer_registro(conn, actor, a: ProponerRegistro) -> dict:
    if a.inicio and not a.servicio_id:
        raise ErrorHerramienta("datos_invalidos", "Para elegir una hora indica también `servicio_id`.")
    srv = _servicio(conn, a.servicio_id, True) if a.servicio_id else None
    pro = _profesional(conn, a.profesional_id) if a.profesional_id else None
    inicio = _bogota(a.inicio) if a.inicio else None
    if inicio:
        _espacio_libre(conn, pro["id"] if pro else None, srv["id"], inicio)
    # Los parámetros de `GET /p/{token}/nueva`; 0 es «sin elegir». `desde` es hora local sin zona.
    par = {"servicio": srv["id"] if srv else 0, "profesional": pro["id"] if pro else 0,
           "desde": inicio.strftime("%Y-%m-%dT%H:%M") if inicio else ""}
    resumen = ("Identifícate para agendar" + (f" {srv['nombre']}" if srv else "") + (f" el {_cuando(inicio)}" if inicio else "")
               + (f" con {pro['nombre']}" if pro else "") + ".")
    return _propuesta("registro", par, resumen)


class ProponerSolicitud(Entrada):
    interes: Literal["evaluacion_virtual", "experiencia", "contacto"] = Field(
        description="`evaluacion_virtual` (vive fuera de Colombia), `experiencia` (viaje, hotel, traslados) o `contacto`.")


@herramienta("proponer_solicitud", "Prepara la tarjeta con el formulario de solicitud del sitio (evaluación virtual, experiencia o "
             "contacto): la persona lo llena y lo envía; la clínica le responde. No envía nada. No pidas sus datos en el chat.",
             ProponerSolicitud, VIS, PROPUESTA)
def proponer_solicitud(conn, actor, a: ProponerSolicitud) -> dict:
    resumen = {"evaluacion_virtual": "Pedir una evaluación virtual.", "experiencia": "Pedir información de una experiencia.",
               "contacto": "Pedir que la clínica te contacte."}[a.interes]
    return _propuesta("solicitud", {"interes": a.interes}, resumen)
