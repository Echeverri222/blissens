"""Asistente del paciente en su enlace personal (docs/prd-asistente.md, §7 y §10).

Ninguna prueba llama a la API real: el cliente falso de `test_asistente_conversacion` entrega respuestas fijas y la prueba lo
inyecta con `app.dependency_overrides[cliente_del_modelo]`.
"""
import re
import time
from html import unescape
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from itsdangerous.timed import TimestampSigner

from estudia import agenda, config, db, familia, links
from estudia.asistente.instrucciones import RESPUESTAS
from estudia.web import asistente_paciente as ap
from estudia.web.app import crear_app

from .conftest import at, book, make_patient, make_pro, svc
from .test_asistente_conversacion import Falso, llama, mensaje, pensar, responde, usar

CEL = "+573001112233"
FALLO = RESPUESTAS["paciente"]["fallo"]
LIMITE = RESPUESTAS["paciente"]["limite"]
HX = {"HX-Request": "true"}


@pytest.fixture
def mundo(conn):
    pro = make_pro(conn, "Dra. Uno")
    ana = make_patient(conn, "Ana María", "Pérez", doc="7654321", celular=CEL)
    luis = make_patient(conn, "Luis", "Gómez", doc="1112223", celular="+573009998877")
    mateo = conn.execute(
        "insert into paciente(nombres, apellidos, documento, celular, fecha_nacimiento, responsable_id, parentesco, consentimiento_en, "
        "consentimiento_por) values ('Mateo','Pérez','5001',%s,'2018-03-04',%s,'hijo',now(),%s) returning id", (CEL, ana, ana)).fetchone()["id"]
    cita_ana = book(conn, ana, pro, at(1, "09:00"))
    cita_mateo = book(conn, mateo, pro, at(2, "10:00"))
    config.set_(conn, "asistente_pacientes", True)
    conn.commit()
    return SimpleNamespace(pro=pro, ana=ana, luis=luis, mateo=mateo, cita_ana=cita_ana, cita_mateo=cita_mateo,
                           t_ana=links.make_token(ana, 1), t_luis=links.make_token(luis, 1), t_mateo=links.make_token(mateo, 1))


@pytest.fixture(autouse=True)
def _limite():
    ap.limite_asistente.reiniciar()
    yield
    ap.limite_asistente.reiniciar()


@pytest.fixture
def app(mundo):
    a = crear_app("local", asistente=True)
    yield a
    a.dependency_overrides.clear()


@pytest.fixture
def cliente(app):
    return TestClient(app, follow_redirects=False)


def inyectar(app, falso):
    app.dependency_overrides[ap.cliente_del_modelo] = lambda: falso


def consentir(cliente, token, accion="aceptar"):
    r = cliente.post(f"/p/{token}/asistente/consentimiento", data={"accion": accion})
    assert r.status_code == 303, r.text
    return r


def escribir(cliente, token, texto="Hola", conversacion="", hx=True, **extra):
    return cliente.post(f"/p/{token}/asistente", data={"texto": texto, "conversacion": conversacion, **extra},
                        headers=HX if hx else {})


def conversacion_de(r) -> str:
    return re.search(r'id="conversacion" name="conversacion" value="(\d*)"', r.text).group(1)


def cuenta(conn, tabla):
    conn.rollback()
    return conn.execute(f"select count(*) n from {tabla}").fetchone()["n"]


def paciente(conn, pid):
    conn.rollback()
    return conn.execute("select * from paciente where id=%s", (pid,)).fetchone()


