from datetime import timedelta

from estudia import agenda, clock, followup, tasks

from .conftest import at, book, button, make_patient, make_pro, outbox, press, status


def cancelled_case(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(22, "10:00"))
    agenda.cancel(conn, c, "paciente", "enlace")
    caso = conn.execute("select * from caso_seguimiento").fetchone()
    return pro, a, c, caso


def test_cancellation_opens_one_case_and_acknowledges_without_counting_an_attempt(conn):
    pro, a, c, caso = cancelled_case(conn)
    assert caso["tipo"] == "cancelacion" and caso["estado"] == "abierto"
    assert len(outbox(conn, a, "cancelacion_recibida")) == 1
    assert conn.execute("select count(*) n from intento").fetchone()["n"] == 0  # el acuse no es un intento
    assert not outbox(conn, a, "seguimiento_reasignacion")  # y no sale nada más al abrir
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
    assert results == ["sin_respuesta"] * 3  # tres intentos: a los 3, 7 y 15 días


def test_ahora_no_closes_case_without_more_attempts(conn):
    pro, a, c, caso = cancelled_case(conn)
    press(conn, a, button(conn, a, "cancelacion_recibida", 0))
    assert conn.execute("select estado from caso_seguimiento").fetchone()["estado"] == "rechazado"
    clock.freeze(caso["abierto_en"] + timedelta(days=4))
    tasks.cycle(conn)
    assert not outbox(conn, a, "seguimiento_reasignacion")
    assert conn.execute("select count(*) n from intento").fetchone()["n"] == 0


def test_booking_again_closes_case_as_reprogramado(conn):
    pro, a, c, caso = cancelled_case(conn)
    clock.freeze(caso["abierto_en"] + timedelta(days=3, minutes=1))
    tasks.cycle(conn)
    new = book(conn, a, pro, at(23, "10:00"))
    row = conn.execute("select * from caso_seguimiento").fetchone()
    assert row["estado"] == "reprogramado" and row["cita_resultante_id"] == new
    assert status(conn, c) == "reprogramada"
    assert [r["resultado"] for r in conn.execute("select resultado from intento order by numero")] == ["acepto"]


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
    caso = conn.execute("select * from caso_seguimiento").fetchone()
    assert caso["tipo"] == "inasistencia"
    assert not outbox(conn, a, "seguimiento_inasistencia")  # sin mensaje el día 0
    clock.freeze(caso["abierto_en"] + timedelta(days=3, minutes=1))
    tasks.cycle(conn)
    assert len(outbox(conn, a, "seguimiento_inasistencia")) == 1  # el primero, a los 3 días


def test_la_cadencia_puede_empezar_en_cualquier_dia_y_no_envia_nada_al_abrir(conn):
    from estudia import config
    config.set_(conn, "cadencia_seguimiento_dias", [2, 5])
    pro, a, c, caso = cancelled_case(conn)
    clock.freeze(caso["abierto_en"] + timedelta(days=2, minutes=1))
    tasks.cycle(conn)
    assert len(outbox(conn, a, "seguimiento_reasignacion")) == 1
    assert followup.max_intentos(conn) == 2


def test_los_intentos_manuales_cuentan_para_los_tres_y_cancelan_los_automaticos_que_faltan(conn):
    pro, a, c, caso = cancelled_case(conn)
    clock.freeze(caso["abierto_en"] + timedelta(days=3, minutes=1))
    tasks.cycle(conn)  # intento automatico 1
    followup.register_manual(conn, caso["id"], "sin_respuesta", "Llamada sin contestar")  # 2
    followup.register_manual(conn, caso["id"], "sin_respuesta", "Otra llamada")  # 3
    assert conn.execute("select count(*) n from intento").fetchone()["n"] == 3
    assert conn.execute("select count(*) n from tarea_programada where tipo='intento_seguimiento' and estado='pendiente'").fetchone()["n"] == 0
    clock.freeze(caso["abierto_en"] + timedelta(days=16))
    tasks.cycle(conn)
    assert len(outbox(conn, a, "seguimiento_reasignacion")) == 1  # no salió el de los 7 ni el de los 15 días
    assert conn.execute("select count(*) n from intento").fetchone()["n"] == 3


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


def test_recuperacion_abre_con_volver_a_empezar_y_nombra_al_profesional(conn):
    """R10: los tres textos de recuperación abren igual y nombran al profesional (título + nombre), sin servicio ni montos."""
    pro, a, c, caso = cancelled_case(conn)
    conn.execute("update profesional set titulo='Dra.', nombre='Ana Pérez' where id=%s", (pro,))
    clock.freeze(caso["abierto_en"] + timedelta(days=3, minutes=1))
    tasks.cycle(conn)
    texto = outbox(conn, a, "seguimiento_reasignacion")[0]["texto"]
    assert "Volver a empezar es más fácil acompañado: Dra. Ana Pérez le guarda un espacio." in texto
    assert "Limpieza" not in texto and "$" not in texto
    for clave in ("seguimiento_reasignacion", "seguimiento_inasistencia", "continuidad_tratamiento"):
        from estudia import catalog
        assert catalog.PLANTILLAS[clave][0].startswith("Hola, {nombre}. Volver a empezar es más fácil acompañado: {profesional}")
        for prohibido in ("{servicio}", "{valor}", "diagn"):
            assert prohibido not in catalog.PLANTILLAS[clave][0]


def test_recuperacion_sin_titulo_usa_solo_el_nombre_y_el_tratamiento_aporta_su_profesional(conn):
    pro, a = make_pro(conn, "Ana Pérez"), make_patient(conn)
    trat = conn.execute("insert into tratamiento(paciente_id, profesional_id) values (%s,%s) returning id", (a, pro)).fetchone()["id"]
    caso = followup.open_case(conn, "tratamiento_a_medias", a, tratamiento_id=trat)
    abierto = conn.execute("select abierto_en from caso_seguimiento where id=%s", (caso,)).fetchone()["abierto_en"]
    clock.freeze(abierto + timedelta(days=3, minutes=1))  # open_case no envía: el primer intento sale con la cadencia
    tasks.cycle(conn)
    texto = outbox(conn, a, "continuidad_tratamiento")[0]["texto"]
    assert "acompañado: Ana Pérez le guarda un espacio" in texto
    conn.execute("update profesional set titulo='Dr.' where id=%s", (pro,))
    assert followup._profesional_del_caso(conn, conn.execute("select * from caso_seguimiento").fetchone()) == "Dr. Ana Pérez"
