"""Landing pública: copia ES/EN, solicitudes al buzón de contacto y agendamiento desde la landing."""
import re

import pytest
from fastapi.testclient import TestClient

from estudia.web.app import app, limite_solicitudes


@pytest.fixture(autouse=True)
def _sin_limite():
    limite_solicitudes.reiniciar()
    yield
    limite_solicitudes.reiniciar()


@pytest.fixture
def client(conn):
    conn.commit()
    return TestClient(app, follow_redirects=False)


def test_root_is_spanish_landing_and_en_is_english(client):
    es = client.get("/")
    assert es.status_code == 200 and '<html lang="es"' in es.text
    assert "SONRÍA Y MIRE" not in es.text and "Sonría y mire" in es.text and "Vivo en Medellín" in es.text
    en = client.get("/en")
    assert en.status_code == 200 and '<html lang="en"' in en.text
    assert "I live abroad" in en.text and "Our team" in en.text
    assert 'href="/panel"' in es.text and 'id="agendar"' in es.text


@pytest.mark.parametrize("ruta", ["/", "/en"])
def test_la_landing_no_tiene_formularios_fuera_del_panel(client, ruta):
    html = client.get(ruta).text
    fuera = html.split('<aside class="asist"')[0]
    assert "<form" not in fuera and "<form" not in html  # el panel arranca con las opciones, sin formularios
    assert 'id="reservar"' not in html and "/sitio/solicitud" not in html and "/agendar/identificar" not in html


def test_los_botones_abren_el_asistente_y_tienen_enlace_de_respaldo(client):
    es = client.get("/").text
    pares = set(re.findall(r'<a [^>]*href="([^"]+)"[^>]*data-abrir-asistente="(\w+)"', es))
    assert ("/agendar", "agendar") in pares and ("/evaluacion", "afuera") in pares
    for paquete in ("premium", "standard", "essential"):
        assert (f"/experiencia?idioma=es&amp;paquete={paquete}", "experiencia") in pares
    assert not re.search(r"<button[^>]*data-paquete", es) and "tel:" in es and "wa.me/573053069616" in es and "maps" in es
    en = set(re.findall(r'<a [^>]*href="([^"]+)"[^>]*data-abrir-asistente="(\w+)"', client.get("/en").text))
    assert ("/agendar?idioma=en", "agendar") in en and ("/evaluacion?idioma=en", "afuera") in en
    assert ("/experiencia?idioma=en&amp;paquete=premium", "experiencia") in en
    assert "/agendar?idioma=en" in client.get("/en").text.split('class="barra"')[1]


@pytest.mark.parametrize("ruta,lang,interes", [("/evaluacion", "es", "evaluacion_virtual"), ("/contacto", "es", "contacto"),
                                                ("/experiencia", "es", "experiencia"), ("/evaluacion?idioma=en", "en", "evaluacion_virtual"),
                                                ("/contacto?idioma=en", "en", "contacto")])
def test_paginas_aparte_de_solicitud_sin_javascript(client, ruta, lang, interes):
    r = client.get(ruta)
    assert r.status_code == 200 and f'<html lang="{lang}"' in r.text and f'name="interes" value="{interes}"' in r.text
    assert 'action="/sitio/solicitud"' in r.text and f'name="idioma" value="{lang}"' in r.text and "noindex" in r.text
    assert ("name=\"pais\"" in r.text) == (interes == "evaluacion_virtual")


def test_pagina_de_experiencia_preselecciona_el_paquete(client):
    r = client.get("/experiencia?idioma=en&paquete=standard")
    assert re.search(r'<option value="standard"\s+selected', r.text) and "Please select a package" in r.text
    assert "selected" not in client.get("/experiencia?paquete=otro").text  # un paquete inválido no se preselecciona


def test_agendar_en_ingles(client):
    r = client.get("/agendar?idioma=en")
    assert r.status_code == 200 and '<html lang="en"' in r.text and "Book your appointment" in r.text