def campos(html, accion):
    """Los campos ocultos del formulario que envía a `accion`."""
    f = re.search(r'<form[^>]*action="%s".*?</form>' % re.escape(accion), html, re.S).group(0)
    return {n: unescape(v) for n, v in re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', f)}


# ------------------------------------------------------------------ enlaces y interruptores

def enlace_vencido(pid):
    with pytest.MonkeyPatch.context() as m:
        m.setattr(TimestampSigner, "get_timestamp", lambda self: int(time.time()) - 40 * 86400)
        return links.make_token(pid, 1)


def test_cada_ruta_con_un_enlace_invalido_o_vencido_es_404(mundo, cliente):
    for token in ("basura", enlace_vencido(mundo.ana)):
        assert cliente.get(f"/p/{token}/asistente").status_code == 404
        assert cliente.post(f"/p/{token}/asistente", data={"texto": "hola"}).status_code == 404
        assert cliente.post(f"/p/{token}/asistente/consentimiento", data={"accion": "aceptar"}).status_code == 404
        assert cliente.post(f"/p/{token}/contacto").status_code == 404


def test_con_el_interruptor_apagado_las_rutas_no_existen_y_mis_citas_no_ofrece_el_asistente(mundo, cliente, conn):
    assert f"/p/{mundo.t_ana}/asistente" in cliente.get(f"/p/{mundo.t_ana}").text  # encendido: hay acceso (aun sin consentir)
    config.set_(conn, "asistente_pacientes", False)
    conn.commit()
    t = mundo.t_ana
    for r in (cliente.get(f"/p/{t}/asistente"), cliente.post(f"/p/{t}/asistente", data={"texto": "hola"}),
              cliente.post(f"/p/{t}/asistente/consentimiento", data={"accion": "aceptar"}), cliente.post(f"/p/{t}/contacto")):
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}  # igual que una ruta que no existe
    assert "asistente" not in cliente.get(f"/p/{t}").text.lower()
    assert cuenta(conn, "solicitud_contacto") == 0
    assert not conn.execute("select acepta_asistente from paciente where id=%s", (mundo.ana,)).fetchone()["acepta_asistente"]


def test_sin_la_clave_las_rutas_no_estan_registradas_aunque_el_negocio_lo_encienda(mundo):
    sin = TestClient(crear_app("local", asistente=False), follow_redirects=False)
    t = mundo.t_ana
    assert sin.get(f"/p/{t}/asistente").status_code == 404
    assert sin.post(f"/p/{t}/contacto").status_code == 404
    assert "asistente" not in sin.get(f"/p/{t}").text.lower()  # la página de citas sí existe, sin acceso al asistente


# ------------------------------------------------------------------ consentimiento

def test_sin_consentimiento_se_pide_y_no_hay_chat_ni_llamada_al_modelo(mundo, app, cliente, conn):
    falso = Falso(responde("no debería salir"))
    inyectar(app, falso)
    r = cliente.get(f"/p/{mundo.t_ana}/asistente")
    assert r.status_code == 200 and "servicio de inteligencia artificial de un tercero" in r.text
    assert "Aceptar y continuar" in r.text and "No, gracias" in r.text and 'name="texto"' not in r.text
    r = escribir(cliente, mundo.t_ana, "¿Cuándo es mi cita?")
    assert r.status_code == 403 and falso.peticiones == []
    assert cuenta(conn, "asistente_conversacion") == 0


def test_aceptar_registra_el_consentimiento_y_abre_el_chat_y_retirarlo_lo_cierra(mundo, app, cliente, conn):
    inyectar(app, Falso(responde("Hola.")))
    assert consentir(cliente, mundo.t_ana).headers["location"] == f"/p/{mundo.t_ana}/asistente"
    a = paciente(conn, mundo.ana)
    assert a["acepta_asistente"] and a["consentimiento_asistente_en"] is not None and a["consentimiento_asistente_por"] is None
    m = paciente(conn, mundo.mateo)  # el hijo queda cubierto, anotado como dado por su responsable
    assert m["acepta_asistente"] and m["consentimiento_asistente_por"] == mundo.ana
    assert not paciente(conn, mundo.luis)["acepta_asistente"]
    pagina = cliente.get(f"/p/{mundo.t_ana}/asistente").text
    assert 'name="texto"' in pagina and "Que me llamen" in pagina and "Retirar mi autorización" in pagina
    assert conn.execute("select count(*) n from auditoria_acceso where accion='asistente:consentimiento' and paciente_id=%s",
                        (mundo.ana,)).fetchone()["n"] == 1
    conn.rollback()

    r = consentir(cliente, mundo.t_ana, "retirar")
    assert "/p/%s?aviso=" % mundo.t_ana in r.headers["location"]
    for pid in (mundo.ana, mundo.mateo):
        x = paciente(conn, pid)
        assert not x["acepta_asistente"] and x["consentimiento_asistente_en"] is None and x["consentimiento_asistente_por"] is None
    assert "servicio de inteligencia artificial" in cliente.get(f"/p/{mundo.t_ana}/asistente").text
    assert escribir(cliente, mundo.t_ana).status_code == 403
    assert conn.execute("select count(*) n from auditoria_acceso where accion='asistente:retiro'").fetchone()["n"] == 1
    conn.rollback()


