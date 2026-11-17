"""Puerto del canal: el webhook encamina al negocio del canal, verifica la firma y no repite reenvíos."""
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from estudia import canales, db, negocios
from estudia.web.app import app

from .conftest import ADMIN, URL, make_patient


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
