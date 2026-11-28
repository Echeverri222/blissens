"""Recordatorios y confirmación explícita (RF-08 a RF-10)."""
import json
from datetime import datetime, timedelta

from . import agenda, clock, config, correo, familia, lifecycle, messaging
from .lifecycle import ALIVE


def _payload(conn, cita_id: int) -> dict:
    d = agenda._info(conn, cita_id)
    return d


def _enviado(conn) -> dict:
    """Marca de que el paciente recibió un recordatorio y cuándo (`recordatorio_en`): la bandeja de la auxiliar lo muestra.
    Es aparte de `recordatorio_<h>h`, que guarda la hora de inicio con la que salió el aviso agrupado del hogar."""
    return {"recordatorio_enviado": True, "recordatorio_en": clock.now(conn).isoformat()}


def _marca(horas: int) -> str:
    return f"recordatorio_{horas}h"


def _ya_avisada(c: dict, horas: int) -> bool:
    """La cita ya salió, con esta misma hora de inicio, en el recordatorio agrupado de su hogar."""
    v = (c["datos_origen"] or {}).get(_marca(horas))
    return bool(v) and c["rango"] is not None and datetime.fromisoformat(v) == c["rango"].lower


def _marcar(conn, citas: list[dict], horas: int, enviado: bool = False) -> None:
    for g in citas:
        extra = {_marca(horas): g["rango"].lower.isoformat(), **(_enviado(conn) if enviado else {})}
        conn.execute("update cita set datos_origen = datos_origen || %s::jsonb where id=%s", (json.dumps(extra), g["id"]))


def run_reminder(conn, cita_id: int, horas: int, inicio: str, now: datetime) -> None:
    c = conn.execute("select * from cita where id=%s for update", (cita_id,)).fetchone()
    if c["estado"] not in ALIVE or c["rango"] is None or c["rango"].lower != datetime.fromisoformat(inicio):
        return  # la cita cambió, se canceló o ya tuvo desenlace
    if _ya_avisada(c, horas):
        # Ya salió en el aviso agrupado del hogar. Pasa a «no confirmada» a su propia hora, no a la de la primera cita.
        if horas == min(config.get(conn, "recordatorios_horas")) and c["estado"] == "programada":
            lifecycle.transition(conn, cita_id, "no_confirmada", "sistema", "Sin respuesta al recordatorio")
        return
    raiz, ids = familia.hogar(conn, c["paciente_id"])
    if len(ids) == 1:
        _recordar_una(conn, c, horas)
        _marcar(conn, [c], horas)
        return
    # Hogar con celular compartido: un solo recordatorio con todas las citas de ese día que aún no lo recibieron.
    grupo = [g for g in conn.execute(
        "select * from cita where paciente_id = any(%s) and dia=%s and estado = any(%s) and rango is not null "
        "and lower(rango) > %s order by lower(rango), id for update", (ids, c["dia"], list(ALIVE), now)).fetchall()
        if g["id"] == c["id"] or not _ya_avisada(g, horas)]
    if len(grupo) == 1 and c["paciente_id"] == raiz["id"]:
        _recordar_una(conn, c, horas)  # solo la cita del propio responsable: el mensaje de siempre
        _marcar(conn, grupo, horas)
        return
    first, last = max(config.get(conn, "recordatorios_horas")), min(config.get(conn, "recordatorios_horas"))
    if horas == first and horas != last:
        pendientes = [g for g in grupo if g["estado"] == "programada"]
        if pendientes:
            messaging.send(conn, raiz["id"], "recordatorio_48h_hogar",
                           {"lista": messaging.lista_de_citas(conn, pendientes, raiz["id"]),
                            "ids": messaging.ids_de_boton(pendientes)}, entity=("cita", c["id"]))
        _marcar(conn, pendientes, horas, enviado=True)
        _marcar(conn, [g for g in grupo if g["estado"] != "programada"], horas)
        return
    for g in grupo:
        correo.enviar(conn, g["paciente_id"], "recordatorio", g["id"])  # cada correo va a la dirección de su paciente
        # Solo las que ya llegaron a su propia hora de 24 h; las demás pasan cuando les toque (ver arriba).
        if g["estado"] == "programada" and g["rango"].lower - timedelta(hours=horas) <= now:
            lifecycle.transition(conn, g["id"], "no_confirmada", "sistema", "Sin respuesta al recordatorio")
    sin_confirmar = [g for g in grupo if g["estado"] != "confirmada"]
    lista = messaging.lista_de_citas(conn, grupo, raiz["id"], marcar={g["id"] for g in sin_confirmar})
    if sin_confirmar:
        messaging.send(conn, raiz["id"], "segundo_intento_hogar",
                       {"lista": lista, "ids": messaging.ids_de_boton(sin_confirmar)}, entity=("cita", c["id"]))
    else:
        messaging.send(conn, raiz["id"], "recordatorio_24h_hogar", {"lista": lista}, entity=("cita", c["id"]))
    _marcar(conn, sin_confirmar, horas, enviado=True)
    _marcar(conn, [g for g in grupo if g["estado"] == "confirmada"], horas)


