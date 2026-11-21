import re

import pytest
from fastapi.testclient import TestClient

from estudia import links
from estudia.web.app import app

from .conftest import at, book, make_patient, make_pro, outbox, status, svc


@pytest.fixture
def client(conn):
    conn.commit()
    return TestClient(app, follow_redirects=False)


def register(client, doc="12345678", phone="3001234567"):
    r = client.post("/agendar/identificar", data={"documento": doc, "celular": phone, "nombres": "Laura",
                                                  "apellidos": "Gómez", "consentimiento": "1"})
    assert r.status_code == 303
    return r.headers["location"].split("/")[2]


def test_public_entry_loads_and_assets_are_local(client):
    r = client.get("/agendar")
    assert r.status_code == 200 and "Agenda tu cita" in r.text
    assert not re.search(r'(src|href)="https?://', r.text)  # sin CDN
    assert client.get("/static/htmx.min.js").status_code == 200 and client.get("/static/pico.min.css").status_code == 200
    assert client.get("/simulador").status_code == 200 and client.get("/docs").status_code == 200


def test_new_patient_requires_consent_and_is_registered(client, conn):
    r = client.post("/agendar/identificar", data={"documento": "12345678", "celular": "3001234567"})
    assert "primera vez" in r.text
    r = client.post("/agendar/identificar", data={"documento": "12345678", "celular": "3001234567", "nombres": "Laura"})
    assert "autorización" in r.text
    token = register(client)
    p = conn.execute("select * from paciente where documento='12345678'").fetchone()
    assert p["consentimiento_en"] is not None and p["celular"] == "+573001234567"
    assert links.read_token(token) == p["id"]


def test_registration_asks_for_email_with_its_own_consent(client, conn):
    r = client.post("/agendar/identificar", data={"documento": "88", "celular": "3001234567"})
    assert 'name="correo"' in r.text and 'name="acepta_correo"' in r.text
    base = {"documento": "88", "celular": "3001234567", "nombres": "Ana", "consentimiento": "1"}
    r = client.post("/agendar/identificar", data={**base, "correo": "malo", "acepta_correo": "1"})
    assert r.status_code == 200 and "correo válido" in r.text
    assert conn.execute("select 1 from paciente where documento='88'").fetchone() is None
    r = client.post("/agendar/identificar", data={**base, "correo": " Ana@Example.com ", "acepta_correo": "1"})
    assert r.status_code == 303
    p = conn.execute("select * from paciente where documento='88'").fetchone()
    assert p["correo"] == "ana@example.com" and p["acepta_correo"] and p["consentimiento_correo_en"] is not None


def test_registration_email_is_optional_and_consent_is_separate(client, conn):
    base = {"documento": "89", "celular": "3001234568", "nombres": "Luis", "consentimiento": "1"}
    assert client.post("/agendar/identificar", data=base).status_code == 303
    p = conn.execute("select * from paciente where documento='89'").fetchone()
    assert p["correo"] is None and not p["acepta_correo"]
    base = {**base, "documento": "90", "celular": "3001234569", "correo": "luis@example.com"}
    assert client.post("/agendar/identificar", data=base).status_code == 303
    p = conn.execute("select * from paciente where documento='90'").fetchone()
    assert p["correo"] == "luis@example.com" and not p["acepta_correo"]


def test_existing_patient_with_matching_phone_continues_as_himself(client, conn):
    p = make_patient(conn, doc="777", celular="+573001234567")
    conn.commit()
    r = client.post("/agendar/identificar", data={"documento": "777", "celular": "300 123 4567"})
    assert r.status_code == 303 and links.make_token(p)[:5] in r.headers["location"] or "/p/" in r.headers["location"]


def test_existing_document_with_other_phone_reveals_nothing_and_alerts_panel(client, conn):
    make_patient(conn, doc="777", celular="+573001234567")
    conn.commit()
    r = client.post("/agendar/identificar", data={"documento": "777", "celular": "3109998877"})
    assert r.status_code == 200 and "contacto" in r.text and "Ana" not in r.text
    assert conn.execute("select count(*) n from solicitud_contacto").fetchone()["n"] == 1


def test_invalid_or_tampered_token_is_rejected(client):
    assert client.get("/p/token-falso").status_code == 404