def test_no_gracias_no_registra_nada(mundo, cliente, conn):
    r = consentir(cliente, mundo.t_ana, "rechazar")
    assert r.headers["location"] == f"/p/{mundo.t_ana}"
    assert not paciente(conn, mundo.ana)["acepta_asistente"]
    assert cliente.post(f"/p/{mundo.t_ana}/asistente/consentimiento", data={"accion": "otra"}).status_code == 422


def test_un_familiar_usa_el_consentimiento_de_su_responsable_y_no_lo_da_ni_lo_retira(mundo, app, cliente, conn):
    inyectar(app, Falso(responde("Hola.")))
    pagina = cliente.get(f"/p/{mundo.t_mateo}/asistente").text
    assert "decide si tu familia usa el asistente" in pagina and "Aceptar y continuar" not in pagina
    consentir(cliente, mundo.t_mateo)  # no hace nada
    assert not paciente(conn, mundo.mateo)["acepta_asistente"] and not paciente(conn, mundo.ana)["acepta_asistente"]
    assert escribir(cliente, mundo.t_mateo).status_code == 403

    consentir(cliente, mundo.t_ana)
    assert escribir(cliente, mundo.t_mateo, "Hola").status_code == 200
    assert 'name="texto"' in cliente.get(f"/p/{mundo.t_mateo}/asistente").text
    assert "Retirar mi autorización" not in cliente.get(f"/p/{mundo.t_mateo}/asistente").text
    consentir(cliente, mundo.t_mateo, "retirar")  # tampoco: sigue dependiendo de su responsable
    assert paciente(conn, mundo.ana)["acepta_asistente"]
    consentir(cliente, mundo.t_ana, "retirar")
    assert escribir(cliente, mundo.t_mateo).status_code == 403


def test_un_familiar_que_dejo_de_compartir_da_su_propio_consentimiento(mundo, app, cliente, conn):
    inyectar(app, Falso(responde("Hola.")))
    rosa = conn.execute(
        "insert into paciente(nombres, apellidos, documento, celular, fecha_nacimiento, responsable_id, parentesco, consentimiento_en) "
        "values ('Rosa','Pérez','5002',%s,'1980-01-01',%s,'otro',now()) returning id", (CEL, mundo.ana)).fetchone()["id"]
    conn.commit()
    t_rosa = links.make_token(rosa, 1)
    consentir(cliente, mundo.t_ana)
    assert escribir(cliente, t_rosa).status_code == 200  # por ahora, el de su responsable
    familia.dejar_de_compartir(conn, paciente(conn, rosa))
    conn.commit()
    # El que le anotó su responsable ya no sirve: hace falta el suyo.
    assert escribir(cliente, t_rosa).status_code == 403
    assert "Aceptar y continuar" in cliente.get(f"/p/{t_rosa}/asistente").text
    consentir(cliente, t_rosa)
    assert paciente(conn, rosa)["consentimiento_asistente_por"] is None
    assert escribir(cliente, t_rosa).status_code == 200
    consentir(cliente, mundo.t_ana, "retirar")  # el de Rosa es suyo: no se toca
    assert escribir(cliente, t_rosa).status_code == 200


# ------------------------------------------------------------------ el chat

