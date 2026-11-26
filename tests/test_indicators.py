from datetime import date, timedelta

from estudia import indicators
from estudia.agenda import rng

from .conftest import NOW, at, make_patient, make_pro, svc

DAY = date(2026, 11, 10)  # martes


def raw(conn, pat, pro, hhmm, estado, day=DAY, service="Valoración o revisión", confirmed=False, reminded=False):
    from datetime import datetime

    from estudia import clock
    h, m = hhmm.split(":")
    start = datetime(day.year, day.month, day.day, int(h), int(m), tzinfo=clock.TZ)
    cid = conn.execute(
        "insert into cita(paciente_id, profesional_id, servicio_id, dia, rango, estado, origen, datos_origen) "
        "values (%s,%s,%s,%s,%s,%s,'auxiliar',%s) returning id",
        (pat, pro, svc(conn, service), day, rng(start, 30), estado,
         '{"recordatorio_enviado": true}' if reminded else "{}")).fetchone()["id"]
    if confirmed:
        conn.execute("insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, momento) "
                     "values (%s,'programada','confirmada','paciente',%s)", (cid, NOW))
    return cid


def cancel(conn, cid, motivo, tardia):
    mid = conn.execute("select id from motivo_cancelacion where etiqueta=%s", (motivo,)).fetchone()["id"]
    conn.execute("insert into cancelacion(cita_id, motivo_id, canal, antelacion_horas, tardia, momento) "
                 "values (%s,%s,'enlace',%s,%s,%s)", (cid, mid, 5 if tardia else 48, tardia, NOW))


def dataset(conn):
    pro, a = make_pro(conn), make_patient(conn)
    for hh in ("08:00", "08:30", "09:00"):
        raw(conn, a, pro, hh, "atendida", confirmed=True, reminded=True)
    raw(conn, a, pro, "09:30", "no_asistio", reminded=True)
    c1 = raw(conn, a, pro, "10:00", "cancelada")
    c2 = raw(conn, a, pro, "10:30", "reprogramada")
    cancel(conn, c1, "Viaje", True)
    cancel(conn, c2, "Salud", False)
    return pro, a


def filt(pro=None):
    return {"desde": DAY, "hasta": DAY, "profesional_id": pro}


def test_daily_close_and_summary_definitions(conn):
    pro, a = dataset(conn)
    indicators.close_day(conn, DAY)
    s = indicators.summary(conn, filt())
    assert s["citas"] == 6 and s["atencion_efectiva"] == 3 / 6                 # atendidas ÷ total
    assert s["inasistencia"] == 1 / 4                                           # no_asistio ÷ (atendida + no_asistio)
    assert s["cancelaciones"] == 2 and s["cancelaciones_tardias"] == 1
    assert s["recuperacion"] == 1 / 2                                           # cancelaciones con cita nueva ÷ total
    assert s["confirmacion"] == 3 / 4                                           # confirmadas explícitas ÷ con recordatorio
    assert s["ocupacion"] == 90 / 540                                           # minutos atendidos ÷ horario del día


def test_reasons_distribution_with_late_share(conn):
    dataset(conn)
    indicators.close_day(conn, DAY)
    r = {x["motivo"]: x for x in indicators.reasons(conn, filt())}
    assert r["Viaje"]["cancelaciones"] == 1 and r["Viaje"]["tardias"] == 1
    assert r["Salud"]["cancelaciones"] == 1 and r["Salud"]["tardias"] == 0


def test_close_is_idempotent_and_filters_by_professional(conn):
    pro, a = dataset(conn)
    pro2 = make_pro(conn, "Dr. Otro")
    raw(conn, a, pro2, "08:00", "no_asistio")
    indicators.close_day(conn, DAY)
    before = conn.execute("select * from hecho_diario order by profesional_id, servicio_id").fetchall()
    indicators.close_day(conn, DAY)
    after = conn.execute("select * from hecho_diario order by profesional_id, servicio_id").fetchall()
    assert before == after
    assert indicators.summary(conn, filt(pro))["inasistencia"] == 1 / 4
    assert indicators.summary(conn, filt(pro2))["inasistencia"] == 1.0
    by = {r["nombre"]: r for r in indicators.by_dimension(conn, filt(), "profesional")}
    assert by["Dr. Otro"]["no_asistio"] == 1


