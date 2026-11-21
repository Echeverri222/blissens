"""Tareas del ciclo: handlers de tareas programadas, vencimientos y procesos diarios."""
from datetime import datetime, timedelta

from . import canales, config, confirmations, correo, followup, indicators, privacidad, recovery, slots, tasks


@tasks.handler("recordatorio")
def _recordatorio(conn, d, now):
    confirmations.run_reminder(conn, d["cita_id"], d["horas"], d["inicio"], now)


@tasks.handler("intento_seguimiento")
def _intento(conn, d, now):
    followup.run_attempt(conn, d["caso_id"], d["numero"])


@tasks.handler("agotar_caso")
def _agotar(conn, d, now):
    followup.exhaust(conn, d["caso_id"])


@tasks.handler("vencer_oferta")
def _vencer(conn, d, now):
    slots.expire(conn, d["oferta_id"])


@tasks.handler("entregar_mensaje")
def _entregar(conn, d, now):
    if conn.execute("update mensaje set estado_entrega='entregado' where id=%s and estado_entrega='diferido' returning id",
                    (d["mensaje_id"],)).fetchone():
        canales.enviar_mensaje(conn, d["mensaje_id"])


@tasks.handler("entregar_correo")
def _entregar_correo(conn, d, now):
    correo.entregar_diferido(conn, d["mensaje_id"], d["intento"])


def expire_offers(conn, now: datetime) -> int:
    n = 0
    for o in conn.execute("select id from oferta_adelanto where estado='pendiente' and vence_en <= %s", (now,)).fetchall():
        slots.expire(conn, o["id"])
        n += 1
    return n


def close_slots(conn, now: datetime) -> int:
    return slots.close_due(conn, now)


def run_daily(conn, now: datetime) -> dict | None:
    """Una vez por día: detección de pacientes en riesgo y cierre de indicadores de los días pendientes."""
    today = now.date()
    last = config.get(conn, "ultimo_diario")
    if last and datetime.fromisoformat(last).date() >= today:
        return None
    first = datetime.fromisoformat(last).date() if last else today - timedelta(days=1)
    first = max(first, today - timedelta(days=60))
    closed = indicators.close_range(conn, first, today - timedelta(days=1)) if first <= today - timedelta(days=1) else 0
    opened = recovery.detect(conn, now)
    depurado = privacidad.depurar(conn)  # por defecto no borra nada
    config.set_(conn, "ultimo_diario", today.isoformat())
    return {"cierres": closed, "casos_recuperacion": opened, **({"depurado": depurado} if depurado else {})}
