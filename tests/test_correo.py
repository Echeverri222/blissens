"""Correo (PRD 5): tres correos por cita, consentimiento y baja propios, ventana, reintentos y aislamiento."""
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from estudia import agenda, canales, catalog, clock, correo, db, negocios, pacientes, tasks
from estudia.web.app import app

from .conftest import ADMIN, URL, at, book, make_patient, make_pro, outbox

AN = "ana@example.com"


def canal_correo(negocio_id=1, remitente="citas@example.com", tipo="correo_prueba"):
    a = db.connect_admin(ADMIN)
    a.execute("insert into canal_negocio(negocio_id, tipo, id_externo) values (%s,%s,%s)", (negocio_id, tipo, remitente))
    a.commit()
    a.close()


@pytest.fixture(autouse=True)
def _proveedor():
    canales.CorreoPrueba.ENVIADOS.clear()
    canales.CorreoPrueba.FALLAR = False
    yield
    canales.CorreoPrueba.FALLAR = False


def correos(conn, paciente, plantilla=None):
    q = "select * from mensaje where paciente_id=%s and canal='correo' and direccion='saliente'"
    args = [paciente]
    if plantilla:
        q += " and plantilla=%s"
        args.append(plantilla)
    return conn.execute(q + " order by id", args).fetchall()


def paciente(conn, **kw):
    return make_patient(conn, correo=AN, acepta_correo=True, **kw)


