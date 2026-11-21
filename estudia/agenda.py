"""Agenda: disponibilidad y escritura de citas (PRD §6.5)."""
from datetime import date, datetime, timedelta

import psycopg
from psycopg.types.range import Range

from . import clock, config, lifecycle, tasks
from .lifecycle import ALIVE


class SlotTaken(Exception):
    """El espacio ya no está disponible."""


class CannotRevert(Exception):
    pass


class OutcomeTooEarly(Exception):
    """El desenlace solo se registra desde la hora de inicio de la cita."""


def rng(start: datetime, minutes: int) -> Range:
    return Range(start, start + timedelta(minutes=minutes), "[)")


def _local(day: date, t) -> datetime:
    return datetime.combine(day, t, tzinfo=clock.TZ)


def day_slots(conn, professional_id: int, service_id: int, day: date, now: datetime | None = None) -> list[datetime]:
    """Espacios agendables en un día: horario, duración, citas vivas, bloqueos y cupos con oferta pendiente."""
    now = now or clock.now(conn)
    dur = conn.execute("select duracion_min from servicio where id=%s", (service_id,)).fetchone()["duracion_min"]
    step = config.get(conn, "paso_min")
    earliest = now + timedelta(hours=config.get(conn, "antelacion_minima_agendar_horas"))
    latest = now + timedelta(days=config.get(conn, "horizonte_dias"))
    windows = conn.execute(
        "select desde, hasta from horario_atencion where profesional_id=%s and dia_semana=%s order by desde",
        (professional_id, day.weekday())).fetchall()
    if not windows:
        return []
    d0, d1 = _local(day, datetime.min.time()), _local(day, datetime.min.time()) + timedelta(days=1)
    busy = [r["rango"] for r in conn.execute(
        "select rango from cita where profesional_id=%s and estado = any(%s) and rango && tstzrange(%s,%s)",
        (professional_id, list(ALIVE), d0, d1))]
    busy += [r["rango"] for r in conn.execute(
        "select rango from bloqueo where profesional_id=%s and rango && tstzrange(%s,%s)", (professional_id, d0, d1))]
    busy += [r["rango"] for r in conn.execute(
        "select c.rango from cupo_liberado c join oferta_adelanto o on o.cupo_id=c.id and o.estado='pendiente' "
        "where c.profesional_id=%s and c.rango && tstzrange(%s,%s)", (professional_id, d0, d1))]
    out = []
    for w in windows:
        start, end = _local(day, w["desde"]), _local(day, w["hasta"])
        cur = start
        while cur + timedelta(minutes=dur) <= end:
            fin = cur + timedelta(minutes=dur)
            if cur >= earliest and cur <= latest and not any(b.lower < fin and cur < b.upper for b in busy):
                out.append(cur)
            cur += timedelta(minutes=step)
    return out


def available_slots(conn, professional_id: int, service_id: int, days: int | None = None) -> dict[date, list[datetime]]:
    now = clock.now(conn)
    days = days or config.get(conn, "horizonte_dias")
    out = {}
    for i in range(days + 1):
        d = now.date() + timedelta(days=i)
        s = day_slots(conn, professional_id, service_id, d, now)
        if s:
            out[d] = s
    return out


def _schedule_reminders(conn, cita_id: int, start: datetime, now: datetime) -> None:
    for h in config.get(conn, "recordatorios_horas"):
        at = start - timedelta(hours=h)
        if at > now:
            tasks.schedule(conn, "recordatorio", at, {"cita_id": cita_id, "horas": h, "inicio": start.isoformat()})


