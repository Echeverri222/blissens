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
    assert s["ocupacion"] == 90 / 480                                          # minutos atendidos ÷ horario del día


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


# ----- Indicadores fase 2 (docs/prd-indicadores-fase2.md) -----

def _creada(conn, cid, momento):
    conn.execute("update cita set creada_en=%s where id=%s", (momento, cid))


def _usuario(conn, nombre="Ana Recepción"):
    from estudia import usuarios
    return usuarios.crear(conn, nombre.split()[0].lower(), nombre, "clave-de-prueba", "auxiliar")


def test_money_lost_counts_no_shows_and_unrebooked_late_cancellations(conn):
    pro = make_pro(conn)
    a, b, c, d = (make_patient(conn, n) for n in ("Ana", "Beto", "Cami", "Dani"))
    conn.execute("update servicio set valor=100000 where nombre='Valoración o revisión'")
    falta = raw(conn, a, pro, "08:00", "no_asistio")
    tarde = raw(conn, b, pro, "08:30", "cancelada")
    recuperada = raw(conn, c, pro, "09:00", "cancelada")
    sin_valor = raw(conn, d, pro, "09:30", "no_asistio", service="Limpieza")
    normal = raw(conn, a, pro, "10:00", "cancelada")                     # cancelación a tiempo: no es dinero perdido
    for cid, t in ((tarde, True), (recuperada, True), (normal, False)):
        cancel(conn, cid, "Viaje", t)
    nueva = raw(conn, c, pro, "08:00", "programada", day=DAY + timedelta(days=7))
    for cid in (falta, tarde, recuperada, sin_valor, normal):
        _creada(conn, cid, NOW - timedelta(days=20))
    _creada(conn, nueva, NOW + timedelta(days=2))                         # agendó de nuevo 2 días después de cancelar
    indicators.close_day(conn, DAY)
    s = indicators.summary(conn, filt(), comparar=True)
    assert (s["valor_perdido"], s["valor_perdido_inasistencia"], s["valor_perdido_tardias"]) == (200000, 100000, 100000)
    assert s["citas_sin_valor"] == 1                                      # la inasistencia de Limpieza no tiene valor
    assert s["anterior"]["valor_perdido"] == 0 and s["anterior"]["citas_sin_valor"] == 0
    por_pro = indicators.by_dimension(conn, filt(), "profesional")
    assert por_pro[0]["valor_perdido"] == 200000
    por_srv = {r["nombre"]: r["valor_perdido"] for r in indicators.by_dimension(conn, filt(), "servicio")}
    assert por_srv["Valoración o revisión"] == 200000 and por_srv["Limpieza"] == 0


def test_summary_returns_current_targets(conn):
    from estudia import config
    dataset(conn)
    indicators.close_day(conn, DAY)
    assert indicators.summary(conn, filt())["metas"] == {}
    config.set_(conn, "metas_indicadores", {"inasistencia": {"max": 0.15}})
    s = indicators.summary(conn, filt(), comparar=True)
    assert s["metas"] == {"inasistencia": {"max": 0.15}} and "metas" not in s["anterior"]


