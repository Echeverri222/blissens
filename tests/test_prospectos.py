"""Prospectos (docs/adr/0010-prospectos-sin-documento.md): quien escribe desde el sitio queda como una ficha ligera sin
documento, con su propia página, sin citas presenciales, y pasa a paciente cuando la recepción le pone el documento."""
import re

import pytest
from fastapi.testclient import TestClient

from estudia import agenda, canales, db, links, migrate, pacientes, privacidad, solicitudes, tasks
from estudia.asistente import herramientas
from estudia.web.app import app

from .conftest import ADMIN, at, make_patient, make_pro, svc
from .test_api import API, mundo  # noqa: F401  (fixture)
from .test_correo import canal_correo

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _proveedor():
    canales.CorreoPrueba.ENVIADOS.clear()
    canales.CorreoPrueba.FALLAR = False
    yield
    canales.CorreoPrueba.FALLAR = False


@pytest.fixture
def client(conn):
    conn.commit()
    return TestClient(app, follow_redirects=False)


def enviar(client, archivos=(), **datos):
    base = {"interes": "evaluacion_virtual", "idioma": "en", "nombre": "Jane Doe", "correo": "Jane@Example.com",
            "celular": "+1 305 555 0100", "pais": "Estados Unidos", "mensaje": "Veneers", "consentimiento": "1"}
    files = [("fotos", a) for a in archivos] or None
    r = client.post("/sitio/solicitud", headers={"HX-Request": "true"}, data={**base, **datos}, files=files)
    assert r.status_code == 200
    return r


def prospectos(conn):
    return conn.execute("select * from paciente where etapa='prospecto' order by id").fetchall()


def enlace_del_acuse(conn, para="jane@example.com"):
    tasks.cycle(conn)
    texto = next(e["texto"] for e in canales.CorreoPrueba.ENVIADOS if e["para"] == para and "/p/" in e["texto"])
    return re.search(r"/p/([\w.\-]+)", texto).group(1)


def test_una_solicitud_desde_el_exterior_crea_un_prospecto_sin_documento(client, conn):
    enviar(client)
    (p,) = prospectos(conn)
    assert (p["nombres"], p["documento"], p["correo"], p["celular"]) == ("Jane Doe", None, "jane@example.com", "+13055550100")
    assert p["internacional"] and p["segmento_origen"] == "sitio_web" and p["segmento_marcado_en"] is not None
    assert p["consentimiento_en"] is not None and not p["acepta_mensajes"] and not p["acepta_correo"]
    s = conn.execute("select paciente_id, origen from solicitud_contacto").fetchone()
    assert (s["paciente_id"], s["origen"]) == (p["id"], "sitio")


def test_solo_con_correo_o_solo_con_whatsapp_tambien_crea_el_prospecto(client, conn):
    enviar(client, celular="")
    enviar(client, nombre="Luis", correo="", celular="+44 20 7946 0000")
    a, b = prospectos(conn)
    assert (a["celular"], a["correo"]) == (None, "jane@example.com") and (b["celular"], b["correo"]) == ("+442079460000", None)


def test_el_mismo_correo_en_otra_grafia_reutiliza_al_prospecto(client, conn):
    enviar(client)
    enviar(client, nombre="Jane D.", correo="JANE@EXAMPLE.COM", celular="", interes="contacto")
    (p,) = prospectos(conn)
    assert p["nombres"] == "Jane Doe"                      # no se pisan sus datos
    assert [s["paciente_id"] for s in conn.execute("select paciente_id from solicitud_contacto order by id")] == [p["id"]] * 2


def test_el_mismo_whatsapp_reutiliza_al_prospecto_aunque_cambie_el_formato(client, conn):
    enviar(client, correo="")
    enviar(client, nombre="J. Doe", correo="otra@example.com", celular="+1 (305) 555-0100")
    (p,) = prospectos(conn)
    assert p["correo"] is None                              # un correo nuevo no se agrega a una ficha que ya existe
    assert conn.execute("select count(*) n from solicitud_contacto where paciente_id=%s", (p["id"],)).fetchone()["n"] == 2


def test_un_paciente_con_documento_recibe_la_solicitud_y_no_baja_de_etapa(client, conn):
    pid = make_patient(conn, "Jane", "Doe", doc="900", correo="jane@example.com")
    conn.commit()
    enviar(client)
    assert prospectos(conn) == []
    p = conn.execute("select etapa, documento, internacional, nombres from paciente where id=%s", (pid,)).fetchone()
    assert (p["etapa"], p["documento"], p["internacional"], p["nombres"]) == ("paciente", "900", False, "Jane")
    assert conn.execute("select paciente_id from solicitud_contacto").fetchone()["paciente_id"] == pid


