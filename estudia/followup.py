"""Seguimiento: casos, intentos y cadencia (PRD §6.5)."""
from datetime import timedelta

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


SEGUIMIENTO = sorted(set(FIRST_TEMPLATE.values()) | set(RETRY_TEMPLATE.values()))
HORAS_ENTRE_SEGUIMIENTOS_DEL_HOGAR = 20


def nombre_con_titulo(titulo: str | None, nombre: str) -> str:
    return f"{titulo.strip()} {nombre}".strip() if titulo and titulo.strip() else nombre


def _profesional_del_caso(conn, caso) -> str:
    """El profesional de la cita o del tratamiento de origen, con su título; sin él, "nuestro equipo"."""
    if caso["cita_id"]:
        r = conn.execute("select p.titulo, p.nombre from cita c join profesional p on p.id=c.profesional_id where c.id=%s",
                         (caso["cita_id"],)).fetchone()
    elif caso["tratamiento_id"]:
        r = conn.execute("select p.titulo, p.nombre from tratamiento t join profesional p on p.id=t.profesional_id "
                         "where t.id=%s", (caso["tratamiento_id"],)).fetchone()
    else:
        r = None
    return nombre_con_titulo(r["titulo"], r["nombre"]) if r else "nuestro equipo"


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
                               "resultado is null and canal='automatico' order by numero desc limit 1) returning numero",
                               (caso_id,)).fetchone()
        tasks.schedule(conn, "intento_seguimiento", ultimo + timedelta(hours=HORAS_ENTRE_SEGUIMIENTOS_DEL_HOGAR),
                       {"caso_id": caso_id, "numero": abierto["numero"] if abierto else 1, "reprogramado": True})
        return
    data = {"caso_id": caso_id, "enlace": messaging.patient_link(conn, caso["paciente_id"], f"/agendar?caso={caso_id}")}
    if caso["cita_id"]:
        from .agenda import _info
        data.update(_info(conn, caso["cita_id"]))
    # Solo el profesional (título y nombre): nunca el servicio, el diagnóstico ni montos.
    data["profesional"] = _profesional_del_caso(conn, caso)
    messaging.send(conn, caso["paciente_id"], template, data, entity=("caso", caso_id))


def run_attempt(conn, caso_id: int, numero: int) -> None:
    """Llegó el siguiente intento: el anterior sin reacción queda 'sin respuesta'."""
    caso = conn.execute("select * from caso_seguimiento where id=%s for update", (caso_id,)).fetchone()
    if caso["estado"] != "abierto":
        return
    if conn.execute("select 1 from intento where caso_id=%s and numero >= %s and canal='automatico'",
                    (caso_id, numero)).fetchone():
        return  # un intento reprogramado que la cadencia ya alcanzó
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