def _recordar_una(conn, c: dict, horas: int) -> None:
    cita_id = c["id"]
    first, last = max(config.get(conn, "recordatorios_horas")), min(config.get(conn, "recordatorios_horas"))
    data = _payload(conn, cita_id)
    if horas == first and horas != last:
        if c["estado"] == "programada":
            messaging.send(conn, c["paciente_id"], "recordatorio_48h", data, entity=("cita", cita_id))
            conn.execute("update cita set datos_origen = datos_origen || %s::jsonb where id=%s", (json.dumps(_enviado(conn)), cita_id))
    else:
        correo.enviar(conn, c["paciente_id"], "recordatorio", cita_id)  # el correo avisa; no pide confirmar
        if c["estado"] == "confirmada":
            messaging.send(conn, c["paciente_id"], "recordatorio_24h", data, entity=("cita", cita_id))
        else:
            if c["estado"] == "programada":
                lifecycle.transition(conn, cita_id, "no_confirmada", "sistema", "Sin respuesta al recordatorio")
            messaging.send(conn, c["paciente_id"], "segundo_intento", data, entity=("cita", cita_id))
            conn.execute("update cita set datos_origen = datos_origen || %s::jsonb where id=%s", (json.dumps(_enviado(conn)), cita_id))


def process_response(conn, patient_id: int, answer: str, cita_id: int) -> bool:
    _, ids = familia.hogar(conn, patient_id)
    c = conn.execute("select * from cita where id=%s and paciente_id = any(%s)", (cita_id, ids)).fetchone()
    if c is None:
        return False
    now = clock.now(conn)
    if c["estado"] not in ALIVE or (c["rango"] and c["rango"].lower <= now):
        messaging.send(conn, patient_id, "respuesta_tardia", {}, direct=True)
        return True
    if answer == "si":
        if c["estado"] != "confirmada":
            lifecycle.transition(conn, cita_id, "confirmada", "paciente", "Confirmó por WhatsApp")
        messaging.send(conn, patient_id, "confirmacion_recibida", agenda._info(conn, cita_id), direct=True)
    elif answer == "no":
        cancel_id = agenda.cancel(conn, cita_id, "paciente", "whatsapp", defer_acuse=True)
        reasons = conn.execute("select id, etiqueta from motivo_cancelacion order by orden").fetchall()
        options = [{"id": f"motivo:{cancel_id}:{r['id']}", "title": r["etiqueta"][:24]} for r in reasons]
        messaging.send(conn, patient_id, "pedir_motivo", agenda._info(conn, cita_id), direct=True, options=options,
                       entity=("cancelacion", cancel_id))
    elif answer == "cambiar":
        link = messaging.patient_link(conn, patient_id, f"/cambiar/{cita_id}")
        messaging.send(conn, patient_id, "cambiar_fecha", {**agenda._info(conn, cita_id), "enlace": link}, direct=True)
    else:
        return False
    return True


def process_household(conn, patient_id: int, answer: str, cita_ids: list[int]) -> None:
    """Respuesta a un recordatorio agrupado del hogar: aplica a las citas del botón que sigan siendo de ese hogar."""
    now = clock.now(conn)
    raiz, ids = familia.hogar(conn, patient_id)
    citas = conn.execute("select * from cita where id = any(%s) and paciente_id = any(%s) and estado = any(%s) "
                         "and rango is not null and lower(rango) > %s order by lower(rango), id",
                         (cita_ids, ids, list(ALIVE), now)).fetchall()
    if not citas:
        messaging.send(conn, patient_id, "respuesta_tardia", {}, direct=True)
        return
    if answer == "si":
        for c in citas:
            if c["estado"] != "confirmada":
                lifecycle.transition(conn, c["id"], "confirmada", "paciente", "Confirmó por WhatsApp (aviso del hogar)")
        messaging.send(conn, raiz["id"], "confirmacion_recibida_hogar",
                       {"lista": messaging.lista_de_citas(conn, citas, raiz["id"])}, direct=True)
    elif answer == "cambiar":
        messaging.send(conn, raiz["id"], "cambiar_hogar", {"enlace": messaging.patient_link(conn, raiz["id"])}, direct=True)
