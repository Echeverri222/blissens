"""Bandejas de la auxiliar: listas de trabajo derivadas con consultas (no hay tabla de alertas)."""
from datetime import date, datetime, timedelta

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


def no_confirmadas(conn):
    return conn.execute(
        "select c.id, lower(c.rango) as inicio, pr.nombre as profesional, p.id as paciente_id, "
        "p.nombres || ' ' || p.apellidos as paciente, p.celular from cita c join profesional pr on pr.id=c.profesional_id "
        "join paciente p on p.id=c.paciente_id where c.estado='no_confirmada' and c.rango is not null "
        "and lower(c.rango) > %s order by lower(c.rango)", (clock.now(conn),)).fetchall()


def seguimientos(conn):
    return conn.execute(
        "select cs.id, cs.tipo, cs.estado, cs.escalado, cs.abierto_en, p.id as paciente_id, "
        "p.nombres || ' ' || p.apellidos as paciente, p.celular, "
        "(select count(*) from intento i where i.caso_id=cs.id) as intentos, "
        "(select resultado from intento i where i.caso_id=cs.id order by numero desc limit 1) as ultimo "
        "from caso_seguimiento cs join paciente p on p.id=cs.paciente_id "
        "where cs.estado='abierto' or (cs.estado='agotado' and cs.escalado) order by cs.escalado desc, cs.abierto_en").fetchall()


def en_riesgo(conn):
    return recovery.at_risk(conn)


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
    return conn.execute("select * from solicitud_contacto where not gestionada order by momento").fetchall()


def dados_de_baja(conn):
    return conn.execute(
        "select c.id, lower(c.rango) as inicio, p.id as paciente_id, p.nombres || ' ' || p.apellidos as paciente, p.celular "
        "from cita c join paciente p on p.id=c.paciente_id where not p.acepta_mensajes and c.estado = any(%s) "
        "and c.rango is not null and lower(c.rango) > %s order by lower(c.rango)", (list(ALIVE), clock.now(conn))).fetchall()


def tareas_fallidas(conn):
    return conn.execute("select id, tipo, ejecutar_en, intentos, error from tarea_programada where estado='fallida' "
                        "order by ejecutar_en desc limit 50").fetchall()


def mark_message_managed(conn, message_id: int) -> bool:
    """Marca como gestionado un mensaje entrante. False si no existe."""
    return conn.execute("update mensaje set gestionado=true where id=%s and direccion='entrante' returning id",
                        (message_id,)).fetchone() is not None


def mark_contact_managed(conn, request_id: int) -> bool:
    return conn.execute("update solicitud_contacto set gestionada=true where id=%s returning id",
                        (request_id,)).fetchone() is not None


def pending_tasks(conn) -> int:
    return conn.execute("select count(*) as n from tarea_programada where estado='pendiente'").fetchone()["n"]


def find_patients(conn, q: str):
    like = f"%{q.strip()}%"
    return conn.execute(
        "select id, nombres, apellidos, documento, celular from paciente where nombres ilike %s or apellidos ilike %s "
        "or documento like %s or celular like %s order by apellidos, nombres limit 30", (like, like, like, like)).fetchall()


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
