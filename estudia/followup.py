"""Seguimiento: casos, intentos y cadencia (PRD §6.5)."""
from datetime import timedelta

import psycopg

from . import clock, config, messaging, tasks

ACUSE_CANCELACION = "cancelacion_recibida"
# Plantilla de cada intento de la cadencia (R7: ninguno sale al abrir el caso; el primero es a los 3 días).
RETRY_TEMPLATE = {
    "cancelacion": "seguimiento_reasignacion",
    "inasistencia": "seguimiento_inasistencia",
    "tratamiento_a_medias": "continuidad_tratamiento",
}


def max_intentos(conn) -> int:
    """Intentos de la cadencia: uno por entrada (3, 7 y 15 días = 3). Los manuales de la recepción cuentan igual."""
    return len(config.get(conn, "cadencia_seguimiento_dias"))


def open_case(conn, kind: str, patient_id: int, *, cita_id: int | None = None, tratamiento_id: int | None = None) -> int | None:
    """Abre un caso. Solo hay uno abierto por cita o tratamiento de origen; devuelve None si ya existía o si el paciente
    es «No contactar». No envía nada: programa cada intento de la cadencia (la primera entrada puede no ser 0)."""
    from . import pacientes
    if not pacientes.contactable(conn, patient_id):
        return None  # «No contactar» (R6): no se abre caso
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
    for n, days in enumerate(cadence, start=1):
        tasks.schedule(conn, "intento_seguimiento", now + timedelta(days=days), {"caso_id": caso, "numero": n})
    tasks.schedule(conn, "agotar_caso", now + timedelta(days=cadence[-1] + config.get(conn, "dias_hasta_agotar")),
                   {"caso_id": caso})
    return caso


def acusar_cancelacion(conn, caso_id: int, *, direct: bool = True) -> int | None:
    """El aviso inmediato «tu cita quedó cancelada». Responde a la acción del propio paciente: sale como envío directo y
    NO es un intento de la cadencia (no se registra en `intento`)."""
    caso = conn.execute("select * from caso_seguimiento where id=%s", (caso_id,)).fetchone()
    return messaging.send(conn, caso["paciente_id"], ACUSE_CANCELACION, _datos(conn, caso), direct=direct,
                          entity=("caso", caso_id))


SEGUIMIENTO = sorted(set(RETRY_TEMPLATE.values()))
HORAS_ENTRE_SEGUIMIENTOS_DEL_HOGAR = 20


def _datos(conn, caso: dict) -> dict:
    data = {"caso_id": caso["id"], "enlace": messaging.patient_link(conn, caso["paciente_id"], f"/agendar?caso={caso['id']}")}
    if caso["cita_id"]:
        from .agenda import _info
        data.update(_info(conn, caso["cita_id"]))
    return data


def _automaticos(conn, caso_id: int) -> int:
    return conn.execute("select count(*) as n from intento where caso_id=%s and canal='automatico'", (caso_id,)).fetchone()["n"]


def send_attempt(conn, caso_id: int, template: str) -> None:
    caso = conn.execute("select * from caso_seguimiento where id=%s", (caso_id,)).fetchone()
    from . import familia
    _, ids = familia.hogar(conn, caso["paciente_id"])
    now = clock.now(conn)
    ultimo = conn.execute(
        "select max(momento) as m from mensaje where paciente_id = any(%s) and direccion='saliente' and plantilla = any(%s) "
        "and estado_entrega <> 'omitido' and momento > %s",
        (ids, SEGUIMIENTO, now - timedelta(hours=HORAS_ENTRE_SEGUIMIENTOS_DEL_HOGAR))).fetchone()["m"] if len(ids) > 1 else None
    if ultimo:
        # El celular del hogar ya recibió un seguimiento hace poco. Este intento no salió, así que no cuenta como
        # intento: se borra y se reprograma para cuando se cumpla la espera (uno a la vez por celular).
        abierto = conn.execute("delete from intento where id = (select id from intento where caso_id=%s and "
                               "resultado is null and canal='automatico' order by numero desc limit 1) returning id",
                               (caso_id,)).fetchone()
        tasks.schedule(conn, "intento_seguimiento", ultimo + timedelta(hours=HORAS_ENTRE_SEGUIMIENTOS_DEL_HOGAR),
                       {"caso_id": caso_id, "numero": _automaticos(conn, caso_id) + 1 if abierto else 1, "reprogramado": True})
        return
    mid = messaging.send(conn, caso["paciente_id"], template, _datos(conn, caso), entity=("caso", caso_id))
    if conn.execute("select 1 from mensaje where id=%s and detalle in ('celular','no_contactar')", (mid,)).fetchone():
        # No salió por el celular o por «No contactar»: no cuenta como intento (R8, R6).
        conn.execute("delete from intento where id = (select id from intento where caso_id=%s and resultado is null "
                     "and canal='automatico' order by numero desc limit 1)", (caso_id,))


