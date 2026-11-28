"""Asistente de la landing pública: botones sin modelo (capa 1) y asistente de IA del visitante (capa 2).

Ninguna prueba llama a la API real: el cliente falso inyecta respuestas fijas con `dependency_overrides`.
"""
import re

import pytest
from fastapi.testclient import TestClient

from estudia import config, links
from estudia.asistente.instrucciones import RESPUESTAS
from estudia.web import asistente_visitante as av
from estudia.web.app import crear_app, limite_solicitudes

from .conftest import make_pro, svc
from .test_asistente_conversacion import Falso, llama, responde, usar

HX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def _limites():
    av.limite_visitantes.reiniciar()
    limite_solicitudes.reiniciar()
    yield
    av.limite_visitantes.reiniciar()
    limite_solicitudes.reiniciar()


@pytest.fixture
def app(conn):
    a = crear_app("local", asistente=True)
    yield a
    a.dependency_overrides.clear()


@pytest.fixture
def cliente(app):
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def activo(conn):
    config.set_(conn, "asistente_visitantes", True)
    conn.commit()


def inyectar(app, falso):
    app.dependency_overrides[av.cliente_del_modelo] = lambda: falso


def escribir(cliente, texto="Hola", **extra):
    return cliente.post("/sitio/asistente", data={"texto": texto, "conversacion": "", **extra}, headers=HX)


# ------------------------------------------------------------------ capa 1

@pytest.mark.parametrize("ruta", ["/", "/en"])
def test_la_landing_trae_el_panel_estatico_con_cuatro_opciones(cliente, ruta):
    r = cliente.get(ruta)
    assert r.status_code == 200 and 'id="asistente"' in r.text and 'id="asist-cuerpo"' in r.text
    assert len(re.findall(r'hx-get="/sitio/asistente/paso/(?:agendar|afuera|direccion|otra)', r.text)) == 4
    assert "onclick" not in r.text.split('id="asistente"')[1].split("</aside>")[0]


def test_cada_paso_devuelve_su_formulario(cliente):
    def paso(clave, **q):
        r = cliente.get(f"/sitio/asistente/paso/{clave}", params=q, headers=HX)
        assert r.status_code == 200, r.text
        return r.text
    assert "/agendar/identificar" in paso("agendar") and "no_hay" not in paso("agendar")
    afuera = paso("afuera")
    assert 'value="evaluacion_virtual"' in afuera and "/sitio/solicitud" in afuera or "solicitud" in afuera
    direccion = paso("direccion", idioma="en")
    assert "google" in direccion and "/sitio/asistente/paso/agendar" in direccion
    assert "/sitio/asistente/paso/afuera" in paso("inicio")


def test_un_paso_desconocido_es_404_y_sin_htmx_redirige_a_la_seccion(cliente):
    assert cliente.get("/sitio/asistente/paso/nada", headers=HX).status_code == 404
    r = cliente.get("/sitio/asistente/paso/agendar")
    assert r.status_code == 303 and r.headers["location"].endswith("#agendar")
    assert cliente.get("/sitio/asistente/paso/afuera", params={"idioma": "en"}).headers["location"].startswith("/en")


def test_otra_pregunta_muestra_el_cuadro_solo_si_esta_disponible_y_si_no_el_contacto(conn, app, cliente):
    sin = cliente.get("/sitio/asistente/paso/otra", headers=HX)
    assert 'value="contacto"' in sin.text and 'name="texto"' not in sin.text and "set-cookie" not in sin.headers
    config.set_(conn, "asistente_visitantes", True)
    conn.commit()
    con = cliente.get("/sitio/asistente/paso/otra", headers=HX)
    assert 'name="texto"' in con.text and "/sitio/asistente\"" in con.text and links.COOKIE_VISITANTE in con.headers["set-cookie"]
    sin_ia = TestClient(crear_app("local"), follow_redirects=False)  # sin clave: no hay ruta de IA
    assert 'name="texto"' not in sin_ia.get("/sitio/asistente/paso/otra", headers=HX).text


def test_registro_con_servicio_preseleccionado_lleva_a_nueva_con_los_datos(conn, cliente):
    pro = make_pro(conn)
    s = svc(conn)
    conn.commit()
    r = cliente.post("/agendar/identificar", headers=HX, data={
        "nombres": "Ana", "apellidos": "Prueba", "documento": "9123456", "celular": "3001112233", "consentimiento": "on",
        "servicio": str(s), "profesional": str(pro), "desde": "2026-11-17T09:00", "idioma": "es"})
    loc = r.headers.get("hx-redirect") or r.headers.get("location") or ""
    assert "/nueva" in loc and f"servicio={s}" in loc and f"profesional={pro}" in loc, (r.status_code, loc, r.text[:300])


