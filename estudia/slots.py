"""Llenado de cupos: cupos liberados, candidatos y ofertas en cadena (RF-18 a RF-23)."""
from datetime import datetime, timedelta

import psycopg
from psycopg.types.range import Range

from . import clock, config, lifecycle, messaging, tasks
from .lifecycle import ALIVE


def register_slot(conn, professional_id: int, rango: Range, origin_cita_id: int | None, cause: str) -> int | None:
    """Todo rango que queda libre se registra (para medirlo). Solo ofrece si falta más que la antelación mínima.

    Un rango bloqueado no es un cupo: no se registra (devuelve None)."""
    now = clock.now(conn)
    if conn.execute("select 1 from bloqueo where profesional_id=%s and rango && %s", (professional_id, rango)).fetchone():
        return None
    cupo = conn.execute(
        "insert into cupo_liberado(profesional_id, rango, cita_origen_id, causa, creado_en) values (%s,%s,%s,%s,%s) "
        "returning id", (professional_id, rango, origin_cita_id, cause, now)).fetchone()["id"]
    if rango.lower - now >= timedelta(hours=config.get(conn, "antelacion_minima_cupo_horas")):
        next_offer(conn, cupo)
    return cupo


def candidates(conn, cupo) -> list[dict]:
    """Citas vivas del mismo profesional, posteriores al cupo, que admiten adelanto y caben en él."""
    now = clock.now(conn)
    slot_min = (cupo["rango"].upper - cupo["rango"].lower).total_seconds() / 60
    week_max = config.get(conn, "max_ofertas_paciente_semana")
    rows = conn.execute(
        """
        select c.id, c.paciente_id, c.rango, c.dia, s.duracion_min
        from cita c
        join servicio s on s.id = c.servicio_id
        join paciente p on p.id = c.paciente_id
        where c.profesional_id = %(pro)s
          and c.estado = any(%(alive)s)
          and c.rango is not null
          and lower(c.rango) > lower(%(rango)s)
          and s.admite_adelanto
          and s.duracion_min <= %(slot_min)s
          and p.acepta_mensajes
          and not exists (select 1 from oferta_adelanto o join cita c2 on c2.id = o.cita_id
                          where c2.paciente_id = c.paciente_id and o.estado = 'pendiente')
          and not exists (select 1 from cita c3 where c3.paciente_id = c.paciente_id and c3.id <> c.id
                          and c3.estado = any(%(alive)s) and c3.dia = (lower(%(rango)s) at time zone current_setting('TimeZone'))::date)
          and not exists (select 1 from oferta_adelanto o2 where o2.cupo_id = %(cupo)s and o2.cita_id = c.id)
          and (select count(*) from oferta_adelanto o3 join cita c4 on c4.id = o3.cita_id
               where c4.paciente_id = c.paciente_id and o3.enviada_en > %(now)s - interval '7 days') < %(week_max)s
        order by lower(c.rango) desc, c.id
        """,
        {"pro": cupo["profesional_id"], "alive": list(ALIVE), "rango": cupo["rango"], "slot_min": slot_min,
         "cupo": cupo["id"], "now": now, "week_max": week_max}).fetchall()
    return rows


def next_offer(conn, cupo_id: int) -> int | None:
    """Ofrece el cupo al siguiente candidato. Una oferta a la vez por cupo."""
    cupo = conn.execute("select * from cupo_liberado where id=%s for update", (cupo_id,)).fetchone()
    if cupo["estado"] not in ("abierto", "en_oferta"):
        return None
    if conn.execute("select 1 from oferta_adelanto where cupo_id=%s and estado='pendiente'", (cupo_id,)).fetchone():
        return None
    now = clock.now(conn)
    made = conn.execute("select count(*) as n from oferta_adelanto where cupo_id=%s", (cupo_id,)).fetchone()["n"]
    if made >= config.get(conn, "max_ofertas_por_cupo") or cupo["rango"].lower - now < timedelta(
            hours=config.get(conn, "antelacion_minima_cupo_horas")):
        conn.execute("update cupo_liberado set estado='abierto' where id=%s", (cupo_id,))
        return None
    cands = candidates(conn, cupo)
    if not cands:
        conn.execute("update cupo_liberado set estado='abierto' where id=%s", (cupo_id,))
        return None
    cand = cands[0]
    vence = min(now + timedelta(minutes=config.get(conn, "vigencia_oferta_min")),
                cupo["rango"].lower - timedelta(minutes=15))
    try:
        with conn.transaction():
            oferta = conn.execute(
                "insert into oferta_adelanto(cupo_id, cita_id, orden, enviada_en, vence_en) values (%s,%s,%s,%s,%s) "
                "returning id", (cupo_id, cand["id"], made + 1, now, vence)).fetchone()["id"]
    except psycopg.errors.UniqueViolation:
        return None
    conn.execute("update cupo_liberado set estado='en_oferta' where id=%s", (cupo_id,))
    from . import fmt
    old = cand["rango"].lower.astimezone(clock.TZ)
    new = cupo["rango"].lower.astimezone(clock.TZ)
    messaging.send(conn, cand["paciente_id"], "oferta_adelanto",
                   {"oferta_id": oferta, "fecha_actual": fmt.fecha(old), "hora_actual": fmt.hora(old),
                    "fecha_nueva": fmt.fecha(new), "hora_nueva": fmt.hora(new)},
                   entity=("oferta", oferta))
    tasks.schedule(conn, "vencer_oferta", vence, {"oferta_id": oferta})
    return oferta


