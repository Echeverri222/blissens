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


DURACION_MIN, DURACION_MAX, DURACION_PASO = 15, 240, 15


def validar_duracion(duracion_min: int | None) -> int | None:
    """La duración de una cita que recepción cambia a mano: de 15 a 240 minutos, en múltiplos de 15."""
    from .pacientes import DatosInvalidos

    if duracion_min is None:
        return None
    if not DURACION_MIN <= duracion_min <= DURACION_MAX or duracion_min % DURACION_PASO:
        raise DatosInvalidos(f"La duración debe estar entre {DURACION_MIN} y {DURACION_MAX} minutos, de {DURACION_PASO} en {DURACION_PASO}")
    return duracion_min


def day_slots(conn, professional_id: int, service_id: int, day: date, now: datetime | None = None,
              duracion_min: int | None = None) -> list[datetime]:
    """Espacios agendables en un día: horario, duración, citas vivas, bloqueos y cupos con oferta pendiente.

    `duracion_min` reemplaza la del servicio (recepción puede alargar o acortar una cita)."""
    now = now or clock.now(conn)
    dur = validar_duracion(duracion_min) or conn.execute(
        "select duracion_min from servicio where id=%s", (service_id,)).fetchone()["duracion_min"]
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


def available_slots(conn, professional_id: int, service_id: int, days: int | None = None,
                    duracion_min: int | None = None) -> dict[date, list[datetime]]:
    now = clock.now(conn)
    days = days or config.get(conn, "horizonte_dias")
    out = {}
    for i in range(days + 1):
        d = now.date() + timedelta(days=i)
        s = day_slots(conn, professional_id, service_id, d, now, duracion_min)
        if s:
            out[d] = s
    return out


def any_slots(conn, service_id: int, days: int | None = None) -> dict[date, list[datetime]]:
    """Espacios de «cualquier especialista»: la unión de lo que ofrece cada profesional activo, sin repetir horas."""
    now = clock.now(conn)
    days = days or config.get(conn, "horizonte_dias")
    pros = [r["id"] for r in conn.execute("select id from profesional where activo order by id")]
    out = {}
    for i in range(days + 1):
        d = now.date() + timedelta(days=i)
        horas = sorted({h for pid in pros for h in day_slots(conn, pid, service_id, d, now)})
        if horas:
            out[d] = horas
    return out


def assign_professional(conn, service_id: int, start: datetime) -> int:
    """Elige a UN especialista para «cualquiera» entre quienes tienen libre ese espacio.

    Regla de desempate (determinista): menos citas vivas ese día; si empatan, el de menor id."""
    now = clock.now(conn)
    start = start.astimezone(clock.TZ)
    libres = [r["id"] for r in conn.execute("select id from profesional where activo order by id")
              if start in day_slots(conn, r["id"], service_id, start.date(), now)]
    if not libres:
        raise SlotTaken("Ese espacio ya no está disponible")
    carga = {r["profesional_id"]: r["n"] for r in conn.execute(
        "select profesional_id, count(*) as n from cita where dia=%s and estado = any(%s) and profesional_id = any(%s) "
        "group by profesional_id", (start.date(), list(ALIVE), libres))}
    return min(libres, key=lambda pid: (carga.get(pid, 0), pid))


def _schedule_reminders(conn, cita_id: int, start: datetime, now: datetime) -> None:
    for h in config.get(conn, "recordatorios_horas"):
        at = start - timedelta(hours=h)
        if at > now:
            tasks.schedule(conn, "recordatorio", at, {"cita_id": cita_id, "horas": h, "inicio": start.isoformat()})


def book(conn, patient_id: int, professional_id: int | None, service_id: int, start: datetime, origin: str,
         actor: str, treatment_id: int | None = None, previous_id: int | None = None,
         notify: bool = True, user_id: int | None = None, duracion_min: int | None = None) -> int:
    """Agenda una cita. Lanza SlotTaken si el espacio ya no está (la base impide cruces).

    `professional_id=None` es «cualquier especialista»: se asigna uno solo entre los que tienen libre ese espacio.
    `duracion_min` (15 a 240) cambia la duración de esta cita; sin él vale la del servicio."""
    from . import followup
    from .pacientes import DatosInvalidos

    if conn.execute("select 1 from paciente where id=%s and etapa='prospecto'", (patient_id,)).fetchone():
        raise DatosInvalidos("Es un prospecto: primero hay que registrar su documento para agendarle una cita presencial")
    validar_duracion(duracion_min)
    now = clock.now(conn)
    start = start.astimezone(clock.TZ)
    if professional_id is None:
        # Si otro paciente toma justo ese espacio con el elegido, se reintenta con quien siga libre.
        for _ in range(3):
            elegido = assign_professional(conn, service_id, start)  # SlotTaken si ya nadie lo tiene
            try:
                return book(conn, patient_id, elegido, service_id, start, origin, actor, treatment_id, previous_id,
                            notify, user_id, duracion_min)
            except SlotTaken:
                continue
        raise SlotTaken("Ese espacio ya no está disponible")
    if start not in day_slots(conn, professional_id, service_id, start.date(), now, duracion_min):
        raise SlotTaken("Ese espacio ya no está disponible")
    dur = duracion_min or conn.execute("select duracion_min from servicio where id=%s", (service_id,)).fetchone()["duracion_min"]
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
        # Solo sale a quien está dado de baja si él mismo hizo el trámite (respuesta a su acción).
        avisar_agendada(conn, patient_id, cid, direct=(actor == "paciente"))
    return cid


