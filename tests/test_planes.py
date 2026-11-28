"""R14 del PRD de respuestas de la clínica: plan entregado, abonos y acompañamiento sin cobrar."""
from datetime import timedelta

import pytest

from estudia import clock, followup, pacientes, planes, tasks

from .conftest import NOW, at, book, button, make_patient, make_pro, outbox, press
from .test_api import API, mundo  # noqa: F401  (fixture)

PALABRAS_PROHIBIDAS = ("deuda", "cobro", "saldo", "pago", "$", "abono", "valor")


def tratamiento(conn, paciente, pro, sesiones=6):
    return conn.execute("insert into tratamiento(paciente_id, profesional_id, sesiones_previstas) values (%s,%s,%s) "
                        "returning id", (paciente, pro, sesiones)).fetchone()["id"]


def caso_plan(conn):
    return conn.execute("select * from caso_seguimiento where tipo='plan' order by id desc").fetchone()


def test_plan_entregado_abre_caso_con_cadencia_3_7_y_mensajes_sin_dinero(conn):
    pro, a = make_pro(conn, "Dr. Rojas"), make_patient(conn)
    t = tratamiento(conn, a, pro)
    r = planes.plan_entregado(conn, a, t, valor=4500000)
    assert r["caso_id"] and caso_plan(conn)["tratamiento_id"] == t
    assert not outbox(conn, a, "plan_acompanamiento_1")  # nada al abrir
    caso = caso_plan(conn)
    clock.freeze(caso["abierto_en"] + timedelta(days=3, minutes=1))
    tasks.cycle(conn)
    clock.freeze(caso["abierto_en"] + timedelta(days=7, minutes=1))
    tasks.cycle(conn)
    m1, m2 = outbox(conn, a, "plan_acompanamiento_1"), outbox(conn, a, "plan_acompanamiento_2")
    assert len(m1) == 1 and len(m2) == 1
    for m in (m1[0], m2[0]):
        assert "Dr. Rojas" in m["texto"] and not any(w in m["texto"].lower() for w in PALABRAS_PROHIBIDAS)
        assert "4500000" not in m["texto"]
    assert "/p/" in m1[0]["texto"]


def test_ahora_no_cierra_como_rechazado(conn):
    pro, a = make_pro(conn), make_patient(conn)
    r = planes.plan_entregado(conn, a, tratamiento(conn, a, pro))
    clock.freeze(caso_plan(conn)["abierto_en"] + timedelta(days=3, minutes=1))
    tasks.cycle(conn)
    press(conn, a, button(conn, a, "plan_acompanamiento_1"))
    assert caso_plan(conn)["estado"] == "rechazado" and caso_plan(conn)["id"] == r["caso_id"]


def test_agendar_con_ese_profesional_lo_cierra_como_reprogramado_y_con_otro_no(conn):
    pro, otro, a = make_pro(conn, "Dr. Uno"), make_pro(conn, "Dr. Dos"), make_patient(conn)
    planes.plan_entregado(conn, a, tratamiento(conn, a, pro))
    book(conn, a, otro, at(2, "10:00"))
    assert caso_plan(conn)["estado"] == "abierto"
    cita = book(conn, a, pro, at(3, "10:00"))
    c = caso_plan(conn)
    assert c["estado"] == "reprogramado" and c["cita_resultante_id"] == cita


def test_no_contactar_y_prospecto_quedan_fuera(conn):
    pro, a = make_pro(conn), make_patient(conn)
    t = tratamiento(conn, a, pro)
    pacientes.no_contactar(conn, a, "cobro", None, None)
    assert planes.plan_entregado(conn, a, t)["caso_id"] is None
    clock.freeze(NOW + timedelta(days=20))
    assert planes.sin_siguiente_paso(conn) == []
    pros, _ = pacientes.atender_solicitud(conn, nombre="Pro Specto", correo="p@example.com", celular=None)
    with pytest.raises(planes.PlanInvalido):
        planes.plan_entregado(conn, pros, tratamiento(conn, pros, pro))