def test_un_mensaje_de_ida_y_vuelta_con_htmx_y_sin_el(mundo, app, cliente, conn, capsys):
    consentir(cliente, mundo.t_ana)
    falso = Falso(responde("Tu cita es mañana a las 9."), responde("De nada, hasta pronto."), responde("Sigues con una cita."))
    inyectar(app, falso)
    r = escribir(cliente, mundo.t_ana, "¿Cuándo es mi cita? secreto-zeta")
    assert r.status_code == 200 and "Tu cita es mañana a las 9." in r.text and "secreto-zeta" in r.text
    conv = conversacion_de(r)
    assert conv.isdigit() and 'hx-swap-oob="true"' in r.text and "<html" not in r.text  # solo el fragmento
    conn.rollback()
    c = conn.execute("select * from asistente_conversacion").fetchall()
    assert len(c) == 1 and c[0]["perfil"] == "paciente" and c[0]["paciente_id"] == mundo.ana and c[0]["usuario_id"] is None

    r = escribir(cliente, mundo.t_ana, "Gracias", conversacion=conv)
    assert conversacion_de(r) == conv and "De nada, hasta pronto." in r.text
    assert "Tu cita es mañana" not in r.text  # el fragmento trae solo lo nuevo
    # Sin HTMX (formulario normal): la página completa con la conversación y el campo de la conversación relleno.
    r = escribir(cliente, mundo.t_ana, "¿Sigo con cita?", conversacion=conv, hx=False)
    assert r.status_code == 200 and "<html" in r.text and "Tu cita es mañana" in r.text and "Sigues con una cita." in r.text
    assert f'name="conversacion" value="{conv}"' in r.text
    # Al volver a abrirla se restaura.
    r = cliente.get(f"/p/{mundo.t_ana}/asistente?c={conv}")
    assert "De nada, hasta pronto." in r.text and "¿Cuándo es mi cita?" in r.text
    # El registro no lleva el texto de nadie.
    salida = capsys.readouterr().out
    assert "secreto-zeta" not in salida and "Tu cita es mañana" not in salida and '"evento": "asistente"' in salida


def test_los_botones_guiados_escriben_en_nombre_de_la_persona(mundo, app, cliente):
    consentir(cliente, mundo.t_ana)
    falso = Falso(responde("ok"), responde("ok"))
    inyectar(app, falso)
    pagina = cliente.get(f"/p/{mundo.t_ana}/asistente").text
    for valor in ap.GUIADOS:
        assert f'name="guiado" value="{valor}"' in pagina
    escribir(cliente, mundo.t_ana, texto="", guiado="cambiar")
    assert falso.peticiones[0]["messages"][-1]["content"][-1]["text"] == ap.GUIADOS["cambiar"]
    escribir(cliente, mundo.t_ana, texto="Mi texto", guiado="inventado")  # un botón desconocido no inventa nada
    assert falso.peticiones[1]["messages"][-1]["content"][-1]["text"] == "Mi texto"


def test_un_texto_vacio_o_de_mas_de_300_caracteres_no_llama_al_modelo(mundo, app, cliente):
    consentir(cliente, mundo.t_ana)
    falso = Falso(responde("no"))
    inyectar(app, falso)
    r = escribir(cliente, mundo.t_ana, "x" * 301, hx=False)
    assert r.status_code == 422 and "entre 1 y 300 caracteres" in r.text
    r = escribir(cliente, mundo.t_ana, "x" * 301)  # HTMX: un 200 con el aviso, porque HTMX no cambia nada con un 4xx
    assert r.status_code == 200 and "entre 1 y 300 caracteres" in r.text
    assert escribir(cliente, mundo.t_ana, "   ", hx=False).status_code == 422
    assert falso.peticiones == []


