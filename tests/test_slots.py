from datetime import timedelta

import psycopg
import pytest

from estudia import agenda, clock, config, slots, tasks

from .conftest import NOW, at, book, button, make_patient, make_pro, outbox, press, status, svc


def setup_three(conn):
    """Un profesional con tres pacientes con citas el martes, miércoles y jueves a las 10:00."""
    pro = make_pro(conn)
    a, b, c = (make_patient(conn, n, doc=d) for n, d in (("Ana", "1"), ("Beto", "2"), ("Carla", "3")))
    ca, cb, cc = (book(conn, p, pro, at(i, "10:00")) for i, p in ((1, a), (2, b), (3, c)))
    return pro, (a, b, c), (ca, cb, cc)


def free_slot(conn, pro, day=1, hhmm="14:00"):
    return slots.register_slot(conn, pro, agenda.rng(at(day, hhmm), 30), None, "cancelacion")


def test_offer_goes_to_farthest_appointment_first(conn):
    pro, (a, b, c), _ = setup_three(conn)
    free_slot(conn, pro, 0, "14:00")
    assert len(outbox(conn, c, "oferta_adelanto")) == 1
    assert not outbox(conn, a, "oferta_adelanto") and not outbox(conn, b, "oferta_adelanto")
    text = outbox(conn, c, "oferta_adelanto")[0]["texto"]
    assert "podría adelantarse" in text and "¿Desea hacerlo?" in text


def test_only_one_pending_offer_per_slot(conn):
    pro, _, _ = setup_three(conn)
    cupo = free_slot(conn, pro, 0, "14:00")
    assert slots.next_offer(conn, cupo) is None  # ya hay una pendiente
    with pytest.raises(psycopg.errors.UniqueViolation):
        with conn.transaction():
            conn.execute("insert into oferta_adelanto(cupo_id, cita_id, orden, enviada_en, vence_en) "
                         "select cupo_id, cita_id, 9, enviada_en, vence_en from oferta_adelanto limit 1")


def test_pending_offer_hides_slot_from_normal_booking(conn):
    pro, _, _ = setup_three(conn)
    free_slot(conn, pro, 1, "14:00")
    assert at(1, "14:00") not in agenda.day_slots(conn, pro, svc(conn), at(1, "14:00").date())
    d = make_patient(conn, "Dani", doc="4")
    with pytest.raises(agenda.SlotTaken):
        book(conn, d, pro, at(1, "14:00"))


def test_rejection_and_expiry_pass_to_next_candidate(conn):
    pro, (a, b, c), _ = setup_three(conn)
    free_slot(conn, pro, 0, "14:00")
    press(conn, c, button(conn, c, "oferta_adelanto", 1))  # No, gracias
    assert len(outbox(conn, b, "oferta_adelanto")) == 1
    clock.advance(timedelta(minutes=31))
    tasks.cycle(conn)
    assert len(outbox(conn, a, "oferta_adelanto")) == 1
    states = [r["estado"] for r in conn.execute("select estado from oferta_adelanto order by id")]
    assert states == ["rechazada", "vencida", "pendiente"]


def test_exhausted_candidates_leave_slot_open_and_visible(conn):
    pro, (a, b, c), _ = setup_three(conn)
    cupo = free_slot(conn, pro, 0, "14:00")
    for p in (c, b, a):
        press(conn, p, button(conn, p, "oferta_adelanto", 1))
    row = conn.execute("select estado from cupo_liberado where id=%s", (cupo,)).fetchone()
    assert row["estado"] == "abierto"
    assert at(0, "14:00") in agenda.day_slots(conn, pro, svc(conn), at(0, "14:00").date())


def test_accept_moves_appointment_and_chains(conn):
    pro, (a, b, c), (ca, cb, cc) = setup_three(conn)
    d = make_patient(conn, "Dani", doc="4")
    book(conn, d, pro, at(4, "10:00"))
    free_slot(conn, pro, 0, "14:00")
    press(conn, d, button(conn, d, "oferta_adelanto", 1))   # la más lejana rechaza
    press(conn, c, button(conn, c, "oferta_adelanto", 0))   # Sí, adelantarla
    assert status(conn, cc) == "reprogramada"
    new = conn.execute("select * from cita where cita_anterior_id=%s", (cc,)).fetchone()
    assert new["rango"].lower == at(0, "14:00") and new["estado"] == "programada"
    assert outbox(conn, c, "adelanto_confirmado")
    # El rango que dejó (jueves 10:00) queda libre y se ofrece en cadena a quien tiene cita posterior
    assert len(outbox(conn, d, "oferta_adelanto")) == 2
    cupos = conn.execute("select causa, estado from cupo_liberado order by id").fetchall()
    assert [(r["causa"], r["estado"]) for r in cupos] == [("cancelacion", "ocupado"), ("adelanto", "en_oferta")]


def test_late_response_to_expired_offer_keeps_original(conn):
    pro, (a, b, c), (ca, cb, cc) = setup_three(conn)
    free_slot(conn, pro, 0, "14:00")
    btn = button(conn, c, "oferta_adelanto", 0)
    clock.advance(timedelta(minutes=45))
    press(conn, c, btn)
    assert status(conn, cc) == "programada"
    assert "ya no está disponible" in outbox(conn, c, "oferta_no_disponible")[-1]["texto"]


