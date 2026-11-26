"""Enruta las respuestas de botón/lista por su identificador a la entidad que las originó."""
from . import agenda, confirmations, followup, messaging, slots


@messaging.route("conf")
def _conf(conn, patient_id, parts, mid):
    answer, cita_id = parts[0], int(parts[1])
    confirmations.process_response(conn, patient_id, answer, cita_id)


@messaging.route("confh")
def _confh(conn, patient_id, parts, mid):
    answer, ids = parts[0], [int(x) for x in parts[1].split("-") if x.isdigit()]
    confirmations.process_household(conn, patient_id, answer, ids)


@messaging.route("motivo")
def _motivo(conn, patient_id, parts, mid):
    cancel_id, reason_id = int(parts[0]), int(parts[1])
    agenda.set_reason(conn, cancel_id, reason_id)
    row = conn.execute("select cita_id from cancelacion where id=%s", (cancel_id,)).fetchone()
    caso = conn.execute("select id from caso_seguimiento where cita_id=%s and estado='abierto'", (row["cita_id"],)).fetchone()
    if caso:
        followup.send_attempt(conn, caso["id"], followup.FIRST_TEMPLATE["cancelacion"])


@messaging.route("seg")
def _seg(conn, patient_id, parts, mid):
    if parts[0] == "ahora_no":
        followup.decline(conn, int(parts[1]))
        messaging.send(conn, patient_id, "seguimiento_pausado", {}, direct=True)


@messaging.route("oferta")
def _oferta(conn, patient_id, parts, mid):
    answer, oferta_id = parts[0], int(parts[1])
    if answer == "si":
        if not slots.accept(conn, oferta_id):
            messaging.send(conn, patient_id, "oferta_no_disponible", {}, direct=True)
    else:
        o = conn.execute("select estado from oferta_adelanto where id=%s", (oferta_id,)).fetchone()
        if o["estado"] != "pendiente":
            messaging.send(conn, patient_id, "oferta_no_disponible", {}, direct=True)
        else:
            slots.reject(conn, oferta_id)