def test_el_texto_del_asistente_se_escapa_y_no_crea_enlaces(mundo, app, cliente):
    consentir(cliente, mundo.t_ana)
    malo = "<script>alert(1)</script> entra a http://malo.example/x <b>ya</b>"
    inyectar(app, Falso(responde(malo)))
    r = escribir(cliente, mundo.t_ana, "Hola")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text and "<script>alert" not in r.text and "<b>ya</b>" not in r.text
    assert "<a " not in r.text and "http://malo.example/x" in r.text  # la dirección es solo texto
    conv = conversacion_de(r)
    pagina = cliente.get(f"/p/{mundo.t_ana}/asistente?c={conv}").text  # y al restaurar la conversación
    assert "<script>alert" not in pagina and "&lt;script&gt;" in pagina and not re.search(r"<a [^>]*malo\.example", pagina)
    inyectar(app, Falso(responde(malo)))
    r = escribir(cliente, mundo.t_ana, "Hola", hx=False)  # y en la página completa
    assert "<script>alert" not in r.text and not re.search(r"<a [^>]*malo\.example", r.text)


def test_los_limites_y_los_fallos_responden_con_el_texto_fijo(mundo, app, cliente, conn):
    consentir(cliente, mundo.t_ana)
    config.set_(conn, "asistente_mensajes_dia_paciente", 2)
    conn.commit()
    falso = Falso(mensaje(pensar(), parada="refusal"), responde("Bien."))
    inyectar(app, falso)
    r = escribir(cliente, mundo.t_ana, "uno")  # un rechazo del modelo: el texto fijo y nada guardado
    assert FALLO in r.text and conversacion_de(r) == ""
    assert "Bien." in escribir(cliente, mundo.t_ana, "dos").text
    # El intento fallido también cuenta: con dos mensajes hoy ya se pasó el tope del hogar y no se vuelve a llamar al modelo.
    r = escribir(cliente, mundo.t_ana, "tres", hx=False)
    assert LIMITE in r.text and f'action="/p/{mundo.t_ana}/contacto"' in r.text and len(falso.peticiones) == 2
    # El tope es del hogar: el hijo comparte el de su responsable.
    assert LIMITE in escribir(cliente, mundo.t_mateo, "hola").text and len(falso.peticiones) == 2


def test_el_limite_por_ip_es_una_segunda_linea(mundo, app, cliente, monkeypatch):
    consentir(cliente, mundo.t_ana)
    monkeypatch.setattr(ap, "limite_asistente", ap.LimiteVentana(maximo=1, segundos=600))
    falso = Falso(responde("Bien."))
    inyectar(app, falso)
    assert "Bien." in escribir(cliente, mundo.t_ana, "uno").text
    r = escribir(cliente, mundo.t_ana, "dos", hx=False)
    assert r.status_code == 429 and LIMITE in r.text and len(falso.peticiones) == 1


def test_d2_ninguna_conexion_de_la_ruta_sigue_abierta_mientras_se_espera_al_modelo(mundo, app, cliente, monkeypatch):
    consentir(cliente, mundo.t_ana)
    abiertas = []
    real = db.psycopg.connect

    def rastrear(*a, **kw):
        c = real(*a, **kw)
        abiertas.append(c)
        return c

    monkeypatch.setattr(db.psycopg, "connect", rastrear)
    vistas = []
    inyectar(app, Falso(llama(usar("servicios")), responde("ok"), al_llamar=lambda: vistas.append([c.closed for c in abiertas])))
    del abiertas[:]
    r = escribir(cliente, mundo.t_ana, "Hola")
    assert r.status_code == 200 and "ok" in r.text
    assert len(vistas) == 2 and all(len(v) >= 2 for v in vistas)  # se abrieron la del enlace y la corta del bucle
    assert all(all(v) for v in vistas), "una conexión seguía abierta mientras se esperaba al modelo"
    assert all(x.closed for x in abiertas)


# ------------------------------------------------------------------ cada quien ve solo lo suyo