def test_two_simultaneous_accepts_only_one_wins(conn, conn2):
    pro, (a, b, c), (ca, cb, cc) = setup_three(conn)
    cupo = free_slot(conn, pro, 0, "14:00")
    o1 = conn.execute("select id from oferta_adelanto").fetchone()["id"]
    conn.commit()
    assert slots.accept(conn, o1) is True
    conn.commit()
    assert slots.accept(conn2, o1) is False  # ya no está pendiente
    assert conn2.execute("select count(*) n from cita where rango && %s and estado<>'cancelada' and estado<>'reprogramada'",
                         (agenda.rng(at(0, "14:00"), 30),)).fetchone()["n"] == 1


def test_slot_taken_by_normal_booking_closes_as_occupied(conn):
    pro, (a, b, c), _ = setup_three(conn)
    cupo = free_slot(conn, pro, 1, "14:00")
    for p in (c, b):
        press(conn, p, button(conn, p, "oferta_adelanto", 1))
    d = make_patient(conn, "Dani", doc="4")
    book(conn, d, pro, at(1, "14:00"))
    clock.advance(timedelta(days=1, hours=7))
    tasks.cycle(conn)
    row = conn.execute("select estado, ocupado_por from cupo_liberado where id=%s", (cupo,)).fetchone()
    assert (row["estado"], row["ocupado_por"]) == ("ocupado", "agendamiento")


def test_unfilled_slot_closes_as_empty(conn):
    pro, _, _ = setup_three(conn)
    cupo = slots.register_slot(conn, pro, agenda.rng(at(1, "14:00"), 30), None, "cancelacion")
    clock.advance(timedelta(days=1, hours=7))
    tasks.cycle(conn)
    assert conn.execute("select estado from cupo_liberado where id=%s", (cupo,)).fetchone()["estado"] == "vacio"


def test_candidate_rules(conn):
    pro = make_pro(conn)
    ok = make_patient(conn, "Ok", doc="1")
    baja = make_patient(conn, "Baja", doc="2", acepta=False)
    mismo_dia = make_patient(conn, "Mismodia", doc="3")
    book(conn, ok, pro, at(2, "10:00"))
    book(conn, baja, pro, at(2, "11:00"))
    book(conn, mismo_dia, pro, at(2, "09:00"))
    book(conn, mismo_dia, pro, at(1, "09:00"))  # ya tiene cita el día del cupo
    anterior = make_patient(conn, "Antes", doc="5")
    book(conn, anterior, pro, at(1, "08:00"))   # cita anterior al cupo: no es candidata
    long_ = make_patient(conn, "Larga", doc="6")
    book(conn, long_, pro, at(3, "10:00"), service="Cirugía")  # no admite adelanto
    cupo = free_slot(conn, pro, 1, "14:00")
    offered = {r["nombres"] for r in conn.execute(
        "select p.nombres from oferta_adelanto o join cita c on c.id=o.cita_id join paciente p on p.id=c.paciente_id")}
    assert offered == {"Ok"}


def test_slot_with_less_than_min_lead_is_registered_but_not_offered(conn):
    pro, _, _ = setup_three(conn)
    cupo = slots.register_slot(conn, pro, agenda.rng(NOW + timedelta(minutes=90), 30), None, "cancelacion")
    assert conn.execute("select count(*) n from oferta_adelanto").fetchone()["n"] == 0
    assert conn.execute("select estado from cupo_liberado where id=%s", (cupo,)).fetchone()["estado"] == "abierto"


def test_max_offers_per_slot(conn):
    pro = make_pro(conn)
    ps = [make_patient(conn, f"P{i}", doc=str(i)) for i in range(1, 8)]
    for p, day in zip(ps, [1, 2, 3, 4, 8, 9, 10]):
        book(conn, p, pro, at(day, "10:00"))
    config.set_(conn, "max_ofertas_por_cupo", 2)
    cupo = free_slot(conn, pro, 0, "14:00")
    for _ in range(3):
        o = conn.execute("select id, cita_id from oferta_adelanto where estado='pendiente'").fetchone()
        if o:
            slots.reject(conn, o["id"])
    assert conn.execute("select count(*) n from oferta_adelanto where cupo_id=%s", (cupo,)).fetchone()["n"] == 2


def test_weekly_offer_limit_per_patient(conn):
    pro = make_pro(conn)
    p = make_patient(conn, "Solo", doc="1")
    book(conn, p, pro, at(3, "10:00"))
    for i in range(3):
        cupo = free_slot(conn, pro, 0, ["14:00", "14:30", "15:00"][i])
        o = conn.execute("select id from oferta_adelanto where cupo_id=%s and estado='pendiente'", (cupo,)).fetchone()
        if o:
            slots.reject(conn, o["id"])
    assert conn.execute("select count(*) n from oferta_adelanto").fetchone()["n"] == 2
