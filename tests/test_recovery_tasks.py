from datetime import timedelta

from estudia import clock, recovery, tasks
from estudia.tasks import HANDLERS

from .conftest import NOW, at, book, make_patient, make_pro, outbox, svc


def treatment_with_last_visit(conn, days_ago, estado="activo"):
    pro, a = make_pro(conn), make_patient(conn)
    tid = conn.execute("insert into tratamiento(paciente_id, profesional_id, estado) values (%s,%s,%s) returning id",
                       (a, pro, estado)).fetchone()["id"]
    day = (NOW - timedelta(days=days_ago)).date()
    conn.execute("insert into cita(paciente_id, profesional_id, servicio_id, tratamiento_id, dia, estado, origen) "
                 "values (%s,%s,%s,%s,%s,'atendida','importacion')", (a, pro, svc(conn), tid, day))
    return pro, a, tid


def test_detects_active_treatment_without_future_appointment_after_threshold(conn):
    pro, a, tid = treatment_with_last_visit(conn, 40)
    assert [r["tratamiento_id"] for r in recovery.at_risk(conn)] == [tid]
    assert recovery.detect(conn) == 1
    caso = conn.execute("select * from caso_seguimiento").fetchone()
    assert caso["tipo"] == "tratamiento_a_medias" and caso["tratamiento_id"] == tid
    msg = outbox(conn, a, "continuidad_tratamiento")[0]["texto"]
    assert "/p/" in msg and "diagn" not in msg.lower()  # sin detalles clínicos


def test_detection_does_not_duplicate_cases(conn):
    treatment_with_last_visit(conn, 40)
    assert recovery.detect(conn) == 1
    assert recovery.detect(conn) == 0
    assert conn.execute("select count(*) n from caso_seguimiento").fetchone()["n"] == 1


def test_not_at_risk_when_recent_future_or_inactive(conn):
    treatment_with_last_visit(conn, 20)                      # reciente
    treatment_with_last_visit(conn, 60, estado="finalizado")  # no activo
    pro, a, tid = treatment_with_last_visit(conn, 45)
    book(conn, a, pro, at(3, "10:00"))                        # cita futura
    assert recovery.at_risk(conn) == []


def test_daily_run_detects_and_is_executed_once_per_day(conn):
    treatment_with_last_visit(conn, 40)
    first = tasks.cycle(conn)
    assert first["diario"]["casos_recuperacion"] == 1
    assert tasks.cycle(conn)["diario"] is None
    clock.freeze(NOW + timedelta(days=1))
    assert tasks.cycle(conn)["diario"] is not None


def test_failing_task_is_retried_then_marked_failed_and_visible(conn):
    def boom(conn_, d, now):
        raise RuntimeError("falla de prueba")
    HANDLERS["boom"] = boom
    tid = tasks.schedule(conn, "boom", NOW, {})
    for _ in range(4):
        tasks.cycle(conn)
        clock.advance(timedelta(minutes=5))
    row = conn.execute("select estado, intentos, error from tarea_programada where id=%s", (tid,)).fetchone()
    assert row["estado"] == "fallida" and row["intentos"] == 3 and "falla de prueba" in row["error"]
    del HANDLERS["boom"]


def test_cycle_is_idempotent(conn):
    HANDLERS["marca"] = lambda c, d, now: c.execute(
        "insert into solicitud_contacto(documento, celular, momento) values ('x','y',%s)", (now,))
    tasks.schedule(conn, "marca", NOW, {})
    tasks.cycle(conn)
    tasks.cycle(conn)
    assert conn.execute("select count(*) n from solicitud_contacto").fetchone()["n"] == 1
    del HANDLERS["marca"]


def test_two_concurrent_cycles_do_not_run_a_task_twice(conn, conn2):
    HANDLERS["marca"] = lambda c, d, now: c.execute(
        "insert into solicitud_contacto(documento, celular, momento) values ('x','y',%s)", (now,))
    tasks.schedule(conn, "marca", NOW, {})
    conn.commit()
    # El primer ciclo toma la tarea (bloqueada, sin confirmar) y un segundo ciclo la salta.
    assert tasks._run_one(conn) is True
    assert tasks._run_one(conn2) is False
    conn.commit()
    conn2.rollback()
    assert conn.execute("select count(*) n from solicitud_contacto").fetchone()["n"] == 1
    del HANDLERS["marca"]
