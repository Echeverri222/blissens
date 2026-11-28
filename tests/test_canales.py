"""Puerto del canal: el webhook encamina al negocio del canal, verifica la firma y no repite reenvíos."""
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from estudia import agenda, canales, confirmations, db, followup, negocios, router, slots
from estudia.web.app import app

from .conftest import ADMIN, URL, at, book, make_patient, make_pro, status


def _firmar(secreto, cuerpo: dict):
    crudo = json.dumps(cuerpo).encode()
    return crudo, {"X-Firma": hmac.new(secreto.encode(), crudo, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}


def _canal(negocio_id, id_externo, ref):
    a = db.connect_admin(ADMIN)
    a.execute("insert into canal_negocio(negocio_id, tipo, id_externo, secreto_ref) values (%s,'prueba',%s,%s)",
              (negocio_id, id_externo, ref))
    a.commit()
    a.close()


def test_webhook_encamina_por_negocio_verifica_firma_y_no_repite(conn, monkeypatch):
    monkeypatch.setenv("SECRETO_A", "secreto-a")
    monkeypatch.setenv("SECRETO_B", "secreto-b")
    a = db.connect_admin(ADMIN)
    b = negocios.crear(a, "otra", "Otra Clínica")
    a.commit()
    a.close()
    pa = make_patient(conn, "Ana", celular="+573001112233")
    conn.commit()
    cb = db.connect(URL, negocio=b)
    make_patient(cb, "Beto", doc="999", celular="+573001112233")  # mismo celular, otro negocio
    cb.commit()
    cb.close()
    _canal(1, "canal-a", "SECRETO_A")
    _canal(b, "canal-b", "SECRETO_B")
    c = TestClient(app)

    msg = {"canal": "canal-a", "id": "wamid.1", "de": "3001112233", "texto": "hola"}
    crudo, h = _firmar("secreto-a", msg)
    assert c.post("/canales/prueba/webhook", content=crudo, headers=h).json() == {"estado": "recibido"}
    assert c.post("/canales/prueba/webhook", content=crudo, headers=h).json() == {"estado": "repetido"}

    # firma de otro negocio: se rechaza; y el mensaje cayó solo en el negocio A
    crudo2, h2 = _firmar("secreto-b", {**msg, "id": "wamid.2"})
    assert c.post("/canales/prueba/webhook", content=crudo2, headers=h2).status_code == 401
    assert c.post("/canales/prueba/webhook", content=b"{}", headers={"Content-Type": "application/json"}).status_code == 404
    assert c.post("/canales/inexistente/webhook", content=crudo, headers=h).status_code == 404
    assert conn.execute("select count(*) n from mensaje where direccion='entrante' and paciente_id=%s", (pa,)).fetchone()["n"] == 1
    a = db.connect_admin(ADMIN)
    assert a.execute("select count(*) n from mensaje where direccion='entrante' and negocio_id=%s", (b,)).fetchone()["n"] == 0
    a.close()


def test_envio_usa_el_canal_del_negocio(conn):
    from estudia import messaging
    _canal(1, "canal-a", None)
    p = make_patient(conn, "Ana")
    conn.commit()
    canales.Prueba.ENVIADOS.clear()
    messaging.send(conn, p, "baja_confirmada", direct=True)
    assert len(canales.Prueba.ENVIADOS) == 1
    assert conn.execute("select canal from mensaje order by id desc limit 1").fetchone()["canal"] == "prueba"


def test_webhook_bloquea_botones_ajenos_o_malformados_sin_filtrar_datos(conn, monkeypatch):
    monkeypatch.setenv("SECRETO_A", "secreto-a")
    _canal(1, "canal-a", "SECRETO_A")
    pro = make_pro(conn)
    pa = make_patient(conn, "Ana", doc="101", celular="+573001112233")
    pb = make_patient(conn, "Beto", doc="202", celular="+573004445566")

    cita_a1 = book(conn, pa, pro, at(3, "10:00"))
    cita_a2 = book(conn, pa, pro, at(4, "10:00"))
    cita_a3 = book(conn, pa, pro, at(4, "14:00"))
    cancel_a = agenda.cancel(conn, cita_a2, "paciente", "enlace")
    caso_a = conn.execute("select id from caso_seguimiento where cita_id=%s", (cita_a2,)).fetchone()["id"]
    slots.register_slot(conn, pro, agenda.rng(at(2, "14:00"), 45), None, "cancelacion")
    oferta_a = conn.execute("select id from oferta_adelanto where cita_id=%s and estado='pendiente'", (cita_a3,)).fetchone()["id"]
    conn.commit()

    c = TestClient(app)
    for i, boton in enumerate(
        (f"conf:no:{cita_a1}", f"oferta:si:{oferta_a}", f"seg:ahora_no:{caso_a}", "conf:malformado"),
        start=1,
    ):
        crudo, h = _firmar("secreto-a", {"canal": "canal-a", "id": f"wamid.b{i}", "de": "3004445566", "boton": boton})
        r = c.post("/canales/prueba/webhook", content=crudo, headers=h)
        assert r.status_code == 200 and r.json() == {"estado": "recibido"}

    conn.rollback()
    entrantes_b = conn.execute("select gestionado from mensaje where paciente_id=%s and direccion='entrante'", (pb,)).fetchall()
    assert len(entrantes_b) == 4 and all(m["gestionado"] is False for m in entrantes_b)
    assert status(conn, cita_a1) == "programada"
    assert conn.execute("select estado from oferta_adelanto where id=%s", (oferta_a,)).fetchone()["estado"] == "pendiente"
    assert conn.execute("select estado from caso_seguimiento where id=%s", (caso_a,)).fetchone()["estado"] == "abierto"
    assert conn.execute("select count(*) n from mensaje where paciente_id=%s and direccion='saliente'", (pb,)).fetchone()["n"] == 0

    # Defensa en profundidad: llamadas directas sin pasar por messaging.receive también validan pertenencia al hogar y formato
    assert confirmations.process_response(conn, pb, "no", cita_a1) is False
    assert followup.decline(conn, caso_a, patient_id=pb) is False
    assert slots.accept(conn, oferta_a, patient_id=pb) is False
    assert slots.reject(conn, oferta_a, patient_id=pb) is False
    assert router._motivo(conn, pb, [str(cancel_a), "1"], 0) is False
    assert router._conf(conn, pb, ["malformado"], 0) is False
    assert router._oferta(conn, pb, ["si", "no-num"], 0) is False
    assert router._seg(conn, pb, ["ahora_no"], 0) is False

    assert status(conn, cita_a1) == "programada"
    assert conn.execute("select estado from oferta_adelanto where id=%s", (oferta_a,)).fetchone()["estado"] == "pendiente"
    assert conn.execute("select estado from caso_seguimiento where id=%s", (caso_a,)).fetchone()["estado"] == "abierto"
    assert conn.execute("select motivo_id from cancelacion where id=%s", (cancel_a,)).fetchone()["motivo_id"] is None
    assert conn.execute("select count(*) n from mensaje where paciente_id=%s and direccion='saliente'", (pb,)).fetchone()["n"] == 0
