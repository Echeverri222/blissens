"""SEO técnico, datos estructurados JSON-LD, robots/sitemap/llms, noindex y caché de estáticos."""
import json
import re
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from estudia.web.app import app


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


def _extraer_json_ld(html: str) -> dict:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert m, "Falta el bloque JSON-LD en la landing"
    return json.loads(m.group(1))


def test_robots_txt_permite_landing_y_bloquea_rutas_privadas(client, monkeypatch):
    from estudia.web import app as web
    monkeypatch.setattr(web.db, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no DB")))

    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "User-agent: *" in body
    assert "Allow: /" in body
    for privada in ("/panel", "/api/", "/p/", "/simulador", "/correo/", "/sitio/", "/canales/"):
        assert f"Disallow: {privada}" in body
    assert "Disallow: /static" not in body
    assert "Sitemap: http://localhost:8000/sitemap.xml" in body


def test_sitemap_xml_bilingue_valido_sin_bd(client, monkeypatch):
    from estudia.web import app as web
    monkeypatch.setattr(web.db, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no DB")))

    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "xml" in r.headers["content-type"]
    root = ET.fromstring(r.text)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}
    locs = [el.text for el in root.findall("s:url/s:loc", ns)]
    assert locs == ["http://localhost:8000/", "http://localhost:8000/en"]
    for url_el in root.findall("s:url", ns):
        hreflangs = {el.attrib["hreflang"]: el.attrib["href"] for el in url_el.findall("x:link", ns)}
        assert hreflangs == {
            "es": "http://localhost:8000/",
            "en": "http://localhost:8000/en",
            "x-default": "http://localhost:8000/",
        }


def test_llms_txt_resume_clinica_sin_bd(client, monkeypatch):
    from estudia.web import app as web
    monkeypatch.setattr(web.db, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no DB")))

    r = client.get("/llms.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "Blissens" in r.text and "Medellín" in r.text
    assert "http://localhost:8000/" in r.text and "http://localhost:8000/en" in r.text
    assert "info@blissens.com" in r.text


def test_landing_es_y_en_incluyen_json_ld_dentist_y_metadatos_sociales(client):
    for ruta, locale, alt_locale, servicio_esperado in (
        ("/", "es_CO", "en_US", "Diseño de sonrisa"),
        ("/en", "en_US", "es_CO", "Smile design"),
    ):
        r = client.get(ruta)
        assert r.status_code == 200
        html = r.text
        assert '<meta name="robots" content="index, follow, max-image-preview:large">' in html
        assert "X-Robots-Tag" not in r.headers
        assert f'<meta property="og:url" content="http://localhost:8000{ruta}">' in html
        assert f'<meta property="og:locale" content="{locale}">' in html
        assert f'<meta property="og:locale:alternate" content="{alt_locale}">' in html
        assert '<meta property="og:image:alt"' in html
        assert '<meta name="twitter:title"' in html
        assert '<meta name="twitter:description"' in html
        assert '<meta name="twitter:image" content="http://localhost:8000/static/sitio/New-Team.jpg">' in html

        datos = _extraer_json_ld(html)
        assert datos["@context"] == "https://schema.org"
        grafo = {item["@type"]: item for item in datos["@graph"]}
        assert "Dentist" in grafo and "WebSite" in grafo
        clinica = grafo["Dentist"]
        assert clinica["name"] == "Blissens"
        assert clinica["telephone"] == "+573053069616"
        assert clinica["email"] == "info@blissens.com"
        assert clinica["address"]["addressLocality"] == "Medellín"
        assert clinica["address"]["addressCountry"] == "CO"
        servicios = [o["itemOffered"]["name"] for o in clinica["hasOfferCatalog"]["itemListElement"]]
        assert servicio_esperado in servicios
        assert len(clinica["employee"]) == 3


def test_rutas_privadas_e_interiores_tienen_noindex_y_x_robots_tag(client, conn):
    conn.commit()
    ag = client.get("/agendar")
    assert ag.status_code == 200
    assert '<meta name="robots" content="noindex, follow">' in ag.text
    assert ag.headers.get("x-robots-tag") == "noindex, follow"
    # Descripción propia distinta a la de la landing
    assert "Toma menos de un minuto" in re.search(r'<meta name="description" content="([^"]+)"', ag.text).group(1)

    sim = client.get("/simulador")
    assert sim.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in sim.text
    assert sim.headers.get("x-robots-tag") == "noindex, nofollow"
    assert sim.headers.get("cache-control") == "no-store"

    api_r = client.get("/api/v1/marca")
    assert api_r.headers.get("x-robots-tag") == "noindex, nofollow"


def test_estaticos_usan_cache_control_y_services_jpg_es_ligero(client):
    r_ver = client.get("/static/sitio/sitio.css?v=1234")
    assert r_ver.status_code == 200
    assert "immutable" in r_ver.headers.get("cache-control", "")

    r_img = client.get("/static/sitio/Services.jpg")
    assert r_img.status_code == 200
    assert "max-age=" in r_img.headers.get("cache-control", "")
    assert len(r_img.content) < 250_000
