from datetime import timedelta

from estudia import agenda, clock, followup, tasks

from .conftest import at, book, button, make_patient, make_pro, outbox, press, status


def cancelled_case(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(22, "10:00"))
    agenda.cancel(conn, c, "paciente", "enlace")
    caso = conn.execute("select * from caso_seguimiento").fetchone()
    return pro, a, c, caso


def test_cancellation_opens_one_case_with_first_attempt(conn):
    pro, a, c, caso = cancelled_case(conn)
    assert caso["tipo"] == "cancelacion" and caso["estado"] == "abierto"
    assert len(outbox(conn, a, "cancelacion_recibida")) == 1
    assert followup.open_case(conn, "cancelacion", a, cita_id=c) is None  # solo un caso abierto por cita


def test_cadence_3_7_15_days_then_exhausted_and_escalated(conn):
    pro, a, c, caso = cancelled_case(conn)
    for days, n in ((3, 1), (7, 2), (15, 3)):
        clock.freeze(caso["abierto_en"] + timedelta(days=days, minutes=1))
        tasks.cycle(conn)
        assert len(outbox(conn, a, "seguimiento_reasignacion")) == n
    clock.freeze(caso["abierto_en"] + timedelta(days=23))
    tasks.cycle(conn)
    row = conn.execute("select estado, escalado from caso_seguimiento").fetchone()
    assert (row["estado"], row["escalado"]) == ("agotado", True)
    results = [r["resultado"] for r in conn.execute("select resultado from intento order by numero")]
    assert results == ["sin_respuesta"] * 4


def test_ahora_no_closes_case_without_more_attempts(conn):
    pro, a, c, caso = cancelled_case(conn)
    press(conn, a, button(conn, a, "cancelacion_recibida", 0))
    assert conn.execute("select estado from caso_seguimiento").fetchone()["estado"] == "rechazado"
    clock.freeze(caso["abierto_en"] + timedelta(days=4))
    tasks.cycle(conn)
    assert not outbox(conn, a, "seguimiento_reasignacion")
    assert conn.execute("select resultado from intento").fetchone()["resultado"] == "rechazo"


def test_booking_again_closes_case_as_reprogramado(conn):
    pro, a, c, caso = cancelled_case(conn)
    clock.freeze(caso["abierto_en"] + timedelta(days=3, minutes=1))
    tasks.cycle(conn)
    new = book(conn, a, pro, at(23, "10:00"))
    row = conn.execute("select * from caso_seguimiento").fetchone()
    assert row["estado"] == "reprogramado" and row["cita_resultante_id"] == new
    assert status(conn, c) == "reprogramada"
    assert [r["resultado"] for r in conn.execute("select resultado from intento order by numero")] == ["sin_respuesta", "acepto"]


def test_manual_attempt_by_phone(conn):
    pro, a, c, caso = cancelled_case(conn)
    followup.register_manual(conn, caso["id"], "sin_respuesta", "Llamada sin contestar")
    assert conn.execute("select canal from intento order by numero desc limit 1").fetchone()["canal"] == "manual"
    followup.register_manual(conn, caso["id"], "rechazo")
    assert conn.execute("select estado from caso_seguimiento").fetchone()["estado"] == "rechazado"


def test_no_show_opens_case(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(0, "13:00"))
    clock.freeze(at(0, "15:00"))
    agenda.mark_outcome(conn, c, "no_asistio")
    assert conn.execute("select tipo from caso_seguimiento").fetchone()["tipo"] == "inasistencia"
    assert outbox(conn, a, "seguimiento_inasistencia")


def test_opt_out_stops_automatic_messages(conn):
    pro, a = make_pro(conn), make_patient(conn)
    press_text = lambda t: __import__("estudia.messaging", fromlist=["x"]).receive(conn, a, text=t)
    press_text("BAJA")
    assert outbox(conn, a, "baja_confirmada")
    c = book(conn, a, pro, at(3, "10:00"))
    clock.freeze(at(3, "10:00") - timedelta(hours=47, minutes=59))
    tasks.cycle(conn)
    assert not outbox(conn, a, "recordatorio_48h")
    assert conn.execute("select count(*) n from mensaje where estado_entrega='omitido'").fetchone()["n"] >= 1


def test_free_text_is_logged_and_unhandled(conn):
    from estudia import messaging
    a = make_patient(conn)
    messaging.receive(conn, a, text="¿Tienen cita mañana?")
    m = conn.execute("select * from mensaje where direccion='entrante'").fetchone()
    assert m["gestionado"] is False and m["texto"] == "¿Tienen cita mañana?"


def test_automatic_messages_wait_for_sending_window(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    clock.freeze(at(3, "10:00") - timedelta(hours=48) + timedelta(minutes=0))  # 10:00 del lunes... dentro de ventana
    clock.freeze(at(1, "05:00"))  # fuera de la ventana 07:00-20:00
    from estudia import messaging
    mid = messaging.send(conn, a, "recordatorio_24h", agenda._info(conn, c))
    assert conn.execute("select estado_entrega from mensaje where id=%s", (mid,)).fetchone()["estado_entrega"] == "diferido"
    mid2 = messaging.send(conn, a, "recordatorio_24h", agenda._info(conn, c), direct=True)
    assert conn.execute("select estado_entrega from mensaje where id=%s", (mid2,)).fetchone()["estado_entrega"] == "entregado"
    clock.freeze(at(1, "07:01"))
    tasks.cycle(conn)
    assert conn.execute("select estado_entrega from mensaje where id=%s", (mid,)).fetchone()["estado_entrega"] == "entregado"


def test_whatsapp_limits_are_enforced(conn):
    import pytest

    from estudia import messaging
    with pytest.raises(messaging.MessageError):
        messaging.validate("botones", [{"id": str(i), "title": "x"} for i in range(4)])
    with pytest.raises(messaging.MessageError):
        messaging.validate("botones", [{"id": "1", "title": "x" * 21}])
    with pytest.raises(messaging.MessageError):
        messaging.validate("lista", [{"id": "1", "title": "x" * 25}])
    messaging.validate("lista", [{"id": str(i), "title": "x" * 24} for i in range(10)])