def test_una_conversacion_es_de_quien_la_escribio_no_del_hogar(mundo, app, cliente):
    for t in (mundo.t_ana,):
        consentir(cliente, t)
    inyectar(app, Falso(responde("Cosas de Ana."), responde("Cosas de Mateo."), responde("Otra de Ana.")))
    de_ana = conversacion_de(escribir(cliente, mundo.t_ana, "Soy Ana"))
    # Mateo, con el id de la conversación de su responsable, se comporta como ante una que no existe.
    r = escribir(cliente, mundo.t_mateo, "Soy Mateo", conversacion=de_ana)
    assert "ya no está disponible" in r.text and "Cosas de Ana." not in r.text and "Cosas de Mateo." not in r.text
    assert conversacion_de(r) == ""
    de_mateo = conversacion_de(escribir(cliente, mundo.t_mateo, "Soy Mateo"))
    assert de_mateo not in ("", de_ana)
    pagina = cliente.get(f"/p/{mundo.t_mateo}/asistente?c={de_ana}").text
    assert "Cosas de Ana." not in pagina and "Soy Ana" not in pagina
    pagina = cliente.get(f"/p/{mundo.t_ana}/asistente?c={de_mateo}").text
    assert "Cosas de Mateo." not in pagina and "Soy Mateo" not in pagina
    assert "Cosas de Ana." in cliente.get(f"/p/{mundo.t_ana}/asistente?c={de_ana}").text
    # Y por el formulario sin HTMX también: no se filtra nada ni se continúa la ajena.
    r = escribir(cliente, mundo.t_ana, "Sigo", conversacion=de_mateo, hx=False)
    assert "Cosas de Mateo." not in r.text


# ------------------------------------------------------------------ propuestas: nada se ejecuta hasta que la persona las envía

def un_espacio(conn, pro, servicio):
    return next(iter(agenda.available_slots(conn, pro, servicio).values()))[0]


def test_propuesta_agendar_apunta_al_formulario_existente_y_no_agenda_hasta_enviarlo(mundo, app, cliente, conn):
    consentir(cliente, mundo.t_ana)
    sid = svc(conn)
    inicio = un_espacio(conn, mundo.pro, sid)
    antes = cuenta(conn, "cita")
    inyectar(app, Falso(llama(usar("proponer_agendar", {"servicio_id": sid, "profesional_id": mundo.pro, "inicio": inicio.isoformat(),
                                                        "para": mundo.mateo})), responde("Lista para confirmar.")))
    r = escribir(cliente, mundo.t_ana, "Agéndale a Mateo")
    accion = f"/p/{mundo.t_ana}/agendar"
    assert f'action="{accion}"' in r.text and "Confirmar cita" in r.text and "Mateo" in r.text
    f = campos(r.text, accion)
    assert f == {"servicio": str(sid), "profesional": str(mundo.pro), "inicio": inicio.isoformat(), "para": str(mundo.mateo)}
    assert f"?servicio={sid}&amp;profesional={mundo.pro}&amp;para={mundo.mateo}&amp;desde=" in r.text  # sin JavaScript: la agenda
    assert cuenta(conn, "cita") == antes  # el asistente no agendó
    r = cliente.post(accion, data=f)  # la persona confirma: lo hace la ruta de siempre, con sus propias comprobaciones
    assert r.status_code == 200 and "La cita de Mateo quedó agendada" in r.headers["HX-Redirect"].replace("%20", " ").replace("%C3%B3", "ó")
    assert cuenta(conn, "cita") == antes + 1
    assert conn.execute("select paciente_id from cita order by id desc limit 1").fetchone()["paciente_id"] == mundo.mateo


def test_propuesta_agendar_con_cualquier_especialista_envia_profesional_cero(mundo, app, cliente, conn):
    consentir(cliente, mundo.t_ana)
    sid = svc(conn)
    inicio = un_espacio(conn, mundo.pro, sid)
    inyectar(app, Falso(llama(usar("proponer_agendar", {"servicio_id": sid, "inicio": inicio.isoformat()})), responde("Lista.")))
    r = escribir(cliente, mundo.t_ana, "Quiero una cita")
    assert campos(r.text, f"/p/{mundo.t_ana}/agendar")["profesional"] == "0"


