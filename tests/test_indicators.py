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