def avisar_agendada(conn, patient_id: int, cita_id: int, direct: bool) -> None:
    """Aviso de cita agendada. Un hogar con celular compartido no recibe un mensaje por cita: las que agenda seguidas
    salen juntas en un solo mensaje, unos minutos después de la última (tarea `avisar_agendadas`)."""
    from . import correo, familia, messaging

    raiz, ids = familia.hogar(conn, patient_id)
    if len(ids) == 1:
        messaging.send(conn, patient_id, "cita_agendada", _info(conn, cita_id), direct=direct, entity=("cita", cita_id))
    correo.enviar(conn, patient_id, "agendada", cita_id, direct=direct)  # el correo va a la dirección de cada paciente
    if len(ids) == 1:
        return
    conn.execute("update cita set datos_origen = datos_origen || '{\"aviso_pendiente\": true}' where id=%s", (cita_id,))
    cuando = clock.now(conn) + timedelta(minutes=config.get(conn, "agrupar_avisos_min"))
    # Cada cita nueva corre la espera: el mensaje sale cuando el hogar termina de agendar.
    if not conn.execute(
            "update tarea_programada set ejecutar_en=%s, datos = datos || jsonb_build_object('direct', "
            "coalesce((datos->>'direct')::boolean, false) or %s, 'citas', coalesce(datos->'citas', '[]') || to_jsonb(%s::bigint)) "
            "where tipo='avisar_agendadas' and estado='pendiente' and (datos->>'hogar')::bigint=%s returning id",
            (cuando, direct, cita_id, raiz["id"])).fetchone():
        tasks.schedule(conn, "avisar_agendadas", cuando, {"hogar": raiz["id"], "direct": direct, "citas": [cita_id]})


def enviar_agendadas(conn, hogar_id: int, direct: bool, cita_ids: list[int] | None = None) -> None:
    """Un solo mensaje con las citas del hogar agendadas desde el último aviso."""
    from . import familia, messaging

    raiz, ids = familia.hogar(conn, hogar_id)
    citas = conn.execute("select * from cita where (paciente_id = any(%s) or id = any(%s)) "
                         "and datos_origen ? 'aviso_pendiente' for update", (ids, cita_ids or [])).fetchall()
    conn.execute("update cita set datos_origen = datos_origen - 'aviso_pendiente' where id = any(%s)",
                 ([c["id"] for c in citas],))
    vivas = [c for c in citas if c["estado"] in ALIVE and c["rango"] is not None]
    for c in [c for c in vivas if c["paciente_id"] not in ids]:  # dejó el hogar durante la espera: su aviso, aparte
        messaging.send(conn, c["paciente_id"], "cita_agendada", _info(conn, c["id"]), direct=direct, entity=("cita", c["id"]))
    vivas = [c for c in vivas if c["paciente_id"] in ids]
    if not vivas:
        return  # se cancelaron o cambiaron antes de avisar: el aviso de la nueva fecha ya está en camino
    if len(vivas) == 1 and vivas[0]["paciente_id"] == raiz["id"]:
        messaging.send(conn, raiz["id"], "cita_agendada", _info(conn, vivas[0]["id"]), direct=direct,
                       entity=("cita", vivas[0]["id"]))
        return
    messaging.send(conn, raiz["id"], "cita_agendada_hogar", {"lista": messaging.lista_de_citas(conn, vivas, raiz["id"])},
                   direct=direct, entity=("cita", vivas[0]["id"]))


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
    from . import correo, followup, slots

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
    correo.enviar(conn, c["paciente_id"], "cancelada", cita_id, direct=(actor == "paciente"))
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
    avisar_agendada(conn, c["paciente_id"], new, direct=(actor == "paciente"))
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


def confirm_by_phone(conn, cita_id: int, user_id: int | None = None) -> None:
    """La auxiliar registra la confirmación que el paciente dio por teléfono: no cancela nada ni escribe al paciente."""
    c = conn.execute("select rango from cita where id=%s", (cita_id,)).fetchone()
    if c is not None and c["rango"] is not None and clock.now(conn) >= c["rango"].lower:
        raise lifecycle.InvalidTransition("Esa cita ya empezó: registra su desenlace")
    lifecycle.transition(conn, cita_id, "confirmada", "auxiliar", "Confirmada por teléfono", user_id=user_id)


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
