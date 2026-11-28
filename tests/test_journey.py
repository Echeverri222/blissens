"""Recorrido de aceptación (PRD §3.4) con reloj falso y canal simulado."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from estudia import agenda, clock, indicators, recovery, tasks
from estudia.web.app import app

from .conftest import NOW, at, book, button, make_patient, make_pro, outbox, press, status, svc


def test_full_acceptance_journey(conn):
    pro = make_pro(conn)
    # Datos de partida: pacientes con citas a distintos plazos y un tratamiento a medias
    p2, p3, p4, p5 = (make_patient(conn, n) for n in ("Dos", "Tres", "Cuatro", "Cinco"))
    c2 = book(conn, p2, pro, at(3, "11:00"))
    c4 = book(conn, p4, pro, at(8, "10:00"))      # cita posterior -> candidata más lejana
    c5 = book(conn, p5, pro, at(7, "10:00"))
    riesgo = make_patient(conn, "Riesgo")
    tid = conn.execute("insert into tratamiento(paciente_id, profesional_id, estado) values (%s,%s,'activo') returning id",
                       (riesgo, pro)).fetchone()["id"]
    conn.execute("insert into cita(paciente_id, profesional_id, servicio_id, tratamiento_id, dia, estado, origen) values "
                 "(%s,%s,%s,%s,%s,'atendida','importacion')", (riesgo, pro, svc(conn), tid, (NOW - timedelta(days=45)).date()))
    conn.commit()
    client = TestClient(app, follow_redirects=False)

    # 1. Paciente nuevo agenda desde /agendar
    r = client.post("/agendar/identificar", data={"documento": "55555", "celular": "3005550000", "nombres": "Nuevo",
                                                  "apellidos": "Paciente", "consentimiento": "1"})
    token = r.headers["location"].split("/")[2]
    client.post(f"/p/{token}/agendar", data={"servicio": svc(conn), "profesional": pro, "inicio": at(3, "10:00").isoformat()})
    conn.rollback()
    c1 = conn.execute("select id, paciente_id from cita where paciente_id not in (%s,%s,%s,%s,%s)",
                      (p2, p3, p4, p5, riesgo)).fetchone()
    p1 = c1["paciente_id"]
    assert outbox(conn, p1, "cita_agendada")

    # 2. 48 h antes: recordatorio con tres botones; "Sí, asistiré" -> confirmada
    clock.freeze(at(3, "10:00") - timedelta(hours=48) + timedelta(minutes=1))
    tasks.cycle(conn)
    assert len(outbox(conn, p1, "recordatorio_48h")[0]["botones"]) == 3
    press(conn, p1, button(conn, p1, "recordatorio_48h", 0))
    assert status(conn, c1["id"]) == "confirmada"

    # 3. Otra cita sin respuesta: a 24 h queda no confirmada con segundo intento
    clock.freeze(at(3, "11:00") - timedelta(hours=24) + timedelta(minutes=1))
    tasks.cycle(conn)
    assert status(conn, c2) == "no_confirmada" and outbox(conn, p2, "segundo_intento")

    # 4. Cancelar desde el enlace con motivo de un toque; se ofrecen espacios; sale sin elegir
    motivo = conn.execute("select id from motivo_cancelacion where etiqueta='Trabajo o estudio'").fetchone()["id"]
    conn.commit()
    r = client.post(f"/p/{token}/cancelar/{c1['id']}", data={"motivo": motivo})
    assert "Elija su espacio" in r.text
    conn.rollback()
    cancelled_at = clock.now(conn)
    assert status(conn, c1["id"]) == "cancelada"

    # 5. Oferta de adelanto al candidato más lejano; vence y pasa al siguiente; el siguiente acepta; cadena
    assert len(outbox(conn, p4, "oferta_adelanto")) == 1
    clock.advance(timedelta(minutes=31))
    tasks.cycle(conn)
    assert len(outbox(conn, p5, "oferta_adelanto")) == 1
    press(conn, p5, button(conn, p5, "oferta_adelanto", 0))
    assert status(conn, c5) == "reprogramada"
    nueva5 = conn.execute("select * from cita where cita_anterior_id=%s", (c5,)).fetchone()
    assert nueva5["rango"].lower == at(3, "10:00")
    assert len(outbox(conn, p4, "oferta_adelanto")) == 2   # el espacio que dejó dispara la cadena

    # 6. +3 días: primer seguimiento de reasignación; el paciente agenda desde el enlace y el caso se cierra
    clock.freeze(cancelled_at + timedelta(days=3, minutes=1))
    tasks.cycle(conn)
    assert len(outbox(conn, p1, "seguimiento_reasignacion")) == 1
    conn.commit()
    client.post(f"/p/{token}/agendar", data={"servicio": svc(conn), "profesional": pro, "inicio": at(10, "09:00").isoformat()})
    conn.rollback()
    caso = conn.execute("select estado from caso_seguimiento where paciente_id=%s", (p1,)).fetchone()
    assert caso["estado"] == "reprogramado"

    # 7. El panel marca una cita como no asistió y otra como atendida (el día de la cita)
    clock.freeze(at(3, "13:00"))
    agenda.mark_outcome(conn, c2, "no_asistio")
    agenda.mark_outcome(conn, nueva5["id"], "atendida")
    assert status(conn, c2) == "no_asistio" and status(conn, nueva5["id"]) == "atendida"

    # 8. Pacientes en riesgo: tratamiento activo sin cita futura, con su mensaje de recuperación
    tasks.cycle(conn)
    assert [r["paciente_id"] for r in recovery.at_risk(conn)] == [riesgo]
    assert outbox(conn, riesgo, "continuidad_tratamiento")

    # 9. Cierre e indicadores reflejan lo ocurrido
    first = conn.execute("select min(dia) d from cita").fetchone()["d"]
    indicators.close_range(conn, first, clock.now(conn).date())
    s = indicators.summary(conn, {"desde": first, "hasta": clock.now(conn).date(), "profesional_id": None})
    assert s["inasistencia"] == 1 / 3 and s["cancelaciones"] == 1 and s["cancelaciones_recuperadas"] == 1
    assert s["recuperacion"] == 1.0
    assert {r["motivo"] for r in indicators.reasons(conn, {"desde": first, "hasta": clock.now(conn).date()})} == {"Trabajo o estudio"}
    assert s["cupos_ocupados_oferta"] >= 1

    # 10. Ficha del paciente: bitácora completa e historial; revertir el adelanto del paso 5
    log = conn.execute("select count(*) n from mensaje where paciente_id=%s", (p5,)).fetchone()["n"]
    assert log >= 2
    h = conn.execute("select id from historial_estado where cita_id=%s and estado_nuevo='reprogramada'", (c5,)).fetchone()["id"]
    # la cita adelantada ya fue atendida: no se puede revertir sobre una cita cerrada
    with pytest.raises(agenda.CannotRevert):
        agenda.revert(conn, h)
