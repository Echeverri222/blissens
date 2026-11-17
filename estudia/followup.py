"""Seguimiento: casos, intentos y cadencia (PRD §6.5)."""
from datetime import datetime, timedelta

import psycopg

from . import clock, config, messaging, tasks

FIRST_TEMPLATE = {
    "cancelacion": "cancelacion_recibida",
    "inasistencia": "seguimiento_inasistencia",
    "tratamiento_a_medias": "continuidad_tratamiento",
}
RETRY_TEMPLATE = {
    "cancelacion": "seguimiento_reasignacion",
    "inasistencia": "seguimiento_inasistencia",
    "tratamiento_a_medias": "continuidad_tratamiento",
}


def open_case(conn, kind: str, patient_id: int, *, cita_id: int | None = None, tratamiento_id: int | None = None,
              send_first: bool = True) -> int | None:
    """Abre un caso. Solo hay uno abierto por cita o tratamiento de origen; devuelve None si ya existía."""
    now = clock.now(conn)
    try:
        with conn.transaction():
            caso = conn.execute(
                "insert into caso_seguimiento(tipo, paciente_id, cita_id, tratamiento_id, abierto_en) "
                "values (%s,%s,%s,%s,%s) returning id", (kind, patient_id, cita_id, tratamiento_id, now),
            ).fetchone()["id"]
    except psycopg.errors.UniqueViolation:
        return None
    cadence = config.get(conn, "cadencia_seguimiento_dias")
    conn.execute("insert into intento(caso_id, numero, canal, momento) values (%s,1,'automatico',%s)", (caso, now))
    for n, days in enumerate(cadence[1:], start=2):
        tasks.schedule(conn, "intento_seguimiento", now + timedelta(days=days), {"caso_id": caso, "numero": n})
    tasks.schedule(conn, "agotar_caso", now + timedelta(days=cadence[-1] + config.get(conn, "dias_hasta_agotar")),
                   {"caso_id": caso})
    if send_first:
        send_attempt(conn, caso, FIRST_TEMPLATE[kind])
    return caso


def send_attempt(conn, caso_id: int, template: str) -> None:
    caso = conn.execute("select * from caso_seguimiento where id=%s", (caso_id,)).fetchone()
    data = {"caso_id": caso_id, "enlace": messaging.patient_link(conn, caso["paciente_id"], f"/agendar?caso={caso_id}")}
    if caso["cita_id"]:
        from .agenda import _info
        data.update(_info(conn, caso["cita_id"]))
    messaging.send(conn, caso["paciente_id"], template, data, entity=("caso", caso_id))


def run_attempt(conn, caso_id: int, numero: int) -> None:
    """Llegó el siguiente intento: el anterior sin reacción queda 'sin respuesta'."""
    caso = conn.execute("select * from caso_seguimiento where id=%s for update", (caso_id,)).fetchone()
    if caso["estado"] != "abierto":
        return
    now = clock.now(conn)
    conn.execute("update intento set resultado='sin_respuesta' where caso_id=%s and resultado is null", (caso_id,))
    conn.execute("insert into intento(caso_id, numero, canal, momento) values (%s,%s,'automatico',%s)",
                 (caso_id, numero, now))
    send_attempt(conn, caso_id, RETRY_TEMPLATE[caso["tipo"]])


def exhaust(conn, caso_id: int) -> None:
    caso = conn.execute("select * from caso_seguimiento where id=%s for update", (caso_id,)).fetchone()
    if caso["estado"] != "abierto":
        return
    now = clock.now(conn)
    conn.execute("update intento set resultado='sin_respuesta' where caso_id=%s and resultado is null", (caso_id,))
    conn.execute("update caso_seguimiento set estado='agotado', escalado=true, cerrado_en=%s where id=%s", (now, caso_id))


def decline(conn, caso_id: int) -> None:
    """El paciente tocó 'Ahora no': sin más intentos."""
    now = clock.now(conn)
    conn.execute("update intento set resultado='rechazo' where caso_id=%s and resultado is null", (caso_id,))
    conn.execute("update caso_seguimiento set estado='rechazado', cerrado_en=%s where id=%s and estado='abierto'",
                 (now, caso_id))


def register_manual(conn, caso_id: int, resultado: str, detalle: str = "") -> None:
    """La auxiliar registra una gestión por teléfono sobre el mismo caso."""
    assert resultado in ("acepto", "rechazo", "sin_respuesta")
    now = clock.now(conn)
    n = conn.execute("select coalesce(max(numero),0)+1 as n from intento where caso_id=%s", (caso_id,)).fetchone()["n"]
    conn.execute("insert into intento(caso_id, numero, canal, resultado, momento, detalle) values (%s,%s,'manual',%s,%s,%s)",
                 (caso_id, n, resultado, now, detalle))
    if resultado == "rechazo":
        decline(conn, caso_id)
    elif resultado == "acepto":
        conn.execute("update caso_seguimiento set estado='reprogramado', cerrado_en=%s where id=%s and estado='abierto'",
                     (now, caso_id))


def resolve_on_booking(conn, patient_id: int, new_cita_id: int) -> None:
    """Si el paciente agenda (por enlace o con la auxiliar), sus casos abiertos se cierran como reprogramados."""
    now = clock.now(conn)
    for caso in conn.execute("select * from caso_seguimiento where paciente_id=%s and estado='abierto'",
                             (patient_id,)).fetchall():
        conn.execute("update intento set resultado='acepto' where caso_id=%s and resultado is null", (caso["id"],))
        conn.execute("update caso_seguimiento set estado='reprogramado', cita_resultante_id=%s, cerrado_en=%s where id=%s",
                     (new_cita_id, now, caso["id"]))
        if caso["cita_id"]:
            c = conn.execute("select estado from cita where id=%s", (caso["cita_id"],)).fetchone()
            if c["estado"] == "cancelada":
                from . import lifecycle
                lifecycle.transition(conn, caso["cita_id"], "reprogramada", "paciente", "Reagendó después de cancelar")
                conn.execute("update cita set cita_anterior_id=%s where id=%s and cita_anterior_id is null",
                             (caso["cita_id"], new_cita_id))
