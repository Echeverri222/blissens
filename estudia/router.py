"""Enruta las respuestas de botón/lista por su identificador a la entidad que las originó."""
from . import agenda, confirmations, familia, followup, messaging, slots


@messaging.route("conf")
def _conf(conn, patient_id, parts, mid):
    try:
        answer, cita_id = parts[0], int(parts[1])
    except (IndexError, ValueError):
        return False
    if answer not in ("si", "no", "cambiar"):
        return False
    return confirmations.process_response(conn, patient_id, answer, cita_id)


@messaging.route("confh")
def _confh(conn, patient_id, parts, mid):
    try:
        answer, raw_ids = parts[0], parts[1]
    except IndexError:
        return False
    if answer not in ("si", "cambiar"):
        return False
    ids = [int(x) for x in raw_ids.split("-") if x.isdigit()]
    if not ids:
        return False
    confirmations.process_household(conn, patient_id, answer, ids)
    return True


@messaging.route("motivo")
def _motivo(conn, patient_id, parts, mid):
    try:
        cancel_id, reason_id = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return False
    _, ids = familia.hogar(conn, patient_id)
    row = conn.execute(
        "select ca.cita_id from cancelacion ca join cita c on c.id=ca.cita_id "
        "where ca.id=%s and c.paciente_id = any(%s)",
        (cancel_id, ids),
    ).fetchone()
    if row is None:
        return False
    if not conn.execute("select 1 from motivo_cancelacion where id=%s", (reason_id,)).fetchone():
        return False
    agenda.set_reason(conn, cancel_id, reason_id)
    caso = conn.execute("select id from caso_seguimiento where cita_id=%s and estado='abierto'", (row["cita_id"],)).fetchone()
    if caso:
        followup.send_attempt(conn, caso["id"], followup.FIRST_TEMPLATE["cancelacion"])
    return True


@messaging.route("seg")
def _seg(conn, patient_id, parts, mid):
    try:
        action, caso_id = parts[0], int(parts[1])
    except (IndexError, ValueError):
        return False
    if action != "ahora_no":
        return False
    if not followup.decline(conn, caso_id, patient_id=patient_id):
        return False
    messaging.send(conn, patient_id, "seguimiento_pausado", {}, direct=True)
    return True


@messaging.route("oferta")
def _oferta(conn, patient_id, parts, mid):
    try:
        answer, oferta_id = parts[0], int(parts[1])
    except (IndexError, ValueError):
        return False
    if answer not in ("si", "no"):
        return False
    _, ids = familia.hogar(conn, patient_id)
    o = conn.execute(
        "select o.estado from oferta_adelanto o join cita c on c.id=o.cita_id "
        "where o.id=%s and c.paciente_id = any(%s)",
        (oferta_id, ids),
    ).fetchone()
    if o is None:
        return False
    if answer == "si":
        if not slots.accept(conn, oferta_id, patient_id=patient_id):
            messaging.send(conn, patient_id, "oferta_no_disponible", {}, direct=True)
    else:
        if o["estado"] != "pendiente":
            messaging.send(conn, patient_id, "oferta_no_disponible", {}, direct=True)
        else:
            slots.reject(conn, oferta_id, patient_id=patient_id)
    return True