def test_agendada_recordatorio_y_cancelada_con_los_datos_minimos(conn):
    canal_correo()
    pro, a = make_pro(conn), paciente(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    assert canales.CorreoPrueba.ENVIADOS == []   # nada sale en línea: sale de la tarea, ya confirmada la cita
    assert correos(conn, a)[0]["estado_entrega"] == "diferido"
    tasks.cycle(conn)
    [m] = correos(conn, a)
    assert (m["plantilla"], m["estado_entrega"]) == ("correo_agendada", "entregado")
    assert m["asunto"] == "Tu cita del jueves 19 de noviembre – Blissens Odontología"
    for dato in ("jueves 19 de noviembre", "10:00 a. m.", "Dra. Prueba", "Calle 00"):
        assert dato in m["texto"]
    assert "/correo/baja/" in m["texto"] and "/p/" in m["texto"]
    assert "Valoración" not in m["texto"]  # nunca el servicio ni nada clínico
    assert canales.CorreoPrueba.ENVIADOS[-1]["de"] == "citas@example.com" and canales.CorreoPrueba.ENVIADOS[-1]["para"] == AN

    clock.freeze(at(3, "10:00") - timedelta(hours=23, minutes=59))   # sin confirmar: WhatsApp pide confirmar, el correo avisa
    tasks.cycle(conn)
    assert len(correos(conn, a, "correo_recordatorio")) == 1 and outbox(conn, a, "segundo_intento")
    agenda.cancel(conn, c, "paciente", "enlace")
    tasks.cycle(conn)
    assert [x["plantilla"] for x in correos(conn, a)] == ["correo_agendada", "correo_recordatorio", "correo_cancelada"]
    assert {x["estado_entrega"] for x in correos(conn, a)} == {"entregado"}
    assert "/agendar" in correos(conn, a, "correo_cancelada")[0]["texto"]


def test_reprogramar_envia_agendada_de_la_nueva_cita_sin_cancelada(conn):
    pro, a = make_pro(conn), paciente(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    agenda.reschedule(conn, c, at(4, "10:00"), "paciente")
    assert [x["plantilla"] for x in correos(conn, a)] == ["correo_agendada", "correo_agendada"]


def test_ningun_otro_correo_por_cita(conn):
    pro, a = make_pro(conn), paciente(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    agenda.cancel(conn, c, "paciente", "enlace")   # abre seguimiento y ofertas por WhatsApp, no por correo
    for dia in range(1, 12):
        clock.freeze(at(dia, "09:00"))
        tasks.cycle(conn)
    assert sorted(x["plantilla"] for x in correos(conn, a)) == ["correo_agendada", "correo_cancelada"]


def test_sin_correo_no_registra_nada_y_sin_consentimiento_queda_omitido(conn):
    pro = make_pro(conn)
    sin_correo = make_patient(conn)
    sin_permiso = make_patient(conn, correo=AN, acepta_correo=False)
    book(conn, sin_correo, pro, at(3, "10:00"))
    book(conn, sin_permiso, pro, at(3, "11:00"))
    assert correos(conn, sin_correo) == []
    assert [x["estado_entrega"] for x in correos(conn, sin_permiso)] == ["omitido"]
    assert outbox(conn, sin_correo, "cita_agendada") and outbox(conn, sin_permiso, "cita_agendada")  # WhatsApp sigue igual
    assert canales.CorreoPrueba.ENVIADOS == []


def test_en_produccion_un_negocio_sin_canal_de_correo_no_envia(conn, monkeypatch):
    from estudia import settings
    monkeypatch.setattr(settings, "ENTORNO", "produccion")
    pro, a = make_pro(conn), paciente(conn)
    book(conn, a, pro, at(3, "10:00"))
    assert [x["estado_entrega"] for x in correos(conn, a)] == ["omitido"]


def test_fuera_de_ventana_queda_diferido_y_la_accion_directa_sale_siempre(conn):
    pro, a = make_pro(conn), paciente(conn)
    clock.freeze(at(0, "22:00"))
    c = book(conn, a, pro, at(3, "10:00"))                       # la auxiliar agenda de noche
    [m] = correos(conn, a)
    assert m["estado_entrega"] == "diferido"
    clock.freeze(at(1, "07:01"))
    tasks.cycle(conn)
    assert correos(conn, a)[0]["estado_entrega"] == "entregado"
    c2 = agenda.reschedule(conn, c, at(4, "10:00"), "paciente")  # el paciente actúa de noche: sale al instante
    clock.freeze(at(1, "23:00"))
    c3 = agenda.reschedule(conn, c2, at(3, "11:00"), "paciente")
    tasks.cycle(conn)
    assert correos(conn, a)[-1]["estado_entrega"] == "entregado" and c3


def test_diferido_no_sale_si_la_cita_ya_no_vive_o_el_paciente_se_dio_de_baja(conn):
    pro, a = make_pro(conn), paciente(conn)
    clock.freeze(at(0, "22:00"))
    c = book(conn, a, pro, at(3, "10:00"))
    agenda.cancel(conn, c, "auxiliar", "panel")
    conn.execute("update paciente set acepta_correo=false where id=%s", (a,))
    clock.freeze(at(1, "07:01"))
    tasks.cycle(conn)
    assert {x["estado_entrega"] for x in correos(conn, a)} == {"omitido"}


def test_reenviar_es_idempotente(conn):
    pro, a = make_pro(conn), paciente(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    assert correo.enviar(conn, a, "agendada", c) is None
    assert len(correos(conn, a)) == 1


def test_enlace_de_baja_confirma_antes_y_solo_apaga_el_correo(conn):
    pro, a = make_pro(conn), paciente(conn)
    book(conn, a, pro, at(3, "10:00"))
    enlace = re.search(r"/correo/baja/\S+", correos(conn, a)[0]["texto"]).group(0)
    conn.commit()
    c = TestClient(app)
    r = c.get(enlace)   # un GET (p. ej. un escáner de enlaces) no da de baja a nadie
    assert r.status_code == 200 and "Dejar de recibir correos" in r.text
    assert conn.execute("select acepta_correo from paciente where id=%s", (a,)).fetchone()["acepta_correo"]
    for _ in range(2):  # y repetir la baja no cambia nada
        r = c.post(enlace)
        assert r.status_code == 200 and "no te enviaremos más correos" in r.text
    p = conn.execute("select acepta_correo, acepta_mensajes from paciente where id=%s", (a,)).fetchone()
    assert (p["acepta_correo"], p["acepta_mensajes"]) == (False, True)
    assert c.get("/correo/baja/falso").status_code == 404 and c.post("/correo/baja/falso").status_code == 404
    # y al revés: BAJA por WhatsApp no apaga el correo
    b = paciente(conn, doc="2222")
    from estudia import messaging
    messaging.receive(conn, b, text="BAJA")
    p = conn.execute("select acepta_correo, acepta_mensajes from paciente where id=%s", (b,)).fetchone()
    assert (p["acepta_correo"], p["acepta_mensajes"]) == (True, False)
    assert "correos" in outbox(conn, b, "baja_confirmada")[0]["texto"]


def test_el_enlace_de_baja_sobrevive_a_la_rotacion_de_la_clave(conn, monkeypatch):
    from estudia import settings
    monkeypatch.setattr(settings, "SECRET_KEY", "clave-vieja")
    token = correo.token_baja(1, 7)
    monkeypatch.setattr(settings, "SECRET_KEY", "clave-nueva")
    assert correo.leer_token_baja(token) is None
    monkeypatch.setattr(settings, "SECRET_KEY_ANTERIOR", "clave-vieja")
    assert correo.leer_token_baja(token) == (1, 7)


def test_un_fallo_del_proveedor_no_impide_agendar_ni_whatsapp_se_reintenta_y_termina_fallido(conn):
    canal_correo()
    canales.CorreoPrueba.FALLAR = True
    pro, a = make_pro(conn), paciente(conn)
    c = book(conn, a, pro, at(3, "10:00"))
    assert outbox(conn, a, "cita_agendada")
    [m] = correos(conn, a)
    assert m["estado_entrega"] == "diferido"                   # reintentando
    for _ in range(4):
        clock.freeze(clock.now(conn) + timedelta(minutes=5))
        tasks.cycle(conn)
    assert correos(conn, a)[0]["estado_entrega"] == "fallido"
    assert conn.execute("select estado from cita where id=%s", (c,)).fetchone()["estado"] == "programada"


def test_el_reintento_entrega_cuando_el_proveedor_se_recupera(conn):
    canal_correo()
    canales.CorreoPrueba.FALLAR = True
    pro, a = make_pro(conn), paciente(conn)
    book(conn, a, pro, at(3, "10:00"))
    tasks.cycle(conn)                                          # primer intento: falla y queda por reintentar
    assert correos(conn, a)[0]["estado_entrega"] == "diferido"
    canales.CorreoPrueba.FALLAR = False
    clock.freeze(clock.now(conn) + timedelta(minutes=2))
    tasks.cycle(conn)
    assert correos(conn, a)[0]["estado_entrega"] == "entregado" and len(canales.CorreoPrueba.ENVIADOS) == 1


def test_consentimiento_y_anonimizacion(conn):
    from estudia import privacidad
    a = make_patient(conn)
    for malo in ("sin-arroba", "a@x.com,b@y.com", "a@x.com b@y.com", "a@x.com;b@y.com", "a@x.com\nBcc: z@y.com"):
        with pytest.raises(pacientes.DatosInvalidos):
            correo.registrar_consentimiento(conn, a, malo, True)
    with pytest.raises(pacientes.DatosInvalidos):
        correo.registrar_consentimiento(conn, a, None, True)
    correo.registrar_consentimiento(conn, a, " Ana@Example.com ", True)
    p = conn.execute("select * from paciente where id=%s", (a,)).fetchone()
    assert (p["correo"], p["acepta_correo"]) == (AN, True) and p["consentimiento_correo_en"] == clock.now(conn)
    privacidad.anonimizar_paciente(conn, a)
    p = conn.execute("select * from paciente where id=%s", (a,)).fetchone()
    assert (p["correo"], p["acepta_correo"], p["consentimiento_correo_en"]) == (None, False, None)


def test_el_correo_de_un_negocio_nunca_usa_el_canal_de_otro(conn):
    a = db.connect_admin(ADMIN)
    b = negocios.crear(a, "otra", "Otra Clínica")
    a.commit()
    a.close()
    canal_correo(1, "citas@a.example.com")
    canal_correo(b, "citas@b.example.com")
    pro, pa = make_pro(conn), paciente(conn)
    book(conn, pa, pro, at(3, "10:00"))
    tasks.cycle(conn)
    conn.commit()
    cb = db.connect(URL, negocio=b)
    catalog.load(cb)
    pb = make_patient(cb, "Beto", doc="777", correo="beto@example.com", acepta_correo=True)
    sid = cb.execute("select id from servicio limit 1").fetchone()["id"]
    agenda.book(cb, pb, make_pro(cb, "Dr. B"), sid, at(3, "10:00"), "auxiliar", "auxiliar")
    tasks.cycle(cb)
    cb.commit()
    cb.close()
    de = {e["para"]: e["de"] for e in canales.CorreoPrueba.ENVIADOS}
    assert de == {AN: "citas@a.example.com", "beto@example.com": "citas@b.example.com"}


def test_la_auxiliar_registra_el_consentimiento_por_la_api(conn):
    from estudia import usuarios

    from .test_api import API, entrar
    usuarios.crear(conn, "recepcion", "Recepción", "clave-de-prueba", "auxiliar")
    a = make_patient(conn)
    conn.commit()
    r = entrar("recepcion").put(f"{API}/pacientes/{a}/correo", json={"correo": AN, "acepta": True})
    assert r.status_code == 200 and r.json() == {"correo": AN, "acepta": True}
    r = entrar("recepcion").put(f"{API}/pacientes/{a}/correo", json={"correo": None, "acepta": True})
    assert r.status_code == 422
