"""Bandejas de la auxiliar: listas de trabajo derivadas con consultas (no hay tabla de alertas)."""
from datetime import date, datetime, time, timedelta

from . import clock, recovery
from .lifecycle import ALIVE


def today_agenda(conn, day: date | None = None, professional_id: int | None = None):
    day = day or clock.now(conn).date()
    return conn.execute(
        "select c.id, c.estado, c.rango, c.dia, pr.nombre as profesional, s.nombre as servicio, "
        "p.id as paciente_id, p.nombres || ' ' || p.apellidos as paciente from cita c "
        "join profesional pr on pr.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "join paciente p on p.id=c.paciente_id where c.dia=%s and (%s::bigint is null or c.profesional_id=%s) "
        "and c.estado <> 'reprogramada' order by pr.nombre, lower(c.rango)", (day, professional_id, professional_id)).fetchall()


def fin_de_manana(conn) -> datetime:
    """Medianoche que cierra el día de mañana, en la zona del negocio."""
    ahora = clock.now(conn)
    return datetime.combine(ahora.date() + timedelta(days=2), time.min, tzinfo=ahora.tzinfo)


def _recordatorio(datos: dict) -> tuple[bool, datetime | None]:
    """(¿se envió recordatorio?, cuándo). `recordatorio_en` lo deja `confirmations`; las citas antiguas solo traen la bandera."""
    en = datos.get("recordatorio_en")
    return bool(en or datos.get("recordatorio_enviado")), datetime.fromisoformat(en) if isinstance(en, str) else None


def no_confirmadas(conn):
    """Citas sin confirmación que aún no empiezan: las `no_confirmada` y las `programada` de hoy y mañana (sin respuesta aún).

    Primero las `no_confirmada` de cada día, por hora. Los pacientes dados de baja van en `dados_de_baja`."""
    filas = conn.execute(
        "select c.id, c.estado, lower(c.rango) as inicio, pr.nombre as profesional, p.id as paciente_id, "
        "p.nombres || ' ' || p.apellidos as paciente, p.celular, c.datos_origen from cita c "
        "join profesional pr on pr.id=c.profesional_id join paciente p on p.id=c.paciente_id "
        "where c.rango is not null and lower(c.rango) > %s and p.acepta_mensajes "
        "and (c.estado='no_confirmada' or (c.estado='programada' and lower(c.rango) < %s))",
        (clock.now(conn), fin_de_manana(conn))).fetchall()
    out = []
    for r in filas:
        enviado, cuando = _recordatorio(r.pop("datos_origen"))
        out.append({**r, "recordatorio_enviado": enviado, "recordatorio_en": cuando})
    zona = clock.tz(conn)
    return sorted(out, key=lambda r: (r["inicio"].astimezone(zona).date(), r["estado"] != "no_confirmada", r["inicio"]))


def resumen_dia(conn) -> dict:
    """Los cuatro contadores de la franja superior de la agenda de la auxiliar."""
    ahora = clock.now(conn)
    limite = fin_de_manana(conn)
    return {
        "citas_hoy": conn.execute("select count(*) as n from cita where dia=%s and estado = any(%s)",
                                  (ahora.date(), list(ALIVE))).fetchone()["n"],
        "sin_confirmar": sum(1 for r in no_confirmadas(conn) if r["inicio"] < limite),
        "mensajes": len(sin_interpretar(conn)), "por_cerrar": len(sin_desenlace(conn))}


def seguimientos(conn):
    return conn.execute(
        "select cs.id, cs.tipo, cs.estado, cs.escalado, cs.abierto_en, p.id as paciente_id, "
        "p.nombres || ' ' || p.apellidos as paciente, p.celular, p.internacional, p.deportista, "
        "(select count(*) from intento i where i.caso_id=cs.id) as intentos, "
        "(select resultado from intento i where i.caso_id=cs.id order by numero desc limit 1) as ultimo "
        "from caso_seguimiento cs join paciente p on p.id=cs.paciente_id "
        "where cs.estado='abierto' or (cs.estado='agotado' and cs.escalado) "
        "order by cs.escalado desc, (p.internacional or p.deportista) desc, cs.abierto_en").fetchall()


def en_riesgo(conn, profesional_id: int | None = None, servicio_id: int | None = None):
    return recovery.at_risk(conn, profesional_id=profesional_id, servicio_id=servicio_id)


def cupos_libres(conn):
    return conn.execute(
        "select c.id, lower(c.rango) as inicio, upper(c.rango) as fin, c.estado, c.causa, pr.nombre as profesional, "
        "(select count(*) from oferta_adelanto o where o.cupo_id=c.id) as ofertas, "
        "(select string_agg(p.nombres || ' ' || p.apellidos || ' (' || o.estado || ')', ', ' order by o.orden) "
        " from oferta_adelanto o join cita ci on ci.id=o.cita_id join paciente p on p.id=ci.paciente_id "
        " where o.cupo_id=c.id) as ofrecido_a "
        "from cupo_liberado c join profesional pr on pr.id=c.profesional_id "
        "where c.estado in ('abierto','en_oferta') and lower(c.rango) > %s order by lower(c.rango)",
        (clock.now(conn),)).fetchall()


def sin_desenlace(conn):
    return conn.execute(
        "select c.id, lower(c.rango) as inicio, c.estado, pr.nombre as profesional, p.id as paciente_id, "
        "p.nombres || ' ' || p.apellidos as paciente from cita c join profesional pr on pr.id=c.profesional_id "
        "join paciente p on p.id=c.paciente_id where c.estado = any(%s) and c.rango is not null and upper(c.rango) < %s "
        "order by lower(c.rango)", (list(ALIVE), clock.now(conn))).fetchall()