def test_landing_makes_no_third_party_requests(client):
    for ruta in ("/", "/en", "/agendar"):
        html = re.sub(r'<link rel="(canonical|alternate)"[^>]*>', "", client.get(ruta).text)  # no cargan nada
        html = re.sub(r"<a\b[^>]*>", "", html)  # los enlaces (WhatsApp, mapa) son navegación, no cargan nada
        assert not re.search(r'(src|href|action)="(https?:)?//', html), ruta
        assert not re.search(r"url\(['\"]?https?://", html), ruta
    css = client.get("/static/sitio/sitio.css").text
    assert not re.search(r"https?://", css)
    for f in ("sitio.js", "fuentes/inter-var.woff2", "fuentes/cardo-400.woff2"):
        assert client.get(f"/static/sitio/{f}").status_code == 200


def test_panel_and_booking_still_work(client):
    # En CI el panel no se construye: /panel responde el aviso «make panel» (503). Lo que importa es que la ruta exista.
    p = client.get("/panel")
    assert p.status_code in (200, 307, 302) or (p.status_code == 503 and "make panel" in p.text)
    r = client.get("/agendar")
    assert r.status_code == 200 and "Agende su cita" in r.text and 'name="documento"' in r.text


def test_experience_form_creates_contact_request(client, conn):
    r = client.post("/sitio/solicitud", headers={"HX-Request": "true"},
                    data={"interes": "experiencia", "paquete": "premium", "nombre": "Visitante", "correo": "v@example.com",
                          "celular": "+1 305 555 0100", "mensaje": "Hola", "consentimiento": "1", "idioma": "en"})
    assert r.status_code == 200 and "excited to be part" in r.text
    fila = conn.execute("select * from solicitud_contacto order by id desc limit 1").fetchone()
    assert (fila["interes"], fila["paquete"], fila["nombre"], fila["idioma"]) == ("experiencia", "premium", "Visitante", "en")
    assert "Experiencia · Premium" in fila["nota"] and not fila["gestionada"]
    assert fila["celular"].startswith("+1")


def test_virtual_assessment_and_contact_forms_and_validation(client, conn):
    base = {"nombre": "Ana", "correo": "ana@example.com", "consentimiento": "1"}
    assert client.post("/sitio/solicitud", data={**base, "interes": "evaluacion_virtual", "pais": "España"}).status_code == 200
    assert "Evaluación virtual" in conn.execute("select nota from solicitud_contacto order by id desc limit 1").fetchone()["nota"]
    antes = conn.execute("select count(*) n from solicitud_contacto").fetchone()["n"]
    for mal in ({"interes": "contacto", "nombre": "", "correo": "a@b.co", "consentimiento": "1"},
                {"interes": "contacto", "nombre": "A", "correo": "", "consentimiento": "1"},
                {"interes": "contacto", "nombre": "A", "correo": "a@b.co"},
                {"interes": "experiencia", "nombre": "A", "correo": "a@b.co", "consentimiento": "1"},
                {"interes": "contacto", "nombre": "A", "correo": "a@b.co", "consentimiento": "1", "web": "robot"}):
        assert client.post("/sitio/solicitud", data=mal).status_code == 200
    assert conn.execute("select count(*) n from solicitud_contacto").fetchone()["n"] == antes
    assert client.post("/sitio/solicitud", data={**base, "interes": "otro"}).status_code == 422


def test_identify_from_landing_uses_htmx_redirect(client):
    r = client.post("/agendar/identificar", headers={"HX-Request": "true"},
                    data={"documento": "9001", "celular": "3001239999", "nombres": "Luz", "consentimiento": "1"})
    assert r.status_code == 200 and r.headers["HX-Redirect"].endswith("/nueva")
    r = client.post("/agendar/identificar", headers={"HX-Request": "true"}, data={"documento": "9002", "celular": "3001230000"})
    assert r.text.lstrip().startswith("<form") and "<html" not in r.text and "primera vez" in r.text


def _solicitudes(conn):
    return conn.execute("select count(*) n from solicitud_contacto").fetchone()["n"]