def test_time_between_attended_appointments(conn):
    pro, a = make_pro(conn), make_patient(conn)
    for d in (DAY - timedelta(days=30), DAY - timedelta(days=20), DAY):
        raw(conn, a, pro, "08:00", "atendida", day=d)
    rows = indicators.time_between(conn, {"desde": DAY - timedelta(days=60), "hasta": DAY})
    assert rows[0]["dias"] == 15.0
    assert indicators.time_between_patient(conn, {"desde": DAY - timedelta(days=60), "hasta": DAY}) == 15.0


def test_slot_facts_in_daily_close(conn):
    pro = make_pro(conn)
    from estudia import slots
    slots.register_slot(conn, pro, rng(at(-6, "10:00"), 30), None, "cancelacion")  # martes pasado 10 de nov
    conn.execute("update cupo_liberado set estado='vacio'")
    indicators.close_day(conn, DAY)
    s = indicators.summary(conn, filt())
    assert s["cupos_liberados"] == 1 and s["cupos_vacios"] == 1


# ----- Indicadores accionables (docs/prd-indicadores.md) -----

def test_asistencia_excludes_rescheduled_and_unresolved(conn):
    pro, a = dataset(conn)                                   # 3 atendidas, 1 no asistió, 1 cancelada, 1 reprogramada
    raw(conn, a, pro, "11:00", "programada")                  # sin desenlace: no cuenta en asistencia
    indicators.close_day(conn, DAY)
    s = indicators.summary(conn, filt())
    assert s["asistencia"] == 3 / 5                            # atendidas ÷ (atendidas + no asistió + canceladas)
    assert s["atencion_efectiva"] == 3 / 7                     # la cifra obsoleta no cambia
    assert s["sin_desenlace"] == 1


def test_sin_desenlace_per_week_in_trend(conn):
    pro, a = dataset(conn)
    raw(conn, a, pro, "11:00", "confirmada")
    indicators.close_day(conn, DAY)
    sem = indicators.weekly_trend(conn, filt())
    assert sem[0]["sin_desenlace"] == 1 and indicators.trend(conn, filt())[0]["sin_desenlace"] == 1


def test_summary_compares_with_previous_period(conn):
    pro, a = dataset(conn)
    ant = DAY - timedelta(days=1)
    raw(conn, a, pro, "08:00", "atendida", day=ant)
    raw(conn, a, pro, "08:30", "no_asistio", day=ant)
    raw(conn, a, pro, "09:00", "no_asistio", day=ant)
    indicators.close_day(conn, DAY)
    indicators.close_day(conn, ant)
    s = indicators.summary(conn, filt(), comparar=True)
    assert (s["desde_anterior"], s["hasta_anterior"]) == (ant, ant)   # igual duración, termina el día antes
    assert s["inasistencia"] == 1 / 4 and s["anterior"]["inasistencia"] == 2 / 3
    assert "anterior" not in indicators.summary(conn, filt())
    p = indicators.period_before({"desde": date(2026, 11, 1), "hasta": date(2026, 11, 10)})
    assert (p["desde"], p["hasta"]) == (date(2026, 10, 22), date(2026, 10, 31))


def test_repeat_no_shows(conn):
    pro, a = make_pro(conn), make_patient(conn)
    b = make_patient(conn, "Luis", "Gómez")
    for hh in ("08:00", "08:30"):
        raw(conn, a, pro, hh, "no_asistio")
    raw(conn, b, pro, "09:00", "no_asistio")
    raw(conn, a, pro, "10:00", "programada", day=DAY + timedelta(days=30))  # cita futura de a
    rows = indicators.repeat_no_shows(conn, filt())
    assert [(r["paciente_id"], r["faltas"], r["tiene_cita_futura"]) for r in rows] == [(a, 2, True)]
    assert indicators.repeat_no_shows(conn, {**filt(), "servicio_id": svc(conn, "Limpieza")}) == []