# ------------------------------------------------------------------ capa 2

def test_el_post_es_404_si_el_interruptor_esta_apagado(app, cliente):
    inyectar(app, Falso())
    assert escribir(cliente).status_code == 404


def test_un_mensaje_responde_firma_la_cookie_y_redacta_los_datos_personales(conn, app, cliente, activo):
    falso = Falso(responde("Con gusto."))
    inyectar(app, falso)
    r = escribir(cliente, "Mi correo es ana@correo.com y mi cel 3001112233")
    assert r.status_code == 200 and "Con gusto." in r.text
    assert "ana@correo.com" not in r.text and "3001112233" not in r.text and "[dato omitido]" in r.text
    assert "3001112233" not in str(falso.peticiones)
    cookie = cliente.cookies.get(links.COOKIE_VISITANTE)
    assert cookie and links.leer_visitante(cookie)
    conn.rollback()
    fila = conn.execute("select perfil, visitante, paciente_id, usuario_id from asistente_conversacion").fetchone()
    assert fila["perfil"] == "visitante" and fila["visitante"] == links.leer_visitante(cookie)
    assert fila["paciente_id"] is None and fila["usuario_id"] is None


def test_una_cookie_manipulada_se_ignora_y_se_entrega_otra(app, cliente, activo):
    inyectar(app, Falso(responde("ok")))
    r = cliente.post("/sitio/asistente", data={"texto": "Hola"}, headers={**HX, "Cookie": f"{links.COOKIE_VISITANTE}=falsificada.abc.def"})
    nueva = re.search(rf"{links.COOKIE_VISITANTE}=([^;]+)", r.headers["set-cookie"]).group(1)
    assert links.leer_visitante(nueva) and nueva != "falsificada.abc.def"


def test_el_honeypot_responde_normal_sin_llamar_al_modelo(conn, app, cliente, activo):
    falso = Falso()
    inyectar(app, falso)
    r = escribir(cliente, "Hola", web="http://spam")
    assert r.status_code == 200 and RESPUESTAS["visitante"]["es"]["fallo"] in r.text and falso.peticiones == []
    conn.rollback()
    assert conn.execute("select count(*) n from asistente_conversacion").fetchone()["n"] == 0


def test_el_limite_por_ip_da_la_respuesta_fija(app, cliente, activo, monkeypatch):
    monkeypatch.setattr(av, "limite_visitantes", av.LimiteVentana(maximo=1, segundos=600))
    inyectar(app, Falso(responde("uno"), responde("dos")))
    assert "uno" in escribir(cliente).text
    r = escribir(cliente)
    assert RESPUESTAS["visitante"]["es"]["limite"] in r.text and "dos" not in r.text


def test_una_propuesta_de_registro_pinta_el_formulario_con_la_preseleccion(conn, app, cliente, activo):
    pro = make_pro(conn)
    s = svc(conn)
    conn.commit()
    inyectar(app, Falso(llama(usar("proponer_registro", {"servicio_id": s})), responde("Déjame tu registro.")))
    r = escribir(cliente, "Quiero agendar")
    assert "Déjame tu registro." in r.text and "/agendar/identificar" in r.text and f'name="servicio" value="{s}"' in r.text
    assert pro  # el profesional existe pero no se preselecciona


def test_texto_demasiado_largo_da_error_legible_sin_modelo(app, cliente, activo):
    falso = Falso()
    inyectar(app, falso)
    r = escribir(cliente, "x" * 400)
    assert falso.peticiones == [] and r.status_code in (200, 422) and "300" in r.text


def test_una_conversacion_de_otro_visitante_se_comporta_como_inexistente(conn, app, cliente, activo):
    inyectar(app, Falso(responde("ok"), responde("no")))
    r = escribir(cliente)
    cid = re.search(r'name="conversacion" value="(\d+)"', r.text).group(1)
    otro = TestClient(app, follow_redirects=False)
    r2 = otro.post("/sitio/asistente", data={"texto": "Hola", "conversacion": cid}, headers=HX)
    assert "no" != r2.text and RESPUESTAS["visitante"]["es"]["fallo"] in r2.text