def book(conn, patient_id: int, professional_id: int, service_id: int, start: datetime, origin: str,
         actor: str, treatment_id: int | None = None, previous_id: int | None = None,
         notify: bool = True, user_id: int | None = None) -> int:
    """Agenda una cita. Lanza SlotTaken si el espacio ya no está (la base impide cruces)."""
    from . import followup, messaging

    now = clock.now(conn)
    start = start.astimezone(clock.TZ)
    if start not in day_slots(conn, professional_id, service_id, start.date(), now):
        raise SlotTaken("Ese espacio ya no está disponible")
    dur = conn.execute("select duracion_min from servicio where id=%s", (service_id,)).fetchone()["duracion_min"]
    born_confirmed = (start - now) < timedelta(hours=24)
    estado = "confirmada" if born_confirmed else "programada"
    try:
        with conn.transaction():
            row = conn.execute(
                "insert into cita(paciente_id, profesional_id, servicio_id, tratamiento_id, dia, rango, estado, origen, "
                "cita_anterior_id, creada_en) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                (patient_id, professional_id, service_id, treatment_id, start.date(), rng(start, dur), estado, origin,
                 previous_id, now)).fetchone()
    except psycopg.errors.ExclusionViolation:
        raise SlotTaken("Ese espacio ya no está disponible") from None
    cid = row["id"]
    lifecycle.record_birth(conn, cid, estado, actor,
                           "Agendar con menos de 24 h equivale a confirmar" if born_confirmed else "", user_id)
    _schedule_reminders(conn, cid, start, now)
    followup.resolve_on_booking(conn, patient_id, cid)
    if notify:
        p = _info(conn, cid)
        # Solo sale a quien está dado de baja si él mismo hizo el trámite (respuesta a su acción).
        messaging.send(conn, patient_id, "cita_agendada", p, direct=(actor == "paciente"), entity=("cita", cid))
    return cid


def _info(conn, cita_id: int) -> dict:
    from . import fmt
    c = conn.execute(
        "select c.*, p.nombre as profesional, s.nombre as servicio, s.duracion_min from cita c "
        "join profesional p on p.id=c.profesional_id join servicio s on s.id=c.servicio_id where c.id=%s",
        (cita_id,)).fetchone()
    start = c["rango"].lower.astimezone(clock.TZ) if c["rango"] else None
    return {"cita_id": cita_id, "profesional": c["profesional"], "servicio": c["servicio"],
            "fecha": fmt.fecha(start or c["dia"]), "hora": fmt.hora(start) if start else ""}


def hours_ahead(conn, cita) -> float:
    return (cita["rango"].lower - clock.now(conn)).total_seconds() / 3600


def cancel(conn, cita_id: int, actor: str, channel: str, reason_id: int | None = None, text: str | None = None,
           defer_first_attempt: bool = False, user_id: int | None = None) -> int:
    """Cancela una cita: registro de cancelación, cupo liberado y caso de seguimiento."""
    from . import followup, slots

    c = conn.execute("select * from cita where id=%s for update", (cita_id,)).fetchone()
    now = clock.now(conn)
    ahead = hours_ahead(conn, c) if c["rango"] else 0
    lifecycle.transition(conn, cita_id, "cancelada", actor, f"Cancelación por {channel}", user_id=user_id)
    row = conn.execute(
        "insert into cancelacion(cita_id, motivo_id, texto_libre, canal, antelacion_horas, tardia, momento) "
        "values (%s,%s,%s,%s,%s,%s,%s) returning id",
        (cita_id, reason_id, text, channel, round(ahead, 2), ahead < config.get(conn, "umbral_tardia_horas"), now),
    ).fetchone()
    # Ofertas pendientes de esta cita ya no aplican.
    conn.execute("update oferta_adelanto set estado='anulada', respondida_en=%s where cita_id=%s and estado='pendiente'",
                 (now, cita_id))
    if c["rango"]:
        slots.register_slot(conn, c["profesional_id"], c["rango"], cita_id, "cancelacion")
    followup.open_case(conn, "cancelacion", c["paciente_id"], cita_id=cita_id,
                       send_first=not defer_first_attempt)
    return row["id"]


def set_reason(conn, cancelacion_id: int, reason_id: int | None, text: str | None = None) -> None:
    conn.execute("update cancelacion set motivo_id=%s, texto_libre=%s where id=%s", (reason_id, text, cancelacion_id))