def sin_interpretar(conn):
    return conn.execute(
        "select m.id, m.momento, m.texto, p.id as paciente_id, p.nombres || ' ' || p.apellidos as paciente "
        "from mensaje m join paciente p on p.id=m.paciente_id where m.direccion='entrante' and not m.gestionado "
        "order by m.momento").fetchall()


def contactos_pendientes(conn):
    """Con los adjuntos (sin su contenido) y el paciente al que la recepción la vinculó."""
    return conn.execute(
        "select s.id, s.documento, s.celular, s.nota, s.momento, s.origen, s.interes, s.idioma, s.nombre, s.correo, s.pais, "
        "s.paquete, s.mensaje, s.paciente_id, nullif(trim(p.nombres || ' ' || p.apellidos), '') as paciente, "
        "coalesce((select json_agg(json_build_object('id', a.id, 'nombre', a.nombre, 'tipo', a.tipo, 'tamano', a.tamano) "
        "order by a.id) from solicitud_adjunto a where a.solicitud_id=s.id), '[]') as adjuntos "
        "from solicitud_contacto s left join paciente p on p.id=s.paciente_id where not s.gestionada order by s.momento").fetchall()


def dados_de_baja(conn):
    return conn.execute(
        "select c.id, lower(c.rango) as inicio, p.id as paciente_id, p.nombres || ' ' || p.apellidos as paciente, p.celular "
        "from cita c join paciente p on p.id=c.paciente_id where not p.acepta_mensajes and c.estado = any(%s) "
        "and c.rango is not null and lower(c.rango) > %s order by lower(c.rango)", (list(ALIVE), clock.now(conn))).fetchall()


def mark_message_managed(conn, message_id: int, user_id: int | None = None) -> bool:
    """Marca como gestionado un mensaje entrante, con quién y cuándo. False si no existe."""
    return conn.execute(
        "update mensaje set gestionado=true, gestionado_en=coalesce(gestionado_en, %s), "
        "gestionado_por=coalesce(gestionado_por, %s) where id=%s and direccion='entrante' returning id",
        (clock.now(conn), user_id, message_id)).fetchone() is not None


def mark_contact_managed(conn, request_id: int) -> bool:
    return conn.execute("update solicitud_contacto set gestionada=true where id=%s returning id",
                        (request_id,)).fetchone() is not None


def pending_tasks(conn) -> int:
    return conn.execute("select count(*) as n from tarea_programada where estado='pendiente'").fetchone()["n"]


CON_TILDE, SIN_TILDE = "áéíóúüñàèìòù", "aeiouunaeiou"


def _sin_tildes(texto: str) -> str:
    return texto.lower().translate(str.maketrans(CON_TILDE, SIN_TILDE))


SEGMENTOS = ("internacional", "deportista")
TOPE_BUSQUEDA = 50


def find_patients(conn, q: str = "", segmentos: tuple[str, ...] = ()):
    """Pacientes cuyo nombre, apellido, documento o celular contienen CADA palabra de `q`, sin importar tildes ni mayúsculas:
    «laura gomez» encuentra a Laura Gómez Arango (recepción casi nunca escribe tildes). Con `segmentos` se queda con los
    que tienen alguna de esas marcas de alto valor; sin texto, lista a todos los de esos segmentos."""
    palabras = _sin_tildes(q).split()[:6]
    segmentos = tuple(s for s in SEGMENTOS if s in segmentos)
    if not palabras and not segmentos:
        return []
    nombre = f"translate(lower(nombres || ' ' || apellidos), '{CON_TILDE}', '{SIN_TILDE}')"
    condiciones = [f"({nombre} like %s or documento like %s or celular like %s or lower(correo) like %s)" for _ in palabras]
    if segmentos:
        condiciones.append("(" + " or ".join(segmentos) + ")")
    args = [x for w in palabras for x in (f"%{w}%",) * 4]
    return conn.execute(f"select id, nombres, apellidos, documento, celular, etapa, internacional, deportista from paciente "
                        f"where {' and '.join(condiciones)} order by apellidos, nombres limit {TOPE_BUSQUEDA}", args).fetchall()


def patient_record(conn, patient_id: int) -> dict:
    return {
        "paciente": conn.execute("select * from paciente where id=%s", (patient_id,)).fetchone(),
        "citas": conn.execute(
            "select c.id, c.estado, c.dia, c.rango, c.origen, pr.nombre as profesional, s.nombre as servicio from cita c "
            "join profesional pr on pr.id=c.profesional_id join servicio s on s.id=c.servicio_id "
            "where c.paciente_id=%s order by c.dia desc, lower(c.rango) desc", (patient_id,)).fetchall(),
        "historial": conn.execute(
            "select h.id, h.cita_id, h.estado_anterior, h.estado_nuevo, h.actor, h.detalle, h.momento, h.revierte_id, "
            "u.nombre as usuario, exists(select 1 from historial_estado r where r.revierte_id=h.id) as revertido "
            "from historial_estado h join cita c on c.id=h.cita_id left join usuario u on u.id=h.usuario_id "
            "where c.paciente_id=%s order by h.momento desc, h.id desc",
            (patient_id,)).fetchall(),
        "casos": conn.execute(
            "select cs.*, (select json_agg(json_build_object('numero', i.numero, 'canal', i.canal, 'resultado', i.resultado, "
            "'momento', i.momento) order by i.numero) from intento i where i.caso_id=cs.id) as intentos "
            "from caso_seguimiento cs where cs.paciente_id=%s order by cs.abierto_en desc", (patient_id,)).fetchall(),
        "mensajes": conn.execute(
            "select * from mensaje where paciente_id=%s and estado_entrega <> 'diferido' order by momento, id",
            (patient_id,)).fetchall(),
    }