def test_el_acuse_lleva_un_enlace_personal_que_funciona(client, conn):
    canal_correo()
    enviar(client, celular="")
    token = enlace_del_acuse(conn)
    (p,) = prospectos(conn)
    assert links.read_token(token) == p["id"] and links.huella_del_token(token) == links.huella_correo("jane@example.com")
    r = client.get(f"/p/{token}")
    assert r.status_code == 200 and "Your requests" in r.text and "Virtual assessment" in r.text and "Received" in r.text
    assert "Agendar" not in r.text and "/agendar" not in r.text


def test_el_enlace_con_celular_tambien_sirve_y_cambiar_el_correo_no_lo_rompe(client, conn):
    canal_correo()
    enviar(client)
    token = enlace_del_acuse(conn)
    (p,) = prospectos(conn)
    assert links.huella_del_token(token) == links.huella_celular("+13055550100")
    conn.execute("update paciente set correo='nuevo@example.com' where id=%s", (p["id"],))
    conn.commit()
    assert client.get(f"/p/{token}").status_code == 200
    conn.execute("update paciente set celular='+1 305 555 9999' where id=%s", (p["id"],))
    conn.commit()
    assert client.get(f"/p/{token}").status_code == 404


def test_quien_escribe_con_el_whatsapp_de_otro_no_recibe_su_enlace(client, conn):
    canal_correo()
    enviar(client)                                                       # la víctima
    canales.CorreoPrueba.ENVIADOS.clear()
    enviar(client, nombre="Intruso", correo="intruso@example.com", celular="+1 305 555 0100")
    tasks.cycle(conn)
    textos = [e["texto"] for e in canales.CorreoPrueba.ENVIADOS if e["para"] == "intruso@example.com"]
    assert textos and "/p/" not in textos[0]


def test_un_enlace_antiguo_sin_huella_sigue_valiendo(client, conn):
    pid = make_patient(conn, "Ana", doc="901")
    token = links.make_token(pid, conn=conn)
    conn.commit()
    assert len(links._serializador().loads(token)) == 2 and client.get(f"/p/{token}").status_code == 200