def reschedule(conn, cita_id: int, new_start: datetime, actor: str, origin: str = "paciente",
               user_id: int | None = None) -> int:
    """Cambiar la fecha no edita la cita: la cierra como reprogramada y crea una nueva enlazada."""
    from . import slots

    c = conn.execute("select * from cita where id=%s for update", (cita_id,)).fetchone()
    if c["estado"] not in ALIVE:
        raise lifecycle.InvalidTransition("Solo se puede cambiar la fecha de una cita viva")
    now = clock.now(conn)
    new_start = new_start.astimezone(clock.TZ)
    dur = conn.execute("select duracion_min from servicio where id=%s", (c["servicio_id"],)).fetchone()["duracion_min"]
    # El cupo propio no cuenta como ocupado al elegir un horario que se cruza con él.
    try:
        with conn.transaction():
            lifecycle.transition(conn, cita_id, "reprogramada", actor, "Cambio de fecha", user_id=user_id)
            if new_start not in day_slots(conn, c["profesional_id"], c["servicio_id"], new_start.date(), now):
                raise SlotTaken("Ese espacio ya no está disponible")
            conn.execute("update oferta_adelanto set estado='anulada', respondida_en=%s where cita_id=%s and estado='pendiente'",
                         (now, cita_id))
            estado = "confirmada" if (new_start - now) < timedelta(hours=24) else "programada"
            new = conn.execute(
                "insert into cita(paciente_id, profesional_id, servicio_id, tratamiento_id, dia, rango, estado, origen, "
                "cita_anterior_id, creada_en) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                (c["paciente_id"], c["profesional_id"], c["servicio_id"], c["tratamiento_id"], new_start.date(),
                 rng(new_start, dur), estado, origin, cita_id, now)).fetchone()["id"]
    except psycopg.errors.ExclusionViolation:
        raise SlotTaken("Ese espacio ya no está disponible") from None
    lifecycle.record_birth(conn, new, estado, actor, f"Reemplaza la cita {cita_id}", user_id)
    _schedule_reminders(conn, new, new_start, now)
    if c["rango"]:
        slots.register_slot(conn, c["profesional_id"], c["rango"], cita_id, "cambio_fecha")
    from . import messaging
    messaging.send(conn, c["paciente_id"], "cita_agendada", _info(conn, new), direct=(actor == "paciente"),
                   entity=("cita", new))
    return new


def mark_outcome(conn, cita_id: int, outcome: str, actor: str = "auxiliar", user_id: int | None = None) -> None:
    """Registra atendida / no asistió. Solo procede desde la hora de inicio de la cita."""
    from . import followup

    assert outcome in ("atendida", "no_asistio")
    c = conn.execute("select paciente_id, rango from cita where id=%s", (cita_id,)).fetchone()
    if c is not None and c["rango"] is not None and clock.now(conn) < c["rango"].lower:
        raise OutcomeTooEarly("Solo se puede registrar el desenlace desde la hora de inicio de la cita")
    lifecycle.transition(conn, cita_id, outcome, actor, "Desenlace registrado", user_id=user_id)
    if outcome == "no_asistio":
        followup.open_case(conn, "inasistencia", c["paciente_id"], cita_id=cita_id)