def test_propuesta_cambiar_fecha_apunta_a_la_ruta_de_cambio_y_no_cambia_nada_hasta_enviarla(mundo, app, cliente, conn):
    consentir(cliente, mundo.t_ana)
    nueva = un_espacio(conn, mundo.pro, svc(conn))
    antes = conn.execute("select estado, rango from cita where id=%s", (mundo.cita_ana,)).fetchone()
    inyectar(app, Falso(llama(usar("proponer_cambiar_fecha", {"cita_id": mundo.cita_ana, "inicio": nueva.isoformat()})),
                        responde("Lista para confirmar.")))
    r = escribir(cliente, mundo.t_ana, "Quiero cambiarla")
    accion = f"/p/{mundo.t_ana}/cambiar/{mundo.cita_ana}"
    f = campos(r.text, accion)
    assert f == {"inicio": nueva.isoformat()} and "Confirmar el cambio" in r.text and f'href="{accion}"' in r.text
    conn.rollback()
    assert conn.execute("select estado, rango from cita where id=%s", (mundo.cita_ana,)).fetchone() == antes
    assert cuenta(conn, "cita") == 2
    assert cliente.post(accion, data=f).status_code == 200
    conn.rollback()
    # Cambiar la fecha cierra la cita como reprogramada y crea otra enlazada, a la hora propuesta.
    nueva_cita = conn.execute("select lower(rango) d from cita where cita_anterior_id=%s", (mundo.cita_ana,)).fetchone()
    assert nueva_cita["d"] == nueva


def test_propuesta_cancelar_abre_la_pantalla_que_pide_el_motivo_sin_cancelar(mundo, app, cliente, conn):
    consentir(cliente, mundo.t_ana)
    inyectar(app, Falso(llama(usar("proponer_cancelar", {"cita_id": mundo.cita_mateo})), responde("Lista para confirmar.")))
    r = escribir(cliente, mundo.t_ana, "Cancela la de Mateo")
    destino = f"/p/{mundo.t_ana}/cancelar/{mundo.cita_mateo}"
    assert f'<a role="button" href="{destino}">' in r.text and f'action="{destino}"' not in r.text  # un enlace, no un envío
    conn.rollback()
    assert conn.execute("select estado from cita where id=%s", (mundo.cita_mateo,)).fetchone()["estado"] not in ("cancelada",)
    pantalla = cliente.get(destino)
    assert pantalla.status_code == 200 and "Cuéntanos el motivo" in pantalla.text


def test_propuesta_contacto_crea_una_sola_solicitud_al_enviarla_y_esta_protegida(mundo, app, cliente, conn):
    consentir(cliente, mundo.t_ana)
    inyectar(app, Falso(llama(usar("pedir_contacto")), responde("Dejé lista la solicitud.")))
    r = escribir(cliente, mundo.t_ana, "Me duele mucho una muela")
    accion = f"/p/{mundo.t_ana}/contacto"
    assert f'action="{accion}"' in r.text and "Que me llamen" in r.text
    assert cuenta(conn, "solicitud_contacto") == 0  # el asistente no avisó a nadie
    r = cliente.post(accion, headers=HX)
    assert r.status_code == 200 and "Listo" in r.text
    fila = conn.execute("select * from solicitud_contacto").fetchall()
    conn.rollback()
    assert len(fila) == 1 and (fila[0]["documento"], fila[0]["celular"], fila[0]["nota"]) == ("7654321", CEL, ap.NOTA_CONTACTO)
    assert not fila[0]["gestionada"]
    # Una segunda no repite la que recepción aún no atiende.
    assert "Ya le avisamos" in cliente.post(accion, headers=HX).text
    assert cuenta(conn, "solicitud_contacto") == 1
    # Otra persona no se ve afectada.
    assert cliente.post(f"/p/{mundo.t_luis}/contacto", headers=HX).status_code == 200
    assert cuenta(conn, "solicitud_contacto") == 2
    # Atendida la primera, se puede pedir otra; pero no más de tres al día.
    for esperadas in (3, 4):
        conn.execute("update solicitud_contacto set gestionada=true where documento='7654321'")
        conn.commit()
        cliente.post(accion, headers=HX)
        assert cuenta(conn, "solicitud_contacto") == min(esperadas, 4)
    conn.execute("update solicitud_contacto set gestionada=true where documento='7654321'")
    conn.commit()
    assert "Ya le avisamos" in cliente.post(accion, headers=HX).text
    assert conn.execute("select count(*) n from solicitud_contacto where documento='7654321'").fetchone()["n"] == ap.CONTACTOS_POR_DIA
    conn.rollback()