def reject(conn, oferta_id: int) -> None:
    now = clock.now(conn)
    o = conn.execute("select * from oferta_adelanto where id=%s for update", (oferta_id,)).fetchone()
    if o["estado"] != "pendiente":
        return
    conn.execute("update oferta_adelanto set estado='rechazada', respondida_en=%s where id=%s", (now, oferta_id))
    next_offer(conn, o["cupo_id"])


def expire(conn, oferta_id: int) -> None:
    now = clock.now(conn)
    o = conn.execute("select * from oferta_adelanto where id=%s for update", (oferta_id,)).fetchone()
    if o["estado"] != "pendiente" or o["vence_en"] > now:
        return
    conn.execute("update oferta_adelanto set estado='vencida' where id=%s", (oferta_id,))
    next_offer(conn, o["cupo_id"])


def accept(conn, oferta_id: int) -> bool:
    """Una sola transacción: verifica vigencia, crea la cita en el cupo, cierra la anterior y reinicia la cadena.

    Devuelve False si la oferta ya no está disponible (el mensaje de 'no disponible' lo envía el llamador).
    """
    from . import agenda

    now = clock.now(conn)
    o = conn.execute("select * from oferta_adelanto where id=%s for update", (oferta_id,)).fetchone()
    if o["estado"] != "pendiente" or o["vence_en"] <= now:
        return False
    cupo = conn.execute("select * from cupo_liberado where id=%s for update", (o["cupo_id"],)).fetchone()
    cita = conn.execute("select * from cita where id=%s for update", (o["cita_id"],)).fetchone()
    if cita["estado"] not in ALIVE:
        conn.execute("update oferta_adelanto set estado='anulada', respondida_en=%s where id=%s", (now, oferta_id))
        return False
    dur = conn.execute("select duracion_min from servicio where id=%s", (cita["servicio_id"],)).fetchone()["duracion_min"]
    start = cupo["rango"].lower
    try:
        with conn.transaction():
            lifecycle.transition(conn, cita["id"], "reprogramada", "paciente", "Adelanto aceptado")
            estado = "confirmada" if cita["estado"] == "confirmada" else "programada"
            new = conn.execute(
                "insert into cita(paciente_id, profesional_id, servicio_id, tratamiento_id, dia, rango, estado, origen, "
                "cita_anterior_id, creada_en) values (%s,%s,%s,%s,%s,%s,%s,'sistema',%s,%s) returning id",
                (cita["paciente_id"], cita["profesional_id"], cita["servicio_id"], cita["tratamiento_id"],
                 start.astimezone(clock.TZ).date(), agenda.rng(start, dur), estado, cita["id"], now)).fetchone()["id"]
            conn.execute("update oferta_adelanto set estado='aceptada', respondida_en=%s where id=%s", (now, oferta_id))
            conn.execute("update cupo_liberado set estado='ocupado', ocupado_por='oferta' where id=%s", (cupo["id"],))
    except psycopg.errors.ExclusionViolation:
        conn.execute("update oferta_adelanto set estado='anulada', respondida_en=%s where id=%s", (now, oferta_id))
        return False
    lifecycle.record_birth(conn, new, estado, "paciente", f"Adelanto de la cita {cita['id']}")
    agenda._schedule_reminders(conn, new, start.astimezone(clock.TZ), now)
    # El rango que deja el paciente queda libre y reinicia el proceso (cadena, RF-20).
    register_slot(conn, cita["profesional_id"], cita["rango"], cita["id"], "adelanto")
    info = agenda._info(conn, new)
    messaging.send(conn, cita["paciente_id"], "adelanto_confirmado", info, direct=True, entity=("cita", new))
    return True


def close_due(conn, now: datetime) -> int:
    """Cuando llega la hora de un cupo se cierra como ocupado (agendamiento normal) o vacío."""
    n = 0
    for c in conn.execute("select * from cupo_liberado where estado in ('abierto','en_oferta') and lower(rango) <= %s "
                          "for update", (now,)).fetchall():
        conn.execute("update oferta_adelanto set estado='anulada', respondida_en=%s where cupo_id=%s and estado='pendiente'",
                     (now, c["id"]))
        taken = conn.execute("select 1 from cita where profesional_id=%s and estado = any(%s) and rango && %s",
                             (c["profesional_id"], list(ALIVE) + ["atendida", "no_asistio"], c["rango"])).fetchone()
        if taken:
            conn.execute("update cupo_liberado set estado='ocupado', ocupado_por='agendamiento' where id=%s", (c["id"],))
        else:
            conn.execute("update cupo_liberado set estado='vacio' where id=%s", (c["id"],))
        n += 1
    return n
