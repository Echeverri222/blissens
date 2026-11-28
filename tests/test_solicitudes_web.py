"""Solicitudes del sitio web: datos en columnas, fotos adjuntas, aviso a la clínica, acuse a quien escribe, vínculo con
la ficha del paciente y borrado al anonimizar."""
import pytest
from fastapi.testclient import TestClient

from estudia import canales, config, privacidad, solicitudes, tasks
from estudia.web.app import app

from .conftest import make_patient
from .test_api import API, mundo  # noqa: F401  (fixture)
from .test_correo import canal_correo

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64
CLINICA = "recepcion@clinica.example"


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
            "celular": "+1 305 555 0100", "pais": "Estados Unidos", "mensaje": "Veneers, March", "consentimiento": "1"}
    files = [("fotos", a) for a in archivos] or None
    return client.post("/sitio/solicitud", headers={"HX-Request": "true"}, data={**base, **datos}, files=files)


def ultima(conn):
    return conn.execute("select * from solicitud_contacto order by id desc limit 1").fetchone()


def cuenta(conn, tabla):
    return conn.execute(f"select count(*) n from {tabla}").fetchone()["n"]


def test_evaluacion_virtual_guarda_columnas_y_fotos(client, conn):
    r = enviar(client, [("sonrisa.png", PNG, "image/png"), ("rx.pdf", PDF, "application/pdf")])
    assert r.status_code == 200 and "within 24 hours" in r.text and "confirmation to your email" in r.text
    s = ultima(conn)
    assert (s["origen"], s["interes"], s["idioma"], s["nombre"], s["correo"], s["pais"], s["mensaje"]) == (
        "sitio", "evaluacion_virtual", "en", "Jane Doe", "jane@example.com", "Estados Unidos", "Veneers, March")
    assert s["celular"].startswith("+1") and s["documento"] == "—" and s["paquete"] is None
    adj = conn.execute("select nombre, tipo, tamano, datos from solicitud_adjunto where solicitud_id=%s order by id",
                       (s["id"],)).fetchall()
    assert [(a["nombre"], a["tipo"], a["tamano"]) for a in adj] == [("sonrisa.png", "image/png", len(PNG)),
                                                                     ("rx.pdf", "application/pdf", len(PDF))]
    assert bytes(adj[0]["datos"]) == PNG
    # El formulario de evaluación ofrece el campo de archivos; el de contacto no.
    pagina = client.get("/evaluacion").text  # el landing ya no tiene formularios: la evaluación vive en su página y en el panel
    assert 'enctype="multipart/form-data"' in pagina and pagina.count('name="fotos"') == 1


@pytest.mark.parametrize("archivos, error", [
    ([("foto.jpg", b"no soy una imagen", "image/jpeg")], "JPG, PNG or WEBP"),               # el tipo se mira en el contenido
    ([(f"f{i}.png", PNG, "image/png") for i in range(5)], "up to 4 files"),
    ([("grande.png", PNG + b"0" * solicitudes.MAX_BYTES, "image/png")], "5 MB max"),
])
def test_adjuntos_invalidos_no_guardan_nada(client, conn, archivos, error):
    r = enviar(client, archivos)
    assert r.status_code == 200 and error in r.text and 'value="Jane Doe"' in r.text   # el formulario conserva lo escrito
    assert cuenta(conn, "solicitud_contacto") == 0 and cuenta(conn, "solicitud_adjunto") == 0


def test_un_campo_de_archivo_vacio_no_cuenta(client, conn):
    assert enviar(client, [("", b"", "application/octet-stream")]).status_code == 200
    assert cuenta(conn, "solicitud_contacto") == 1 and cuenta(conn, "solicitud_adjunto") == 0


def test_aviso_a_la_clinica_y_acuse_en_el_idioma_de_quien_escribe(client, conn):
    canal_correo()
    config.set_(conn, "correo_avisos_solicitudes", CLINICA)
    conn.commit()
    enviar(client, [("sonrisa.png", PNG, "image/png")])
    enviar(client, idioma="es", nombre="Luisa Gómez", correo="luisa@example.com", interes="contacto")
    assert canales.CorreoPrueba.ENVIADOS == []        # nada sale dentro de la petición
    tasks.cycle(conn)
    enviados = {(e["para"], e["asunto"]): e["texto"] for e in canales.CorreoPrueba.ENVIADOS}
    assert len(enviados) == 4
    aviso = enviados[(CLINICA, "Nueva solicitud web: Evaluación virtual – Jane Doe")]
    assert "Archivos adjuntos: 1" in aviso and "País: Estados Unidos" in aviso and "/panel/bandejas?b=contactos" in aviso
    assert "within 24 hours" in enviados[("jane@example.com", "We received your request – Blissens Odontología")]
    assert "próximas 24 horas" in enviados[("luisa@example.com", "Recibimos tu solicitud – Blissens Odontología")]
    assert conn.execute("select count(*) n from solicitud_contacto where aviso_enviado_en is null or acuse_enviado_en is null"
                        ).fetchone()["n"] == 0
    tasks.cycle(conn)
    assert len(canales.CorreoPrueba.ENVIADOS) == 4    # cada correo sale una vez


