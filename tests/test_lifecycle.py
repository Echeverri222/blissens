import pytest

from estudia import agenda, lifecycle

from .conftest import at, book, make_patient, make_pro, status


def test_valid_and_invalid_transitions_and_history(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "09:00"))
    lifecycle.transition(conn, c, "confirmada", "paciente")
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.transition(conn, c, "no_confirmada", "sistema")
    lifecycle.transition(conn, c, "atendida", "auxiliar")
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.transition(conn, c, "cancelada", "auxiliar")
    hist = conn.execute("select estado_anterior, estado_nuevo, actor from historial_estado where cita_id=%s order by id",
                        (c,)).fetchall()
    assert [(h["estado_anterior"], h["estado_nuevo"], h["actor"]) for h in hist] == [
        (None, "programada", "auxiliar"), ("programada", "confirmada", "paciente"), ("confirmada", "atendida", "auxiliar")]


def test_cancelled_can_only_become_reprogramada(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "09:00"))
    lifecycle.transition(conn, c, "cancelada", "paciente")
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.transition(conn, c, "confirmada", "paciente")
    lifecycle.transition(conn, c, "reprogramada", "paciente")


def test_revert_outcome_and_cancellation(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "09:00"))
    agenda.cancel(conn, c, "paciente", "enlace")
    h = conn.execute("select id from historial_estado where cita_id=%s and estado_nuevo='cancelada'", (c,)).fetchone()["id"]
    agenda.revert(conn, h)
    assert status(conn, c) == "programada"
    assert conn.execute("select estado from caso_seguimiento").fetchone()["estado"] == "anulado"
    assert conn.execute("select estado from cupo_liberado").fetchone()["estado"] == "anulado"
    with pytest.raises(agenda.CannotRevert):  # ya revertido
        agenda.revert(conn, h)
    # nunca se borra historial
    assert conn.execute("select count(*) n from historial_estado where cita_id=%s", (c,)).fetchone()["n"] == 3


def test_revert_cancellation_fails_if_range_was_taken(conn):
    pro, a, b = make_pro(conn), make_patient(conn), make_patient(conn, "Beto")
    c = book(conn, a, pro, at(3, "09:00"))
    agenda.cancel(conn, c, "paciente", "enlace")
    book(conn, b, pro, at(3, "09:00"))
    h = conn.execute("select id from historial_estado where cita_id=%s and estado_nuevo='cancelada'", (c,)).fetchone()["id"]
    with pytest.raises(agenda.CannotRevert):
        agenda.revert(conn, h)
    assert status(conn, c) == "cancelada"


def test_revert_reschedule_restores_original(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "09:00"))
    new = agenda.reschedule(conn, c, at(4, "10:00"), "paciente")
    h = conn.execute("select id from historial_estado where cita_id=%s and estado_nuevo='reprogramada'", (c,)).fetchone()["id"]
    agenda.revert(conn, h)
    assert status(conn, c) == "programada" and status(conn, new) == "cancelada"