def test_abono_con_sesiones_pendientes_reabre_el_caso(conn):
    pro, a = make_pro(conn), make_patient(conn)
    t = tratamiento(conn, a, pro, sesiones=4)
    planes.plan_entregado(conn, a, t)
    followup.decline(conn, caso_plan(conn)["id"])
    r = planes.registrar_abono(conn, a, t)
    assert r["caso_id"] and caso_plan(conn)["estado"] == "abierto"
    assert conn.execute("select ultimo_abono_en from tratamiento where id=%s", (t,)).fetchone()["ultimo_abono_en"]


def test_bandeja_planes_sin_siguiente_paso_orden_y_exclusiones(conn):
    pro = make_pro(conn)
    a, b, c, d = (make_patient(conn, n) for n in ("Ana", "Beto", "Cai", "Dani"))
    conn.execute("update paciente set deportista=true where id=%s", (d,))
    ts = {x: tratamiento(conn, x, pro) for x in (a, b, c, d)}
    for x, valor in ((a, 1000000), (b, 5000000), (c, 9000000), (d, 100)):
        planes.plan_entregado(conn, x, ts[x], None, valor)
    clock.freeze(NOW + timedelta(days=8))
    book(conn, c, pro, at(10, "10:00"))  # tiene siguiente paso
    planes.registrar_abono(conn, a, ts[a])  # abono posterior a la entrega
    conn.execute("update tratamiento set ultimo_abono_en = %s where id=%s", (clock.now(conn), ts[a]))
    assert [r["paciente_id"] for r in planes.sin_siguiente_paso(conn)] == [d, b]  # alto valor primero, luego valor_plan
    clock.freeze(NOW + timedelta(days=3))
    assert planes.sin_siguiente_paso(conn) == []  # aún no pasan 7 días


def test_indicador_planes(conn):
    pro = make_pro(conn)
    a, b = make_patient(conn, "Ana"), make_patient(conn, "Beto")
    planes.plan_entregado(conn, a, tratamiento(conn, a, pro), valor=2000000)
    planes.plan_entregado(conn, b, tratamiento(conn, b, pro), valor=3000000)
    book(conn, a, pro, at(2, "10:00"))
    r = planes.resumen_periodo(conn, NOW.date(), NOW.date())
    assert r == {"entregados": 2, "con_siguiente_paso": 1, "conversion_pct": 50.0, "valor_sin_siguiente_paso": 3000000}
    vacio = planes.resumen_periodo(conn, NOW.date() - timedelta(days=90), NOW.date() - timedelta(days=60))
    assert vacio["entregados"] == 0 and vacio["conversion_pct"] is None and vacio["valor_sin_siguiente_paso"] is None


def test_api_plan_abono_ficha_y_auditoria(conn, mundo):
    t = tratamiento(conn, mundo.p1, mundo.pro1)
    conn.commit()
    r = mundo.aux.put(f"{API}/pacientes/{mundo.p1}/tratamientos/{t}/plan-entregado", json={"valor_plan": 800000})
    assert r.status_code == 200 and r.json()["caso_id"]
    assert mundo.aux.put(f"{API}/pacientes/{mundo.p1}/tratamientos/{t}/abono", json={}).status_code == 200
    ficha = mundo.aux.get(f"{API}/pacientes/{mundo.p1}").json()
    assert ficha["tratamientos"][0]["valor_plan"] == 800000 and ficha["tratamientos"][0]["ultimo_abono_en"]
    acciones = {x["accion"] for x in conn.execute("select accion from auditoria_acceso").fetchall()}
    assert {"plan_entregado", "registrar_abono"} <= acciones
    assert mundo.aux.put(f"{API}/pacientes/{mundo.p2}/tratamientos/{t}/abono", json={}).status_code == 404
    assert mundo.aux.put(f"{API}/pacientes/{mundo.p1}/tratamientos/{t}/plan-entregado",
                         json={"valor_plan": -1}).status_code == 422
    assert mundo.aux.get(f"{API}/indicadores/planes").json()["entregados"] == 1
    assert mundo.aux.get(f"{API}/bandejas").json()["planes"] == 0
    assert mundo.esp1.put(f"{API}/pacientes/{mundo.p1}/tratamientos/{t}/abono", json={}).status_code == 403
