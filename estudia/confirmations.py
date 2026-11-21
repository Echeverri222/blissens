"""Recordatorios y confirmación explícita (RF-08 a RF-10)."""
from datetime import datetime

from . import agenda, clock, config, correo, lifecycle, messaging
from .lifecycle import ALIVE


def _payload(conn, cita_id: int) -> dict:
    d = agenda._info(conn, cita_id)
    return d


def run_reminder(conn, cita_id: int, horas: int, inicio: str, now: datetime) -> None:
    c = conn.execute("select * from cita where id=%s for update", (cita_id,)).fetchone()
    if c["estado"] not in ALIVE or c["rango"] is None or c["rango"].lower != datetime.fromisoformat(inicio):
        return  # la cita cambió, se canceló o ya tuvo desenlace
    first, last = max(config.get(conn, "recordatorios_horas")), min(config.get(conn, "recordatorios_horas"))
    data = _payload(conn, cita_id)
    if horas == first and horas != last:
        if c["estado"] == "programada":
            messaging.send(conn, c["paciente_id"], "recordatorio_48h", data, entity=("cita", cita_id))
            conn.execute("update cita set datos_origen = datos_origen || '{\"recordatorio_enviado\": true}' where id=%s", (cita_id,))
    else:
        correo.enviar(conn, c["paciente_id"], "recordatorio", cita_id)  # el correo avisa; no pide confirmar
        if c["estado"] == "confirmada":
            messaging.send(conn, c["paciente_id"], "recordatorio_24h", data, entity=("cita", cita_id))
        else:
            if c["estado"] == "programada":
                lifecycle.transition(conn, cita_id, "no_confirmada", "sistema", "Sin respuesta al recordatorio")
            messaging.send(conn, c["paciente_id"], "segundo_intento", data, entity=("cita", cita_id))
            conn.execute("update cita set datos_origen = datos_origen || '{\"recordatorio_enviado\": true}' where id=%s", (cita_id,))


def process_response(conn, patient_id: int, answer: str, cita_id: int) -> None:
    c = conn.execute("select * from cita where id=%s", (cita_id,)).fetchone()
    now = clock.now(conn)
    if c is None or c["estado"] not in ALIVE or (c["rango"] and c["rango"].lower <= now):
        messaging.send(conn, patient_id, "respuesta_tardia", {}, direct=True)
        return
    if answer == "si":
        if c["estado"] != "confirmada":
            lifecycle.transition(conn, cita_id, "confirmada", "paciente", "Confirmó por WhatsApp")
        messaging.send(conn, patient_id, "confirmacion_recibida", agenda._info(conn, cita_id), direct=True)
    elif answer == "no":
        cancel_id = agenda.cancel(conn, cita_id, "paciente", "whatsapp", defer_first_attempt=True)
        reasons = conn.execute("select id, etiqueta from motivo_cancelacion order by orden").fetchall()
        options = [{"id": f"motivo:{cancel_id}:{r['id']}", "title": r["etiqueta"][:24]} for r in reasons]
        messaging.send(conn, patient_id, "pedir_motivo", agenda._info(conn, cita_id), direct=True, options=options,
                       entity=("cancelacion", cancel_id))
    elif answer == "cambiar":
        link = messaging.patient_link(conn, patient_id, f"/cambiar/{cita_id}")
        messaging.send(conn, patient_id, "cambiar_fecha", {**agenda._info(conn, cita_id), "enlace": link}, direct=True)