def revert(conn, historial_id: int, actor: str = "auxiliar", user_id: int | None = None) -> int:
    """Revertir es un evento nuevo que compensa al anterior; nunca borra historial (RNF-07)."""
    h = conn.execute("select * from historial_estado where id=%s", (historial_id,)).fetchone()
    if h is None or h["estado_anterior"] is None:
        raise CannotRevert("Ese cambio no se puede revertir")
    if conn.execute("select 1 from historial_estado where revierte_id=%s", (historial_id,)).fetchone():
        raise CannotRevert("Ese cambio ya fue revertido")
    cita_id, now = h["cita_id"], clock.now(conn)
    cita = conn.execute("select estado, profesional_id, rango from cita where id=%s", (cita_id,)).fetchone()
    current = cita["estado"]
    if current != h["estado_nuevo"]:
        raise CannotRevert("La cita cambió después de ese movimiento; revierte primero el más reciente")
    if h["estado_anterior"] in ALIVE and cita["rango"] is not None and conn.execute(
            "select 1 from bloqueo where profesional_id=%s and rango && %s",
            (cita["profesional_id"], cita["rango"])).fetchone():
        raise CannotRevert("El rango original quedó bloqueado. Agenda al paciente en otro espacio.")
    try:
        with conn.transaction():
            if h["estado_nuevo"] == "reprogramada":
                # Adelanto o cambio de fecha: se cancela la cita nueva y se recupera el rango original.
                nueva = conn.execute("select id, estado from cita where cita_anterior_id=%s and estado = any(%s)",
                                     (cita_id, list(ALIVE))).fetchone()
                if nueva is None:
                    raise CannotRevert("La cita que la reemplazó ya no está viva")
                lifecycle.transition(conn, nueva["id"], "cancelada", actor, f"Reversión del movimiento {historial_id}",
                                     revierte_id=None, force=True, user_id=user_id)
                conn.execute("update cupo_liberado set estado='anulado' where cita_origen_id=%s and estado in "
                             "('abierto','en_oferta')", (cita_id,))
                conn.execute("update oferta_adelanto o set estado='anulada', respondida_en=%s from cupo_liberado c "
                             "where o.cupo_id=c.id and c.cita_origen_id=%s and o.estado='pendiente'", (now, cita_id))
            elif h["estado_nuevo"] == "cancelada":
                conn.execute("update cupo_liberado set estado='anulado' where cita_origen_id=%s and estado in "
                             "('abierto','en_oferta')", (cita_id,))
                conn.execute("update oferta_adelanto o set estado='anulada', respondida_en=%s from cupo_liberado c "
                             "where o.cupo_id=c.id and c.cita_origen_id=%s and o.estado='pendiente'", (now, cita_id))
                conn.execute("update caso_seguimiento set estado='anulado', cerrado_en=%s where cita_id=%s and estado='abierto'",
                             (now, cita_id))
            elif h["estado_nuevo"] == "no_asistio":
                conn.execute("update caso_seguimiento set estado='anulado', cerrado_en=%s where cita_id=%s and estado='abierto'",
                             (now, cita_id))
            return lifecycle.transition(conn, cita_id, h["estado_anterior"], actor,
                                        f"Reversión del movimiento {historial_id}", revierte_id=historial_id, force=True,
                                        user_id=user_id)
    except psycopg.errors.ExclusionViolation:
        raise CannotRevert("El rango original ya no está libre. Agenda al paciente en otro espacio.") from None


def range_agenda(conn, desde: date, hasta: date, professional_id: int | None = None) -> dict:
    """Agenda por rango de fechas (inclusive): citas, bloqueos, franjas del horario y cupos liberados abiertos."""
    d0 = _local(desde, datetime.min.time())
    d1 = _local(hasta, datetime.min.time()) + timedelta(days=1)
    pro = (professional_id,) * 2
    citas = conn.execute(
        "select c.id, c.estado, c.dia, c.rango, c.profesional_id, pr.nombre as profesional, c.servicio_id, "
        "s.nombre as servicio, c.paciente_id, p.nombres || ' ' || p.apellidos as paciente, p.celular "
        "from cita c join profesional pr on pr.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "join paciente p on p.id=c.paciente_id where c.dia between %s and %s and c.estado <> 'reprogramada' "
        "and (%s::bigint is null or c.profesional_id=%s) order by c.dia, lower(c.rango), c.id",
        (desde, hasta, *pro)).fetchall()
    bloqueos = conn.execute(
        "select b.id, b.profesional_id, b.rango, b.motivo, u.nombre as creado_por_nombre from bloqueo b "
        "left join usuario u on u.id=b.creado_por where b.rango && tstzrange(%s,%s) "
        "and (%s::bigint is null or b.profesional_id=%s) order by lower(b.rango), b.id", (d0, d1, *pro)).fetchall()
    cupos = conn.execute(
        "select id, profesional_id, rango, estado, causa from cupo_liberado where estado in ('abierto','en_oferta') "
        "and rango && tstzrange(%s,%s) and (%s::bigint is null or profesional_id=%s) order by lower(rango)",
        (d0, d1, *pro)).fetchall()
    horarios = conn.execute(
        "select profesional_id, dia_semana, desde, hasta from horario_atencion "
        "where (%s::bigint is null or profesional_id=%s) order by profesional_id, dia_semana, desde", pro).fetchall()
    franjas = []
    day = desde
    while day <= hasta:
        for h in horarios:
            if h["dia_semana"] == day.weekday():
                franjas.append({"profesional_id": h["profesional_id"], "fecha": day,
                                "inicio": _local(day, h["desde"]), "fin": _local(day, h["hasta"])})
        day += timedelta(days=1)
    return {"citas": [c for c in citas if c["rango"] is not None], "citas_sin_hora": [c for c in citas if c["rango"] is None],
            "bloqueos": bloqueos, "cupos": cupos, "franjas": franjas}