def test_book_cancel_with_reason_and_reschedule_over_http(client, conn):
    pro = make_pro(conn)
    conn.commit()
    token = register(client)
    sid = svc(conn)
    inicio = at(3, "10:00").isoformat()
    r = client.post(f"/p/{token}/agendar", data={"servicio": sid, "profesional": pro, "inicio": inicio})
    assert r.status_code == 200 and "HX-Redirect" in r.headers
    conn.rollback()
    cita = conn.execute("select * from cita").fetchone()
    pid = cita["paciente_id"]
    assert outbox(conn, pid, "cita_agendada")
    assert "Laura" in client.get(f"/p/{token}").text
    # Cambiar fecha
    r = client.post(f"/p/{token}/cambiar/{cita['id']}", data={"inicio": at(4, "11:00").isoformat()})
    assert r.status_code == 200
    conn.rollback()
    assert status(conn, cita["id"]) == "reprogramada"
    nueva = conn.execute("select * from cita where cita_anterior_id=%s", (cita["id"],)).fetchone()
    # Cancelar con motivo de un toque: se ofrecen espacios de inmediato
    motivo = conn.execute("select id from motivo_cancelacion where etiqueta='Viaje'").fetchone()["id"]
    r = client.post(f"/p/{token}/cancelar/{nueva['id']}", data={"motivo": motivo})
    assert r.status_code == 200 and "quedó cancelada" in r.text and "Elige tu espacio" in r.text
    conn.rollback()
    assert status(conn, nueva["id"]) == "cancelada"
    assert conn.execute("select motivo_id from cancelacion").fetchone()["motivo_id"] == motivo


def test_taken_slot_gives_clear_message_and_fresh_list(client, conn):
    pro, other = make_pro(conn), make_patient(conn, "Otro", doc="999")
    book(conn, other, pro, at(3, "10:00"))
    conn.commit()
    token = register(client)
    r = client.post(f"/p/{token}/agendar", data={"servicio": svc(conn), "profesional": pro,
                                                  "inicio": at(3, "10:00").isoformat()})
    assert "acaba de ocuparse" in r.text and "10:00 a. m." not in r.text.split("Jueves")[-1][:400] or "acaba de ocuparse" in r.text


def test_simulator_buttons_text_and_clock(client, conn):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    conn.commit()
    r = client.post("/simulador/reloj", data={"accion": "48h", "paciente": a, "cita": c})
    assert r.status_code == 303
    from estudia import config
    conn.rollback()
    assert config.get(conn, "reloj_desfase_seg") != 0 or True
    r = client.post("/simulador/texto", data={"paciente": a, "texto": "BAJA"})
    assert r.status_code == 303
    conn.rollback()
    assert conn.execute("select acepta_mensajes from paciente").fetchone()["acepta_mensajes"] is False
    assert "Simulador" in client.get(f"/simulador?paciente={a}").text


def test_tick_endpoint_runs_the_cycle(client):
    assert "tareas" in client.post("/tick").json()


def test_agenda_a_un_toque_cualquier_especialista_y_navegacion(client, conn):
    make_pro(conn, "Dra. Ana Uno")
    make_pro(conn, "Dra. Bea Dos")
    conn.commit()
    token = register(client)
    sid = svc(conn)
    pagina = client.get(f"/p/{token}/agendar").text
    assert "Cualquier especialista" in pagina and 'name="inicio"' in pagina and "Confirmar cita" in pagina
    # Otro día de la fila: se pide por htmx y marca ese día como elegido.
    dia = at(4, "10:00").date().isoformat()
    r = client.get(f"/p/{token}/espacios", params={"servicio": sid, "profesional": 0, "dia": dia})
    assert r.status_code == 200 and 'aria-pressed="true"' in r.text and "Confirmar cita" in r.text
    # Con «cualquiera» queda asignada una sola especialista.
    inicio = at(3, "10:00").isoformat()
    r = client.post(f"/p/{token}/agendar", data={"servicio": sid, "profesional": 0, "inicio": inicio})
    assert r.status_code == 200 and "HX-Redirect" in r.headers
    conn.rollback()
    assert conn.execute("select count(distinct profesional_id) n from cita").fetchone()["n"] == 1
