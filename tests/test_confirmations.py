from datetime import timedelta

from estudia import clock, tasks

from .conftest import at, book, button, make_patient, make_pro, outbox, press, status


def test_reminders_at_48h_and_24h_with_three_buttons(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))   # jueves 10:00
    tasks.cycle(conn)
    assert not outbox(conn, a, "recordatorio_48h")
    clock.freeze(at(3, "10:00") - timedelta(hours=48) + timedelta(minutes=1))
    tasks.cycle(conn)
    msg = outbox(conn, a, "recordatorio_48h")[0]
    assert [b["title"] for b in msg["botones"]] == ["Sí, asistiré", "No podré ir", "Cambiar fecha"]


def test_yes_confirms_and_24h_gets_short_reminder(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    clock.freeze(at(3, "10:00") - timedelta(hours=47, minutes=59))
    tasks.cycle(conn)
    press(conn, a, button(conn, a, "recordatorio_48h", 0))
    assert status(conn, c) == "confirmada" and outbox(conn, a, "confirmacion_recibida")
    clock.freeze(at(3, "10:00") - timedelta(hours=23, minutes=59))
    tasks.cycle(conn)
    assert outbox(conn, a, "recordatorio_24h") and not outbox(conn, a, "segundo_intento")
    assert not outbox(conn, a, "recordatorio_24h")[0]["botones"]


def test_no_answer_becomes_no_confirmada_with_second_attempt(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    clock.freeze(at(3, "10:00") - timedelta(hours=47, minutes=59))
    tasks.cycle(conn)
    clock.freeze(at(3, "10:00") - timedelta(hours=23, minutes=59))
    tasks.cycle(conn)
    assert status(conn, c) == "no_confirmada"
    assert len(outbox(conn, a, "segundo_intento")) == 1


def test_late_answer_still_valid_before_appointment(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    clock.freeze(at(3, "10:00") - timedelta(hours=47, minutes=59))
    tasks.cycle(conn)
    btn = button(conn, a, "recordatorio_48h", 0)
    clock.freeze(at(3, "10:00") - timedelta(hours=23, minutes=59))
    tasks.cycle(conn)
    assert status(conn, c) == "no_confirmada"
    press(conn, a, btn)
    assert status(conn, c) == "confirmada"


def test_no_podre_ir_cancels_asks_reason_and_offers_new_slots(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    clock.freeze(at(3, "10:00") - timedelta(hours=47, minutes=59))
    tasks.cycle(conn)
    press(conn, a, button(conn, a, "recordatorio_48h", 1))
    assert status(conn, c) == "cancelada"
    pedir = outbox(conn, a, "pedir_motivo")[0]
    assert pedir["tipo"] == "lista" and len(pedir["botones"]) == 5
    assert [o["title"] for o in pedir["botones"]] == ["Salud", "Trabajo o estudio", "Viaje", "Motivo económico", "Otro"]
    assert all(len(o["title"]) <= 24 for o in pedir["botones"])
    press(conn, a, pedir["botones"][2]["id"])  # Viaje
    assert conn.execute("select m.etiqueta from cancelacion c join motivo_cancelacion m on m.id=c.motivo_id").fetchone()["etiqueta"] == "Viaje"
    assert "/p/" in outbox(conn, a, "cancelacion_recibida")[0]["texto"]


def test_cambiar_fecha_keeps_appointment_and_sends_link(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    clock.freeze(at(3, "10:00") - timedelta(hours=47, minutes=59))
    tasks.cycle(conn)
    press(conn, a, button(conn, a, "recordatorio_48h", 2))
    assert status(conn, c) == "programada"
    assert f"/cambiar/{c}" in outbox(conn, a, "cambiar_fecha")[0]["texto"]


def test_cancelled_appointment_gets_no_reminders(conn):
    from estudia import agenda
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    agenda.cancel(conn, c, "paciente", "enlace")
    clock.freeze(at(3, "10:00") - timedelta(hours=47, minutes=59))
    tasks.cycle(conn)
    assert not outbox(conn, a, "recordatorio_48h")


def test_booking_with_little_notice_skips_confirmation_flow(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(1, "08:00"))  # 24 h exactas -> no hay recordatorio de 48 h
    assert status(conn, c) == "programada"
    c2 = book(conn, a, pro, at(0, "14:00"))
    assert status(conn, c2) == "confirmada"
    tasks.cycle(conn)
    assert not outbox(conn, a, "recordatorio_48h")