def run_attempt(conn, caso_id: int, numero: int) -> None:
    """Llegó el siguiente intento: el anterior sin reacción queda 'sin respuesta'."""
    caso = conn.execute("select * from caso_seguimiento where id=%s for update", (caso_id,)).fetchone()
    if caso["estado"] != "abierto":
        return
    if _automaticos(conn, caso_id) >= numero:
        return  # un intento reprogramado que la cadencia ya alcanzó
    hechos = conn.execute("select count(*) as n from intento where caso_id=%s", (caso_id,)).fetchone()["n"]
    if hechos >= max_intentos(conn):
        return  # con los manuales de la recepción ya se completaron los intentos
    now = clock.now(conn)
    conn.execute("update intento set resultado='sin_respuesta' where caso_id=%s and resultado is null", (caso_id,))
    conn.execute("insert into intento(caso_id, numero, canal, momento) values (%s,%s,'automatico',%s)",
                 (caso_id, hechos + 1, now))
    send_attempt(conn, caso_id, RETRY_TEMPLATE[caso["tipo"]])


def exhaust(conn, caso_id: int) -> None:
    caso = conn.execute("select * from caso_seguimiento where id=%s for update", (caso_id,)).fetchone()
    if caso["estado"] != "abierto":
        return
    now = clock.now(conn)
    conn.execute("update intento set resultado='sin_respuesta' where caso_id=%s and resultado is null", (caso_id,))
    conn.execute("update caso_seguimiento set estado='agotado', escalado=true, cerrado_en=%s where id=%s", (now, caso_id))


def decline(conn, caso_id: int, user_id: int | None = None, *, patient_id: int | None = None) -> bool:
    """El paciente tocó 'Ahora no' (o la auxiliar lo registró): sin más intentos."""
    if patient_id is not None:
        from . import familia
        _, ids = familia.hogar(conn, patient_id)
        caso = conn.execute("select id from caso_seguimiento where id=%s and paciente_id = any(%s)",
                            (caso_id, ids)).fetchone()
        if caso is None:
            return False
    now = clock.now(conn)
    conn.execute("update intento set resultado='rechazo' where caso_id=%s and resultado is null", (caso_id,))
    conn.execute("update caso_seguimiento set estado='rechazado', cerrado_en=%s, cerrado_por=%s "
                 "where id=%s and estado='abierto'", (now, user_id, caso_id))
    return True


def register_manual(conn, caso_id: int, resultado: str, detalle: str = "", user_id: int | None = None) -> None:
    """La auxiliar registra una gestión por teléfono sobre el mismo caso."""
    assert resultado in ("acepto", "rechazo", "sin_respuesta")
    now = clock.now(conn)
    n = conn.execute("select coalesce(max(numero),0)+1 as n from intento where caso_id=%s", (caso_id,)).fetchone()["n"]
    conn.execute("insert into intento(caso_id, numero, canal, resultado, momento, detalle) values (%s,%s,'manual',%s,%s,%s)",
                 (caso_id, n, resultado, now, detalle))
    total = conn.execute("select count(*) as n from intento where caso_id=%s", (caso_id,)).fetchone()["n"]
    if total >= max_intentos(conn):  # con los intentos completos, los automáticos que faltan ya no salen
        conn.execute("delete from tarea_programada where tipo='intento_seguimiento' and estado='pendiente' "
                     "and (datos->>'caso_id')::bigint=%s", (caso_id,))
    if resultado == "rechazo":
        decline(conn, caso_id, user_id)
    elif resultado == "acepto":
        conn.execute("update caso_seguimiento set estado='reprogramado', cerrado_en=%s, cerrado_por=%s "
                     "where id=%s and estado='abierto'", (now, user_id, caso_id))


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