def test_missed_appointments_flags_rebooked(conn):
    pro, a = make_pro(conn), make_patient(conn)
    f = raw(conn, a, pro, "08:00", "no_asistio")
    tarde = raw(conn, a, pro, "09:00", "cancelada")
    cancel(conn, tarde, "Viaje", True)
    temprano = raw(conn, a, pro, "10:00", "cancelada")
    cancel(conn, temprano, "Salud", False)                    # cancelación a tiempo: no cuenta como perdida
    raw(conn, a, pro, "11:00", "programada", day=DAY + timedelta(days=7))  # volvió a agendar el mismo servicio
    rows = {r["cita_id"]: r for r in indicators.missed_appointments(conn, filt())}
    assert set(rows) == {f, tarde}
    assert rows[f]["estado"] == "no_asistio" and rows[f]["reagendada"] is True
    assert rows[tarde]["motivo"] == "Viaje" and rows[tarde]["cancelacion_tardia"] is True
    assert indicators.missed_appointments(conn, {**filt(), "profesional_id": make_pro(conn, "Dr. Otro")}) == []


def test_reminders_compare_and_funnel(conn):
    pro, a = dataset(conn)                                     # con recordatorio: 3 atendidas + 1 no asistió
    raw(conn, a, pro, "11:00", "atendida")
    raw(conn, a, pro, "11:30", "no_asistio")
    indicators.close_day(conn, DAY)
    r = indicators.reminders(conn, filt())
    assert r["con_recordatorio"] == {"n": 4, "no_asistio": 1, "inasistencia": 1 / 4}
    assert r["sin_recordatorio"] == {"n": 2, "no_asistio": 1, "inasistencia": 1 / 2}
    assert r["embudo"] == {"citas": 8, "con_recordatorio": 4, "confirmadas": 3, "atendidas": 4}


def test_weekday_hour_uses_local_time(conn):
    pro, a = make_pro(conn), make_patient(conn)
    raw(conn, a, pro, "08:00", "atendida")
    raw(conn, a, pro, "08:30", "no_asistio")
    raw(conn, a, pro, "09:00", "no_asistio")
    raw(conn, a, pro, "10:00", "cancelada")                    # no cuenta
    celdas = {(c["dia_semana"], c["hora"]): c for c in indicators.weekday_hour(conn, filt())}
    assert celdas[(1, 8)]["atendidas"] == 1 and celdas[(1, 8)]["no_asistio"] == 1   # martes = 1
    assert celdas[(1, 9)]["no_asistio"] == 1 and (1, 10) not in celdas


def test_service_filter_applies_to_time_between_patient(conn):
    pro, a = make_pro(conn), make_patient(conn)
    for d, s in ((DAY - timedelta(days=30), "Valoración o revisión"), (DAY - timedelta(days=20), "Valoración o revisión"),
                 (DAY - timedelta(days=19), "Limpieza"), (DAY, "Valoración o revisión")):
        raw(conn, a, pro, "08:00", "atendida", day=d, service=s)
    f = {"desde": DAY - timedelta(days=60), "hasta": DAY}
    assert indicators.time_between_patient(conn, {**f, "servicio_id": svc(conn)}) == 15.0
    assert indicators.time_between_patient(conn, f) == (10 + 1 + 19) / 3
    pro2 = make_pro(conn, "Dr. Otro")
    assert indicators.time_between_patient(conn, {**f, "profesional_id": pro2}) is None


def test_capacity_and_slots_do_not_apply_when_filtering_by_service(conn):
    dataset(conn)
    indicators.close_day(conn, DAY)
    s = indicators.summary(conn, {**filt(), "servicio_id": svc(conn)})
    assert s["capacidad_aplica"] is False
    assert s["ocupacion"] is None and s["minutos_disponibles"] is None and s["cupos_liberados"] is None
    assert s["cupos_vacios"] is None and s["citas"] == 6
    assert indicators.summary(conn, filt())["capacidad_aplica"] is True