def test_sin_correo_no_hay_acuse_y_sin_destinatario_no_hay_aviso(client, conn):
    canal_correo()
    conn.commit()
    enviar(client, correo="")
    assert cuenta(conn, "tarea_programada") == 0
    tasks.cycle(conn)
    assert canales.CorreoPrueba.ENVIADOS == []


def test_si_el_proveedor_falla_el_correo_se_reintenta(client, conn):
    canal_correo()
    conn.commit()
    canales.CorreoPrueba.FALLAR = True
    enviar(client)
    tasks.cycle(conn)
    assert canales.CorreoPrueba.ENVIADOS == [] and ultima(conn)["acuse_enviado_en"] is None
    t = conn.execute("select estado, intentos from tarea_programada where tipo='correo_solicitud'").fetchone()
    assert (t["estado"], t["intentos"]) == ("pendiente", 1)


def test_la_recepcion_ve_descarga_y_vincula_la_solicitud(mundo, conn):  # noqa: F811
    web = TestClient(app, follow_redirects=False)
    enviar(web, [("sonrisa.png", PNG, "image/png")])
    fila = next(c for c in mundo.aux.get(f"{API}/bandejas/contactos").json() if c["origen"] == "sitio")
    assert fila["interes"] == "evaluacion_virtual" and fila["pais"] == "Estados Unidos"
    prospecto = conn.execute("select id, etapa from paciente where correo='jane@example.com'").fetchone()
    assert fila["paciente_id"] == prospecto["id"] and prospecto["etapa"] == "prospecto"   # ya nace con su ficha
    assert [(a["nombre"], a["tamano"]) for a in fila["adjuntos"]] == [("sonrisa.png", len(PNG))]

    url = f"{API}/contactos/{fila['id']}/adjuntos/{fila['adjuntos'][0]['id']}"
    r = mundo.aux.get(url)
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert r.headers["content-disposition"].startswith("attachment;") and r.headers["x-content-type-options"] == "nosniff"
    assert mundo.esp1.get(url).status_code == 403                       # solo la recepción
    assert TestClient(app).get(url).status_code == 401
    assert mundo.aux.get(f"{API}/contactos/{fila['id']}/adjuntos/999999").status_code == 404

    sin_correo = make_patient(conn, "Jane", "Doe")
    conn.execute("update paciente set correo=null where id=%s", (sin_correo,))
    conn.commit()
    r = mundo.aux.post(f"{API}/contactos/{fila['id']}/paciente", json={"paciente_id": sin_correo})
    assert r.status_code == 200, r.text
    p = conn.execute("select correo, acepta_correo, internacional from paciente where id=%s", (sin_correo,)).fetchone()
    assert (p["correo"], p["acepta_correo"], p["internacional"]) == ("jane@example.com", False, True)
    fila = next(c for c in mundo.aux.get(f"{API}/bandejas/contactos").json() if c["id"] == fila["id"])
    assert fila["paciente_id"] == sin_correo and fila["paciente"] == "Jane Doe"
    assert mundo.aux.post(f"{API}/contactos/{fila['id']}/paciente", json={"paciente_id": 999999}).status_code == 404
    assert mundo.aux.post(f"{API}/contactos/999999/paciente", json={"paciente_id": sin_correo}).status_code == 404


def test_anonimizar_borra_las_solicitudes_vinculadas_y_las_de_su_correo(client, conn):
    p = make_patient(conn, "Jane", "Doe")
    conn.execute("update paciente set correo='jane@example.com', celular=null where id=%s", (p,))
    conn.commit()
    enviar(client, [("sonrisa.png", PNG, "image/png")])                     # se asocia a Jane por su correo
    enviar(client, correo="JANE@example.com", celular="")                      # solo dejó el correo
    enviar(client, nombre="Otra Persona", correo="otra@example.com", celular="+1 305 555 0199")
    vinculada = conn.execute("select id from solicitud_contacto where nombre='Jane Doe' order by id limit 1").fetchone()["id"]
    exportado = privacidad.exportar_paciente(conn, p)["solicitudes_web"]
    assert [s["id"] for s in exportado] == [vinculada, vinculada + 1] and exportado[0]["adjuntos"][0]["nombre"] == "sonrisa.png"
    privacidad.anonimizar_paciente(conn, p)
    assert [r["nombre"] for r in conn.execute("select nombre from solicitud_contacto")] == ["Otra Persona"]
    assert cuenta(conn, "solicitud_adjunto") == 0


def test_un_correo_compartido_con_otro_paciente_no_borra_sus_solicitudes(client, conn):
    enviar(client, correo="hogar@example.com")
    a, b = make_patient(conn, "Ana", "Uno"), make_patient(conn, "Beto", "Dos")
    conn.execute("update paciente set correo='hogar@example.com' where id in (%s,%s)", (a, b))
    privacidad.anonimizar_paciente(conn, a)
    assert cuenta(conn, "solicitud_contacto") == 1


def test_el_tipo_se_decide_por_el_contenido():
    assert solicitudes.tipo_de(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert solicitudes.tipo_de(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert solicitudes.tipo_de(b"<svg onload=alert(1)>") is None
    limpio = solicitudes.validar_adjuntos([solicitudes.Adjunto('../../"x"\n.png', PNG)])
    assert limpio[0][0] == "....x.png"
