"""API de administración: solo administradores, aislada por negocio, con contraseña temporal."""
import pytest
from fastapi.testclient import TestClient

from estudia import data, db, negocios, usuarios
from estudia.api.operacion import limite_cambio_clave, limite_login
from estudia.web.app import app

from .conftest import ADMIN


@pytest.fixture(autouse=True)
def _limpiar_limites():
    limite_login.reiniciar()
    limite_cambio_clave.reiniciar()
    yield
    limite_login.reiniciar()
    limite_cambio_clave.reiniciar()


def _entrar(usuario, clave):
    c = TestClient(app)
    r = c.post("/api/v1/sesion", json={"usuario": usuario, "clave": clave})
    assert r.status_code == 200, r.text
    return c, r.json()


def _preparar(conn):
    data.seed(conn)
    conn.commit()


def test_solo_administradores(conn):
    _preparar(conn)
    esp, _ = _entrar("especialista1", usuarios.DEMO_CLAVE)
    assert esp.get("/api/v1/admin/usuarios").status_code == 403
    adm, _ = _entrar("auxiliar", usuarios.DEMO_CLAVE)
    assert {x["nombre_usuario"] for x in adm.get("/api/v1/admin/usuarios").json()} >= {"auxiliar", "especialista1"}


def test_crear_con_clave_temporal_y_cambio_obligatorio(conn):
    _preparar(conn)
    adm, _ = _entrar("auxiliar", usuarios.DEMO_CLAVE)
    r = adm.post("/api/v1/admin/usuarios", json={"usuario": "nueva", "nombre": "Nueva Auxiliar", "rol": "auxiliar"})
    assert r.status_code == 201
    temporal = r.json()["clave_temporal"]
    c, s = _entrar("nueva", temporal)
    assert s["debe_cambiar_clave"] is True
    assert c.get("/api/v1/agenda?desde=2026-11-16&hasta=2026-11-17").status_code == 403
    misma = c.post("/api/v1/sesion/clave", json={"actual": temporal, "nueva": temporal})
    assert misma.status_code == 422 and misma.json()["codigo"] == "clave_invalida"
    assert c.get("/api/v1/agenda?desde=2026-11-16&hasta=2026-11-17").status_code == 403
    assert c.post("/api/v1/sesion/clave", json={"actual": temporal, "nueva": "otra-clave-larga-1"}).status_code == 200
    assert c.get("/api/v1/pacientes?q=a").status_code == 200


def test_desactivar_y_ultimo_administrador(conn):
    _preparar(conn)
    adm, _ = _entrar("auxiliar", usuarios.DEMO_CLAVE)
    lista = {x["nombre_usuario"]: x for x in adm.get("/api/v1/admin/usuarios").json()}
    assert adm.post(f"/api/v1/admin/usuarios/{lista['auxiliar']['acceso_id']}/desactivar", json={}).status_code == 409
    e = lista["especialista1"]["acceso_id"]
    assert adm.post(f"/api/v1/admin/usuarios/{e}/desactivar").status_code == 422
    assert adm.post(f"/api/v1/admin/usuarios/{e}/desactivar", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert adm.post(f"/api/v1/admin/usuarios/{e}/desactivar", json={}).json()["activo"] is False
    assert adm.post(f"/api/v1/admin/usuarios/{e}/activar", json={}).json()["activo"] is True
    assert adm.post("/api/v1/admin/usuarios/999999/activar", json={}).status_code == 404


def test_no_ve_ni_toca_usuarios_de_otro_negocio(conn):
    _preparar(conn)
    a = db.connect_admin(ADMIN)
    nid = negocios.crear(a, "otro", "Otro Negocio")
    usuarios.crear(a, "ajeno", "Ajeno", "clave-larga-ajena-1", "auxiliar", None, True)
    a.commit()
    ajeno = a.execute("select id from acceso where negocio_id=%s", (nid,)).fetchone()["id"]
    a.close()
    adm, _ = _entrar("auxiliar", usuarios.DEMO_CLAVE)
    assert "ajeno" not in {x["nombre_usuario"] for x in adm.get("/api/v1/admin/usuarios").json()}
    assert adm.post(f"/api/v1/admin/usuarios/{ajeno}/desactivar", json={}).status_code == 404
    assert adm.post(f"/api/v1/admin/usuarios/{ajeno}/clave-temporal", json={}).status_code == 404
