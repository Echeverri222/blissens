from datetime import timedelta

import psycopg
import pytest
from psycopg.types.range import Range

from estudia import agenda, config, lifecycle

from .conftest import NOW, at, book, make_patient, make_pro, status, svc


def test_slots_respect_hours_duration_and_min_lead(conn):
    pro = make_pro(conn)
    s30 = agenda.day_slots(conn, pro, svc(conn), NOW.date())
    # Hoy a las 8:00: no se muestran espacios a menos de 2 h
    assert s30[0].hour == 10 and s30[0].minute == 0
    s120 = agenda.day_slots(conn, pro, svc(conn, "Cirugía"), at(1, "08:00").date())
    # 120 min dentro de 7:30-12:00: el último inicio válido es 10:00; en la tarde 13:00-17:30 hasta 15:30
    assert s120[0].strftime("%H:%M") == "07:30"
    assert max(s for s in s120 if s.hour < 13).strftime("%H:%M") == "10:00"
    assert max(s120).strftime("%H:%M") == "15:30"


def test_slots_exclude_live_appointments_blocks_and_pending_offers(conn):
    pro, a = make_pro(conn), make_patient(conn)
    day = at(1, "08:00").date()
    book(conn, a, pro, at(1, "09:00"))
    conn.execute("insert into bloqueo(profesional_id, rango, motivo) values (%s,%s,'viaje')",
                 (pro, Range(at(1, "10:00"), at(1, "11:00"), "[)")))
    slots = [s.strftime("%H:%M") for s in agenda.day_slots(conn, pro, svc(conn), day)]
    assert "09:00" not in slots and "10:00" not in slots and "10:30" not in slots and "11:00" in slots
    assert "08:30" in slots
    # Una cita cancelada libera el espacio
    cid = conn.execute("select id from cita").fetchone()["id"]
    lifecycle.transition(conn, cid, "cancelada", "paciente")
    assert "09:00" in [s.strftime("%H:%M") for s in agenda.day_slots(conn, pro, svc(conn), day)]


def test_slots_not_beyond_horizon(conn):
    pro = make_pro(conn)
    assert agenda.day_slots(conn, pro, svc(conn), (NOW + timedelta(days=61)).date()) == []


def test_booking_overlap_is_rejected_by_database(conn):
    pro, a, b = make_pro(conn), make_patient(conn), make_patient(conn, "Beto")
    book(conn, a, pro, at(1, "09:00"))
    with pytest.raises(agenda.SlotTaken):
        book(conn, b, pro, at(1, "09:00"))
    # Incluso saltándose el código, la base lo impide
    with pytest.raises(psycopg.errors.ExclusionViolation):
        with conn.transaction():
            conn.execute("insert into cita(paciente_id, profesional_id, servicio_id, dia, rango, estado, origen) "
                         "values (%s,%s,%s,%s,%s,'programada','auxiliar')",
                         (b, pro, svc(conn), at(1, "09:00").date(), Range(at(1, "09:15"), at(1, "09:45"), "[)")))


def test_two_people_reserving_same_slot_at_once(conn, conn2):
    pro, a, b = make_pro(conn), make_patient(conn), make_patient(conn, "Beto")
    conn.commit()
    book(conn, a, pro, at(1, "09:00"), notify=False)  # la primera aún sin commit
    with pytest.raises(agenda.SlotTaken):
        # La segunda ve el mismo espacio libre hasta que la primera confirme; al chocar, recibe SlotTaken
        import threading
        err = []

        def second():
            try:
                agenda.book(conn2, b, pro, svc(conn2), at(1, "09:00"), "paciente", "paciente", notify=False)
                conn2.commit()
            except agenda.SlotTaken as e:
                err.append(e)
                conn2.rollback()

        t = threading.Thread(target=second)
        t.start()
        import time
        time.sleep(0.5)
        conn.commit()
        t.join(5)
        assert err
        raise err[0]
    assert conn.execute("select count(*) n from cita").fetchone()["n"] == 1


def test_booking_with_less_than_24h_is_born_confirmed(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c1 = book(conn, a, pro, at(0, "13:00"))   # 5 h
    c2 = book(conn, a, pro, at(3, "09:00"))
    assert status(conn, c1) == "confirmada" and status(conn, c2) == "programada"


def test_reschedule_closes_old_and_links_new(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "09:00"))
    new = agenda.reschedule(conn, c, at(4, "10:00"), "paciente")
    assert status(conn, c) == "reprogramada" and status(conn, new) == "programada"
    assert conn.execute("select cita_anterior_id from cita where id=%s", (new,)).fetchone()["cita_anterior_id"] == c
    # el rango viejo quedó libre y registrado como cupo liberado
    assert conn.execute("select causa from cupo_liberado").fetchone()["causa"] == "cambio_fecha"


def test_reschedule_to_taken_slot_keeps_original(conn):
    pro, a, b = make_pro(conn), make_patient(conn), make_patient(conn, "Beto")
    c = book(conn, a, pro, at(3, "09:00"))
    book(conn, b, pro, at(4, "10:00"))
    with pytest.raises(agenda.SlotTaken):
        agenda.reschedule(conn, c, at(4, "10:00"), "paciente")
    assert status(conn, c) == "programada"


def test_cancel_records_reason_advance_and_late_flag(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c1, c2 = book(conn, a, pro, at(0, "13:00")), book(conn, a, pro, at(3, "09:00"))
    reason = conn.execute("select id from motivo_cancelacion where etiqueta='Viaje'").fetchone()["id"]
    agenda.cancel(conn, c1, "paciente", "enlace", reason_id=reason)
    agenda.cancel(conn, c2, "paciente", "whatsapp")
    rows = conn.execute("select * from cancelacion order by id").fetchall()
    assert rows[0]["tardia"] is True and float(rows[0]["antelacion_horas"]) == 5.0 and rows[0]["motivo_id"] == reason
    assert rows[1]["tardia"] is False and rows[1]["motivo_id"] is None
    config.set_(conn, "umbral_tardia_horas", 100)
    c3 = book(conn, a, pro, at(3, "14:00"))
    agenda.cancel(conn, c3, "paciente", "enlace")
    assert conn.execute("select tardia from cancelacion order by id desc limit 1").fetchone()["tardia"] is True