def test_el_prospecto_no_agenda_ni_cambia_ni_cancela_ni_agrega_familia(client, conn):
    canal_correo()
    enviar(client)
    token = enlace_del_acuse(conn)
    for ruta in ("nueva", "agendar", "cambiar/1", "cancelar/1", "familia/agregar", "espacios?servicio=1"):
        r = client.get(f"/p/{token}/{ruta}")
        assert r.status_code == 303 and r.headers["location"].startswith(f"/p/{token}?aviso="), ruta
    r = client.get(r.headers["location"])
    assert "Todav" in r.text and "documento" in r.text
    r = client.post(f"/p/{token}/agendar", data={"servicio": 1, "inicio": "2026-11-20T09:00"}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and r.headers["hx-redirect"].startswith(f"/p/{token}?aviso=")
    assert client.post(f"/p/{token}/confirmar/1").status_code == 303
    assert client.get(f"/p/{token}/asistente").status_code == 404
    assert conn.execute("select count(*) n from cita").fetchone()["n"] == 0


def test_agenda_book_rechaza_a_un_prospecto(client, conn):
    make_pro(conn)
    enviar(client)
    (p,) = prospectos(conn)
    with pytest.raises(pacientes.DatosInvalidos):
        agenda.book(conn, p["id"], None, svc(conn), at(2, "09:00"), "auxiliar", "auxiliar")


def test_el_prospecto_agrega_fotos_a_su_ultima_solicitud(client, conn):
    canal_correo()
    enviar(client)
    enviar(client, interes="contacto")
    token = enlace_del_acuse(conn)
    r = client.post(f"/p/{token}/adjuntos", files=[("fotos", ("rx.png", PNG, "image/png"))])
    assert r.status_code == 303 and "aviso=" in r.headers["location"]
    ultima = conn.execute("select id from solicitud_contacto order by id desc limit 1").fetchone()["id"]
    assert [a["nombre"] for a in solicitudes.adjuntos(conn, ultima)] == ["rx.png"]
    assert conn.execute("select count(*) n from solicitud_adjunto").fetchone()["n"] == 1
    # reglas del formulario: el tipo se mira en el contenido y hay tope por solicitud
    r = client.post(f"/p/{token}/adjuntos", files=[("fotos", ("x.png", b"no soy imagen", "image/png"))])
    assert r.status_code == 422 and "JPG, PNG or WEBP" in r.text
    for _ in range(solicitudes.MAX_ADJUNTOS_TOTAL):
        client.post(f"/p/{token}/adjuntos", files=[("fotos", ("a.png", PNG, "image/png"))])
    assert conn.execute("select count(*) n from solicitud_adjunto").fetchone()["n"] == solicitudes.MAX_ADJUNTOS_TOTAL
    # una solicitud ya gestionada vuelve a la bandeja cuando llegan archivos nuevos
    conn.execute("update solicitud_contacto set gestionada=true where id=%s", (ultima,))
    conn.commit()
    client.post(f"/p/{token}/adjuntos", files=[("fotos", ("b.png", PNG, "image/png"))])
    assert conn.execute("select gestionada from solicitud_contacto where id=%s", (ultima,)).fetchone()["gestionada"] is True


def test_la_pagina_muestra_el_estado_de_cada_solicitud(client, conn):
    canal_correo()
    enviar(client)
    enviar(client, interes="contacto")
    token = enlace_del_acuse(conn)
    conn.execute("update solicitud_contacto set gestionada=true where interes='contacto'")
    conn.commit()
    t = client.get(f"/p/{token}").text
    assert "Being handled" in t and "Received" in t and "Contact" in t


def test_la_recepcion_convierte_al_prospecto_con_el_documento(mundo, client, conn):  # noqa: F811
    enviar(client, celular="")
    (p,) = prospectos(conn)
    url = f"{API}/pacientes/{p['id']}"
    assert mundo.aux.get(url).json()["paciente"]["etapa"] == "prospecto"
    assert [x["etapa"] for x in mundo.aux.get(f"{API}/pacientes", params={"q": "jane@example"}).json()] == ["prospecto"]
    assert [x["etapa"] for x in mundo.aux.get(f"{API}/pacientes", params={"segmento": "internacional"}).json()] == ["prospecto"]
    # sin celular hace falta uno para poder atenderlo
    r = mundo.aux.put(f"{url}/identificacion", json={"documento": "1.234.567"})
    assert r.status_code == 422 and r.json()["codigo"] == "datos_invalidos"
    # el documento de otro paciente del negocio
    r = mundo.aux.put(f"{url}/identificacion", json={"documento": conn.execute("select documento from paciente where id=%s", (mundo.p1,)).fetchone()["documento"],
                                                   "celular": "3001234567"})
    assert r.status_code == 409 and r.json()["codigo"] == "documento_existente"
    r = mundo.aux.put(f"{url}/identificacion", json={"documento": "1.234.567", "celular": "300 123 4567"})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": p["id"], "etapa": "paciente", "documento": "1234567", "celular": "+573001234567"}
    assert mundo.aux.get(url).json()["paciente"]["etapa"] == "paciente"
    # ya es paciente: no se vuelve a identificar y ya se le puede agendar
    assert mundo.aux.put(f"{url}/identificacion", json={"documento": "999"}).status_code == 422
    assert mundo.aux.put(f"{API}/pacientes/999999/identificacion", json={"documento": "999"}).status_code == 404
    assert agenda.book(conn, p["id"], make_pro(conn), svc(conn), at(3, "09:00"), "auxiliar", "auxiliar")
    assert mundo.esp1.put(f"{url}/identificacion", json={"documento": "5"}).status_code == 403


def test_el_documento_es_unico_por_negocio_tambien_en_la_base(client, conn):
    enviar(client)
    (p,) = prospectos(conn)
    make_patient(conn, "Otro", doc="777")
    with pytest.raises(pacientes.DocumentoExistente):
        pacientes.completar_documento(conn, p["id"], "777", "+13055550100")


def test_exportar_y_anonimizar_a_un_prospecto(client, conn):
    enviar(client, [("rx.png", PNG, "image/png")])
    (p,) = prospectos(conn)
    exp = privacidad.exportar_paciente(conn, p["id"])
    assert exp["paciente"]["etapa"] == "prospecto" and exp["paciente"]["correo"] == "jane@example.com"
    assert exp["solicitudes_web"][0]["adjuntos"][0]["nombre"] == "rx.png"
    privacidad.anonimizar_paciente(conn, p["id"])
    a = conn.execute("select * from paciente where id=%s", (p["id"],)).fetchone()
    assert (a["nombres"], a["etapa"], a["correo"], a["celular"], a["documento"]) == (privacidad.ANONIMO, "paciente", None, None, None)
    assert not a["internacional"]
    assert conn.execute("select count(*) n from solicitud_contacto").fetchone()["n"] == 0
    assert conn.execute("select count(*) n from solicitud_adjunto").fetchone()["n"] == 0
    token = links.make_token(p["id"], conn=conn, correo="jane@example.com")
    conn.commit()
    assert client.get(f"/p/{token}").status_code == 404


def test_la_base_exige_contacto_y_que_un_prospecto_no_tenga_documento(conn):
    with pytest.raises(Exception, match="paciente_prospecto_contacto"):
        conn.execute("insert into paciente(nombres, etapa) values ('X','prospecto')")
    conn.rollback()
    with pytest.raises(Exception, match="paciente_prospecto_contacto"):
        conn.execute("insert into paciente(nombres, etapa, correo, documento) values ('X','prospecto','x@example.com','1')")


def test_el_asistente_de_recepcion_ve_la_etapa_sin_datos_de_contacto(client, conn):
    enviar(client)
    filas = herramientas.bandejas.find_patients(conn, "jane")
    assert [(f["etapa"], f["documento"]) for f in filas] == [("prospecto", None)]
    assert herramientas._ultimos4(filas[0]["documento"]) is None


def test_la_tarjeta_de_solicitud_del_asistente_visitante_tambien_crea_prospectos(client, conn):
    # la tarjeta `proponer_solicitud` renderiza el mismo formulario y lo manda a la misma ruta
    enviar(client, interes="contacto", panel="asistente")
    assert len(prospectos(conn)) == 1


def test_la_migracion_020_enlaza_las_solicitudes_viejas_por_correo():
    a = db.connect_admin(ADMIN.rsplit("/", 1)[0] + "/postgres")
    a.autocommit = True
    a.execute("drop database if exists estudia_mig_prospecto")
    a.execute("create database estudia_mig_prospecto")
    url = ADMIN.rsplit("/", 1)[0] + "/estudia_mig_prospecto"
    try:
        migrate.run(url, hasta="019")
        c = db.connect_admin(url)
        c.execute("insert into paciente(negocio_id, nombres, documento, celular, correo) values (1,'Ana','1','+573001112233','ana@example.com')")

        def solicitud(nombre, correo, celular="", pais="Peru", idioma="en"):
            c.execute("insert into solicitud_contacto(negocio_id, documento, celular, nota, momento, origen, interes, idioma, "
                      "nombre, correo, pais) values (1,'—',%s,'Sitio web',now(),'sitio','contacto',%s,%s,%s,%s)",
                      (celular, idioma, nombre, correo, pais))
        solicitud("Ana P", "ANA@example.com")                  # ya hay un paciente con ese correo
        solicitud("Jane", "jane@example.com", "+1 305 555 0100")
        solicitud("Jane Doe", "JANE@example.com")              # misma persona, otra grafía
        solicitud("Solo Tel", None, "+44 20 7946 0000")        # sin correo: queda suelta
        c.commit()
        assert migrate.run(url, hasta="020") == ["020_prospecto.sql"]
        pros = c.execute("select * from paciente where etapa='prospecto'").fetchall()
        assert [(p["correo"], p["nombres"], p["celular"], p["documento"], p["internacional"]) for p in pros] == [
            ("jane@example.com", "Jane Doe", "+1 305 555 0100", None, True)]
        s = c.execute("select nombre, paciente_id from solicitud_contacto order by id").fetchall()
        assert s[0]["paciente_id"] == c.execute("select id from paciente where documento='1'").fetchone()["id"]
        assert s[1]["paciente_id"] == s[2]["paciente_id"] == pros[0]["id"] and s[3]["paciente_id"] is None
        c.close()
        assert migrate.bajar(url, 1) == ["020_prospecto.sql"]
        c = db.connect_admin(url)
        assert c.execute("select count(*) n from paciente").fetchone()["n"] == 1
        assert c.execute("select count(*) n from solicitud_contacto where paciente_id is not null").fetchone()["n"] == 1
        c.close()
    finally:
        a.execute("drop database if exists estudia_mig_prospecto")
        a.close()
