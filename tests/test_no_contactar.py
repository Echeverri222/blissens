"""R6 del PRD de respuestas de la clínica: «No contactar». Los efectos se hacen cumplir en el dominio, no solo en el panel."""
from datetime import timedelta

import pytest

from estudia import agenda, bandejas, clock, messaging, pacientes, recovery, tasks

from .conftest import NOW, at, book, make_patient, make_pro, outbox
from .test_api import API, mundo  # noqa: F401  (fixture)
from .test_recovery_tasks import treatment_with_last_visit


def estado_de(conn, mid):
    return conn.execute("select estado_entrega, detalle from mensaje where id=%s", (mid,)).fetchone()


def test_no_contactar_omite_lo_automatico_pero_deja_pasar_la_respuesta_directa(conn):
    a = make_patient(conn)
    assert pacientes.contactable(conn, a)
    pacientes.no_contactar(conn, a, "cobro", "Cartera", None)
    assert not pacientes.contactable(conn, a)
    auto = messaging.send(conn, a, "baja_confirmada")
    assert dict(estado_de(conn, auto)) == {"estado_entrega": "omitido", "detalle": "no_contactar"}
    assert estado_de(conn, messaging.send(conn, a, "baja_confirmada", direct=True))["estado_entrega"] == "entregado"
    pacientes.quitar_no_contactar(conn, a)
    assert pacientes.contactable(conn, a)
    assert estado_de(conn, messaging.send(conn, a, "baja_confirmada"))["estado_entrega"] == "entregado"


def test_fallecido_bloquea_hasta_las_respuestas_directas(conn):
    a = make_patient(conn)
    pacientes.no_contactar(conn, a, "fallecido", None, None)
    assert estado_de(conn, messaging.send(conn, a, "baja_confirmada", direct=True))["estado_entrega"] == "omitido"


def test_motivo_invalido_y_paciente_inexistente(conn):
    a = make_patient(conn)
    with pytest.raises(pacientes.DatosInvalidos):
        pacientes.no_contactar(conn, a, "caprichos", None, None)
    assert pacientes.no_contactar(conn, 999999, "otro", None, None) is None


def test_marcarlo_cierra_como_anulados_sus_casos_abiertos_y_no_abre_nuevos(conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(22, "10:00"))
    agenda.cancel(conn, c, "paciente", "enlace")
    assert conn.execute("select estado from caso_seguimiento").fetchone()["estado"] == "abierto"
    pacientes.no_contactar(conn, a, "queja", None, None)
    assert conn.execute("select estado from caso_seguimiento").fetchone()["estado"] == "anulado"
    c2 = book(conn, a, pro, at(23, "10:00"))
    agenda.cancel(conn, c2, "paciente", "enlace")
    assert conn.execute("select count(*) n from caso_seguimiento").fetchone()["n"] == 1  # no se abrió otro
    clock.freeze(NOW + timedelta(days=4))
    tasks.cycle(conn)
    assert not outbox(conn, a, "seguimiento_reasignacion")


def test_sale_de_las_listas_de_trabajo(conn):
    pro = make_pro(conn)
    a, b = make_patient(conn, "Ana"), make_patient(conn, "Beto")
    ca, cb = book(conn, a, pro, at(1, "10:00")), book(conn, b, pro, at(1, "11:00"))
    conn.execute("update cita set estado='no_confirmada' where id = any(%s)", ([ca, cb],))
    assert {r["paciente_id"] for r in bandejas.no_confirmadas(conn)} == {a, b}
    pacientes.no_contactar(conn, a, "otro", None, None)
    assert {r["paciente_id"] for r in bandejas.no_confirmadas(conn)} == {b}
    _, riesgo, _ = treatment_with_last_visit(conn, 90)
    assert [r["paciente_id"] for r in recovery.at_risk(conn)] == [riesgo]
    pacientes.no_contactar(conn, riesgo, "cobro", None, None)
    assert recovery.at_risk(conn) == []


def test_ofertas_de_adelanto_no_van_al_que_no_se_contacta(conn):
    pro, libera, candidato = make_pro(conn), make_patient(conn, "Lia"), make_patient(conn, "Cai")
    c1 = book(conn, libera, pro, at(2, "09:00"))
    book(conn, candidato, pro, at(3, "09:00"))
    pacientes.no_contactar(conn, candidato, "cobro", None, None)
    agenda.cancel(conn, c1, "paciente", "enlace")
    assert conn.execute("select count(*) n from oferta_adelanto").fetchone()["n"] == 0


def test_el_fallecido_no_sale_en_la_busqueda_salvo_que_se_pida(conn):
    a = make_patient(conn, "Fabio", "Difunto")
    pacientes.no_contactar(conn, a, "fallecido", None, None)
    assert bandejas.find_patients(conn, "difunto") == []
    assert [r["id"] for r in bandejas.find_patients(conn, "difunto", con_fallecidos=True)] == [a]
    pacientes.quitar_no_contactar(conn, a)
    assert [r["id"] for r in bandejas.find_patients(conn, "difunto")] == [a]


def test_no_se_agenda_a_un_fallecido(conn):
    pro, a = make_pro(conn), make_patient(conn)
    pacientes.no_contactar(conn, a, "fallecido", None, None)
    with pytest.raises(pacientes.DatosInvalidos):
        book(conn, a, pro, at(3, "10:00"))


def test_el_panel_marca_y_quita_con_auditoria(mundo, conn):  # noqa: F811
    r = mundo.aux.put(f"{API}/pacientes/{mundo.p1}/no-contactar", json={"motivo": "cobro", "nota": "En cartera"})
    assert r.status_code == 200, r.text
    assert r.json()["no_contactar"] == "cobro" and r.json()["no_contactar_nota"] == "En cartera"
    ficha = mundo.aux.get(f"{API}/pacientes/{mundo.p1}").json()["paciente"]
    assert ficha["no_contactar"] == "cobro" and ficha["no_contactar_en"]
    r = mundo.aux.delete(f"{API}/pacientes/{mundo.p1}/no-contactar")
    assert r.status_code == 200 and r.json()["no_contactar"] is None
    acciones = [x["accion"] for x in conn.execute(
        "select accion from auditoria_acceso where paciente_id=%s order by id", (mundo.p1,))]
    assert "marcar_no_contactar" in acciones and "quitar_no_contactar" in acciones
    assert mundo.aux.put(f"{API}/pacientes/{mundo.p1}/no-contactar", json={"motivo": "x"}).status_code == 422
    assert mundo.aux.put(f"{API}/pacientes/999999/no-contactar", json={"motivo": "otro"}).status_code == 404


def test_la_busqueda_del_panel_oculta_fallecidos_hasta_pedirlos(mundo, conn):  # noqa: F811
    mundo.aux.put(f"{API}/pacientes/{mundo.p1}/no-contactar", json={"motivo": "fallecido"})
    nombre = conn.execute("select nombres from paciente where id=%s", (mundo.p1,)).fetchone()["nombres"].split()[0]
    sin = [p["id"] for p in mundo.aux.get(f"{API}/pacientes", params={"q": nombre}).json()]
    assert mundo.p1 not in sin
    con = [p["id"] for p in mundo.aux.get(f"{API}/pacientes", params={"q": nombre, "fallecidos": "true"}).json()]
    assert mundo.p1 in con