def test_junk_phone_without_email_is_rejected_and_nothing_is_inserted(client, conn):
    antes = _solicitudes(conn)
    base = {"interes": "contacto", "nombre": "A", "consentimiento": "1"}
    r = client.post("/sitio/solicitud", data={**base, "celular": "abc"})
    assert r.status_code == 200 and "correo válido o un celular" in r.text
    r = client.post("/sitio/solicitud", data={**base, "celular": "12", "idioma": "en"})
    assert "valid email or a phone number" in r.text
    assert _solicitudes(conn) == antes
    # un teléfono internacional razonable sí se acepta; uno basura con correo válido se guarda sin teléfono
    assert client.post("/sitio/solicitud", data={**base, "celular": "+44 20 7946 0958"}).status_code == 200
    assert conn.execute("select celular from solicitud_contacto order by id desc limit 1").fetchone()["celular"].startswith("+44")
    client.post("/sitio/solicitud", data={**base, "celular": "abc", "correo": "a@b.co"})
    assert conn.execute("select celular from solicitud_contacto order by id desc limit 1").fetchone()["celular"] == ""


def test_site_form_is_rate_limited_per_ip(client, conn):
    datos = {"interes": "contacto", "nombre": "A", "correo": "a@b.co", "consentimiento": "1"}
    antes = _solicitudes(conn)
    for _ in range(5):
        assert client.post("/sitio/solicitud", data=datos).status_code == 200
    r = client.post("/sitio/solicitud", data=datos)
    assert r.status_code == 429 and "varias solicitudes" in r.text
    assert "several requests" in client.post("/sitio/solicitud", data={**datos, "idioma": "en"}).text
    assert _solicitudes(conn) == antes + 5
    limite_solicitudes.reiniciar()
    assert client.post("/sitio/solicitud", data=datos).status_code == 200


def test_landing_renders_without_database_or_business(client, monkeypatch):
    from estudia.web import app as web

    def sin_base(*a, **k):
        raise AssertionError("la landing no debe abrir conexión")
    monkeypatch.setattr(web.db, "connect", sin_base)
    for ruta in ("/", "/en"):
        assert client.get(ruta).status_code == 200


def test_identify_errors_and_consent_follow_language(client):
    r = client.post("/agendar/identificar", headers={"HX-Request": "true"},
                    data={"documento": "9003", "celular": "123", "idioma": "en"})
    assert "Check your ID number" in r.text and "Revisa tu documento" not in r.text
    r = client.post("/agendar/identificar", headers={"HX-Request": "true"},
                    data={"documento": "9004", "celular": "3001230001", "nombres": "Luz", "idioma": "en"})
    assert "I authorize" in r.text and "you@email.com" in r.text and "Autorizo" not in r.text
    r = client.post("/agendar/identificar", headers={"HX-Request": "true"},
                    data={"documento": "9005", "celular": "3001230002", "nombres": "Luz", "idioma": "en"})
    assert "To register we need your authorization" in r.text


def test_seo_links_only_on_landing_and_footer_scopes(client):
    es = client.get("/").text
    assert 'rel="canonical" href="http://localhost:8000/"' in es and 'hreflang="x-default"' in es and 'hreflang="en" href="http://localhost:8000/en"' in es
    assert 'og:image" content="http://localhost:8000/static/sitio/New-Team.jpg"' in es
    assert 'href="/panel"' in es and "info@blissens.com" in es
    interior = client.get("/agendar").text
    assert 'rel="canonical"' not in interior and "hreflang=\"x-default\"" not in interior
    assert 'href="/panel"' not in interior and "info@blissens.com" not in interior and "+57 305 306 9616" in interior


def test_x_forwarded_for_no_evade_el_limite(client):
    datos = {"interes": "contacto", "nombre": "Ana", "correo": "ana@example.com", "consentimiento": "1"}
    for _ in range(5):
        assert client.post("/sitio/solicitud", data=datos).status_code == 200
    for i in range(3):
        r = client.post("/sitio/solicitud", data=datos, headers={"X-Forwarded-For": f"10.0.0.{i}"})
        assert r.status_code == 429


def test_entrada_no_confia_en_cualquier_proxy():
    from pathlib import Path

    from estudia import settings
    sh = (Path(__file__).parent.parent / "scripts" / "entrada.sh").read_text(encoding="utf-8")
    assert "--forwarded-allow-ips='*'" not in sh and "TRUSTED_PROXIES" in sh
    assert settings.TRUSTED_PROXIES != "*"
