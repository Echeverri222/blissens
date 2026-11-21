"""Pruebas de la API REST pública del paciente: /api/v1/publico/*."""
import pytest
from fastapi.testclient import TestClient

from estudia import links
from estudia.web.app import app

from .conftest import at, book, make_patient, make_pro, svc

API = "/api/v1/publico"


@pytest.fixture
def client(conn):
    conn.commit()
    return TestClient(app, follow_redirects=False)


def test_identificar_nuevo_paciente_requiere_registro_y_consentimiento(client, conn):
    # Sin nombres -> requiere registro
    r = client.post(f"{API}/identificar", json={"documento": "100200300", "celular": "3001234567"})
    assert r.status_code == 200
    assert r.json()["estado"] == "requiere_registro"

    # Con nombres pero sin consentimiento -> 422 requiere_consentimiento
    r = client.post(f"{API}/identificar", json={
        "documento": "100200300", "celular": "3001234567",
        "nombres": "Camila", "apellidos": "Torres", "consentimiento": False
    })
    assert r.status_code == 422
    assert r.json()["codigo"] == "requiere_consentimiento"

    # Con consentimiento -> registrado y entrega token
    r = client.post(f"{API}/identificar", json={
        "documento": "100200300", "celular": "3001234567",
        "nombres": "Camila", "apellidos": "Torres", "consentimiento": True
    })
    assert r.status_code == 200
    data = r.json()
    assert data["estado"] == "registrado"
    assert data["token"] is not None
    assert data["paciente"]["nombres"] == "Camila"


def test_identificar_paciente_existente_con_mismo_celular_retorna_token(client, conn):
    p = make_patient(conn, "Carlos", "Rojas", doc="888999", celular="+573112223344")
    conn.commit()

    r = client.post(f"{API}/identificar", json={"documento": "888999", "celular": "3112223344"})
    assert r.status_code == 200
    data = r.json()
    assert data["estado"] == "autenticado"
    assert data["token"] is not None
    assert data["paciente"]["id"] == p


def test_identificar_documento_con_otro_celular_genera_contacto_sin_revelar_datos(client, conn):
    make_patient(conn, "Diana", "Lopez", doc="555666", celular="+573001112233")
    conn.commit()

    r = client.post(f"{API}/identificar", json={"documento": "555666", "celular": "3209998877"})
    assert r.status_code == 200
    data = r.json()
    assert data["estado"] == "contacto_pendiente"
    assert data["token"] is None
    assert "contacto" in data["mensaje"]


def test_mis_citas_y_agendar_y_cambiar_y_cancelar_ciclo_completo(client, conn):
    pro = make_pro(conn, "Dra. Blissens")
    p = make_patient(conn, "Valeria", "Duque", doc="111222", celular="+573004445566")
    sid = svc(conn)
    conn.commit()

    token = links.make_token(p, conn=conn)

    # 1. Consultar citas (inicialmente vacías)
    r = client.get(f"{API}/citas", params={"token": token})
    assert r.status_code == 200
    data = r.json()
    assert data["paciente"]["nombres"] == "Valeria"
    assert len(data["citas"]) == 0

    # 2. Consultar espacios
    r = client.get(f"{API}/espacios", params={"token": token, "servicio_id": sid, "profesional_id": pro})
    assert r.status_code == 200
    esp = r.json()
    assert len(esp["dias"]) > 0
    primer_dia = esp["dias"][0]
    hora_elegida = primer_dia["horas"][0]

    # 3. Agendar cita
    r = client.post(f"{API}/agendar", json={
        "token": token,
        "servicio_id": sid,
        "profesional_id": pro,
        "inicio": hora_elegida
    })
    assert r.status_code == 200
    cita_id = r.json()["cita_id"]

    # 4. Verificar en mis citas
    r = client.get(f"{API}/citas", params={"token": token})
    assert len(r.json()["citas"]) == 1
    assert r.json()["citas"][0]["id"] == cita_id

    # 5. Cambiar fecha a otra hora
    otra_hora = primer_dia["horas"][1]
    r = client.post(f"{API}/cambiar/{cita_id}", json={
        "token": token,
        "inicio": otra_hora
    })
    assert r.status_code == 200
    nueva_cita_id = r.json()["cita_id"]

    # 6. Obtener motivos de cancelación
    r = client.get(f"{API}/motivos-cancelacion", params={"token": token})
    assert r.status_code == 200
    motivos = r.json()
    assert len(motivos) > 0

    # 7. Cancelar cita
    r = client.post(f"{API}/cancelar/{nueva_cita_id}", json={
        "token": token,
        "motivo_id": motivos[0]["id"]
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["espacios_alternativos"] is not None

    # 8. Comprobar que en citas ya no sale como viva
    r = client.get(f"{API}/citas", params={"token": token})
    assert len(r.json()["citas"]) == 0