def test_pending_followthrough_medians_and_overdue(conn):
    pro, a = make_pro(conn), make_patient(conn)
    u = _usuario(conn)
    # Dos desenlaces registrados por una persona 2 h y 4 h después de terminar; uno por el sistema (no cuenta).
    for hh, horas in (("08:00", 2), ("08:30", 4)):
        cid = raw(conn, a, pro, hh, "atendida")
        fin = conn.execute("select upper(rango) as f from cita where id=%s", (cid,)).fetchone()["f"]
        conn.execute("insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, momento, usuario_id) "
                     "values (%s,'programada','atendida','auxiliar',%s,%s)", (cid, fin + timedelta(hours=horas), u))
    auto = raw(conn, a, pro, "09:00", "no_asistio")
    conn.execute("insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, momento) "
                 "values (%s,'programada','no_asistio','sistema',%s)", (auto, NOW))
    raw(conn, a, pro, "09:30", "programada", day=DAY - timedelta(days=1))          # abierta: ya pasó hace más de 48 h
    m = conn.execute("insert into mensaje(paciente_id, direccion, texto, gestionado, momento) "
                     "values (%s,'entrante','hola',false,%s) returning id", (a, NOW - timedelta(hours=60))).fetchone()["id"]
    from estudia import bandejas
    bandejas.mark_message_managed(conn, m, u)                                         # gestionado ahora, tras 60 h
    conn.execute("insert into mensaje(paciente_id, direccion, texto, gestionado, momento) "
                 "values (%s,'entrante','otro',false,%s)", (a, NOW - timedelta(hours=1)))
    f = {"desde": DAY, "hasta": NOW.date(), "profesional_id": None, "servicio_id": None}
    r = indicators.pending_followthrough(conn, f)
    c = r["cierre_citas"]
    assert c["resueltos"] == 2 and c["mediana_horas"] == 3.0 and c["p90_horas"] == 3.8
    assert c["vencidos"] == 1 and c["abiertos_hoy"] == 1
    ms = r["mensajes"]
    assert (ms["resueltos"], ms["mediana_horas"], ms["abiertos_hoy"], ms["vencidos"]) == (1, 60.0, 1, 0)
    assert r["seguimientos"]["resueltos"] == 0
    assert {(x["usuario"], x["resueltos"]) for x in r["por_usuario"]} == {("Ana Recepción", 3)}
    assert r["registro_desde"] == indicators.REGISTRO_PENDIENTES_DESDE


def test_pending_followthrough_counts_hand_closed_follow_ups_with_user(conn):
    from estudia import agenda, followup
    pro, a = make_pro(conn), make_patient(conn)
    u = _usuario(conn)
    c = agenda.book(conn, a, pro, svc(conn), at(2, "09:00"), "auxiliar", "auxiliar")
    clock_now = NOW + timedelta(days=1)
    from estudia import clock
    clock.freeze(clock_now)
    agenda.cancel(conn, c, "paciente", "enlace")
    caso = conn.execute("select id from caso_seguimiento").fetchone()["id"]
    clock.freeze(clock_now + timedelta(days=2))
    followup.register_manual(conn, caso, "rechazo", user_id=u)
    assert conn.execute("select cerrado_por from caso_seguimiento").fetchone()["cerrado_por"] == u
    r = indicators.pending_followthrough(conn, {"desde": DAY, "hasta": NOW.date() + timedelta(days=5), "profesional_id": None, "servicio_id": None})
    sg = r["seguimientos"]
    assert (sg["resueltos"], sg["mediana_horas"], sg["abiertos_hoy"]) == (1, 48.0, 0)


def test_rebooking_buckets(conn):
    pro = make_pro(conn)
    pacientes = [make_patient(conn, n) for n in ("Ana", "Beto", "Cami", "Dani", "Eli")]
    # momento de cada cancelación: NOW; la cita nueva se crea `dias` después (None = nunca).
    for i, (p, dias) in enumerate(zip(pacientes, (0, 2, 10, 40, None))):
        cid = raw(conn, p, pro, f"0{8 + i}:00", "cancelada")
        cancel(conn, cid, "Viaje", False)
        _creada(conn, cid, NOW - timedelta(days=5))
        if dias is not None:
            nueva = raw(conn, p, pro, f"0{8 + i}:00", "programada", day=DAY + timedelta(days=30))
            _creada(conn, nueva, NOW + timedelta(days=dias, hours=1))
    r = indicators.rebooking(conn, {"desde": NOW.date(), "hasta": NOW.date(), "profesional_id": None, "servicio_id": None})
    assert r["total"] == 5 and r["mediana_dias"] == 6.0           # mediana de 0, 2, 10, 40 días
    assert r["buckets"] == {"mismo_dia": 1, "1_3": 1, "4_14": 1, "15_60": 1, "no_reagendo": 1}