def test_contacto_sin_htmx_redirige_a_mis_citas_con_el_aviso(mundo, cliente, conn):
    r = cliente.post(f"/p/{mundo.t_luis}/contacto")
    assert r.status_code == 303 and r.headers["location"].startswith(f"/p/{mundo.t_luis}?aviso=")
    assert cuenta(conn, "solicitud_contacto") == 1
    assert "Listo" in cliente.get(r.headers["location"]).text


def test_una_propuesta_mal_formada_no_pinta_ningun_boton():
    t = "tok"
    for malo in ({"tipo": "agendar", "parametros": {"servicio": "x"}, "resumen": "r"}, {"tipo": "borrar_todo", "parametros": {}},
                 {"tipo": "cancelar", "parametros": {"cita_id": "../../x"}}, {"tipo": "cambiar_fecha", "parametros": {"cita_id": 1, "inicio": "ayer"}}, {}):
        assert ap._tarjeta(malo, t) is None
    assert ap._tarjeta({"tipo": "contacto", "parametros": {}, "resumen": "r"}, t)["accion"] == "/p/tok/contacto"
    assert ap._tarjeta({"tipo": "confirmar", "parametros": {"cita_id": "x"}, "resumen": "r"}, t) is None
    cf = ap._tarjeta({"tipo": "confirmar", "parametros": {"cita_id": 7}, "resumen": "r"}, t)
    assert cf["accion"] == "/p/tok/confirmar/7" and cf["boton"] == "Confirmar asistencia"


def estado(conn, cita_id):
    conn.rollback()
    return conn.execute("select estado from cita where id=%s", (cita_id,)).fetchone()["estado"]


def test_confirmar_desde_el_enlace_confirma_la_cita_del_hogar_y_solo_una_vez(mundo, cliente, conn):
    assert "Confirmar asistencia" in cliente.get(f"/p/{mundo.t_ana}").text  # P1: la página lo ofrece, no solo el asistente
    r = cliente.post(f"/p/{mundo.t_ana}/confirmar/{mundo.cita_mateo}", headers=HX)
    assert r.status_code == 200 and "Mateo" in r.text and estado(conn, mundo.cita_mateo) == "confirmada"
    historial = conn.execute("select actor from historial_estado where cita_id=%s order by id desc limit 1",
                             (mundo.cita_mateo,)).fetchone()
    assert historial["actor"] == "paciente"
    assert "ya estaba confirmada" in cliente.post(f"/p/{mundo.t_ana}/confirmar/{mundo.cita_mateo}", headers=HX).text
    r = cliente.post(f"/p/{mundo.t_ana}/confirmar/{mundo.cita_ana}")
    assert r.status_code == 303 and r.headers["location"].startswith(f"/p/{mundo.t_ana}?aviso=")
    assert estado(conn, mundo.cita_ana) == "confirmada"


def test_confirmar_una_cita_de_otro_hogar_o_un_enlace_invalido_es_404(mundo, cliente, conn):
    assert cliente.post(f"/p/{mundo.t_luis}/confirmar/{mundo.cita_ana}").status_code == 404
    assert cliente.post(f"/p/{mundo.t_mateo}/confirmar/{mundo.cita_ana}").status_code == 404  # el hijo no toca lo de su madre
    assert cliente.post(f"/p/no-es-un-token/confirmar/{mundo.cita_ana}").status_code == 404
    assert estado(conn, mundo.cita_ana) != "confirmada"
