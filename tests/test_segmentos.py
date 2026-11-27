"""Pacientes de alto valor (ficha del reto, §03): internacionales y deportistas de alto nivel. Se marcan en el panel, desde
el software de la clínica o al registrarse en el sitio en inglés, y salen primero en las bandejas de seguimiento."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from estudia import bandejas, data, privacidad, recovery
from estudia.web.app import app

from .conftest import NOW, make_patient
from .test_api import API, entrar, mundo  # noqa: F401  (fixture)
from .test_import import build
from .test_recovery_tasks import treatment_with_last_visit


def marcar(conn, paciente, **marcas):
    conn.execute("update paciente set internacional=%s, deportista=%s where id=%s",
                 (marcas.get("internacional", False), marcas.get("deportista", False), paciente))


def test_en_riesgo_pone_primero_al_paciente_de_alto_valor(conn):
    _, regular, t_regular = treatment_with_last_visit(conn, 90)
    _, vip, t_vip = treatment_with_last_visit(conn, 40)
    assert [r["tratamiento_id"] for r in recovery.at_risk(conn)] == [t_regular, t_vip]  # sin marcas: más días primero
    marcar(conn, vip, deportista=True)
    filas = recovery.at_risk(conn)
    assert [r["tratamiento_id"] for r in filas] == [t_vip, t_regular]
    assert filas[0]["deportista"] and not filas[0]["internacional"]


def test_seguimientos_pone_primero_al_paciente_de_alto_valor(conn):
    regular, vip = make_patient(conn, "Rita", "Regular"), make_patient(conn, "Vera", "Vip")
    for paciente, abierto in ((regular, NOW - timedelta(days=3)), (vip, NOW - timedelta(days=1))):  # el de alto valor, después
        conn.execute("insert into caso_seguimiento(tipo, paciente_id, abierto_en) values ('inasistencia', %s, %s)",
                     (paciente, abierto))
    assert [r["paciente_id"] for r in bandejas.seguimientos(conn)] == [regular, vip]
    marcar(conn, vip, internacional=True)
    filas = bandejas.seguimientos(conn)
    assert [r["paciente_id"] for r in filas] == [vip, regular] and filas[0]["internacional"]


def test_la_recepcion_marca_desde_el_panel_y_queda_registrado(mundo, conn):  # noqa: F811
    r = mundo.aux.put(f"{API}/pacientes/{mundo.p1}/segmentos", json={"internacional": True, "deportista": True})
    assert r.status_code == 200, r.text
    assert r.json()["segmento_origen"] == "recepcion" and r.json()["segmento_marcado_en"]
    ficha = mundo.aux.get(f"{API}/pacientes/{mundo.p1}").json()["paciente"]
    assert ficha["internacional"] and ficha["deportista"] and ficha["segmento_origen"] == "recepcion"
    assert conn.execute("select count(*) n from auditoria_acceso where accion='editar_segmentos' and paciente_id=%s",
                        (mundo.p1,)).fetchone()["n"] == 1
    r = mundo.aux.put(f"{API}/pacientes/{mundo.p1}/segmentos", json={"internacional": False, "deportista": False})
    assert r.json()["internacional"] is False and r.json()["deportista"] is False
    assert mundo.aux.put(f"{API}/pacientes/999999/segmentos", json={"internacional": True, "deportista": False}).status_code == 404
    assert mundo.aux.put(f"{API}/pacientes/{mundo.p1}/segmentos", json={"internacional": "x"}).status_code == 422


@pytest.mark.parametrize("textos, esperado", [
    (("Internacional",), {"internacional": True, "deportista": False}),
    (("Paciente del exterior",), {"internacional": True, "deportista": False}),
    (("Coldeportes",), {"internacional": False, "deportista": False}),
    (("Deportista alto rendimiento",), {"internacional": False, "deportista": True}),
    (("Rehabilitacion", None, float("nan")), {"internacional": False, "deportista": False}),
])
def test_segmentos_de_las_columnas_del_software(textos, esperado):
    assert data.segmentos_de(*textos) == esperado


def test_la_importacion_marca_y_no_pisa_lo_que_decidio_la_recepcion(conn, tmp_path):
    import openpyxl
    build(tmp_path)
    libro = tmp_path / "Agenda y citas .xlsx"
    wb = openpyxl.load_workbook(libro)
    ws = wb.active
    ws.cell(1, ws.max_column + 1, "Tipo Paciente")
    for fila in range(2, ws.max_row + 1):  # paciente 1: internacional; paciente 2: deportista; paciente 3: nada
        ws.cell(fila, ws.max_column, {"1.0": "Internacional", "2.0": "Deportista"}.get(ws.cell(fila, 7).value, "-"))
    wb.save(libro)
    assert data.importar(conn, tmp_path)["segmentados"] == 2
    p = {r["external_id"]: r for r in conn.execute("select * from paciente")}
    assert p["1"]["internacional"] and not p["1"]["deportista"] and p["1"]["segmento_origen"] == "importacion"
    assert p["2"]["deportista"] and not p["3"]["internacional"] and p["3"]["segmento_origen"] is None
    conn.execute("update paciente set internacional=false, segmento_origen='recepcion' where external_id='1'")
    assert data.importar(conn, tmp_path)["segmentados"] == 0  # la recepción lo desmarcó: la importación no lo vuelve a marcar
    assert not conn.execute("select internacional from paciente where external_id='1'").fetchone()["internacional"]


def test_quien_se_registra_en_el_sitio_en_ingles_queda_marcado_como_internacional(conn):
    conn.commit()
    client = TestClient(app, follow_redirects=False)
    for doc, idioma in (("7001", "en"), ("7002", "es")):
        r = client.post("/agendar/identificar", data={"documento": doc, "celular": f"300123{doc}", "nombres": "Luz",
                                                      "consentimiento": "1", "idioma": idioma})
        assert r.status_code == 303, r.text
    p = {r["documento"]: r for r in conn.execute("select * from paciente where documento in ('7001','7002')")}
    assert p["7001"]["internacional"] and p["7001"]["segmento_origen"] == "sitio_en"
    assert not p["7002"]["internacional"] and p["7002"]["segmento_origen"] is None


def test_anonimizar_quita_las_marcas(conn):
    p = make_patient(conn)
    marcar(conn, p, internacional=True, deportista=True)
    privacidad.anonimizar_paciente(conn, p)
    r = conn.execute("select internacional, deportista, segmento_origen from paciente where id=%s", (p,)).fetchone()
    assert not r["internacional"] and not r["deportista"] and r["segmento_origen"] is None
