"""Agendar para toda la familia desde un solo enlace (docs/prd-familia.md)."""
import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from fastapi.testclient import TestClient

from estudia import clock, familia, links, privacidad, tasks
from estudia.web.app import app

from .conftest import at, book, make_patient, make_pro, outbox, status, svc

CEL = "+573001112233"


@pytest.fixture
def client(conn):
    conn.commit()
    return TestClient(app, follow_redirects=False)


def agregar(client, token, doc="5001", nombres="Mateo", nacimiento="2018-03-04", parentesco="hijo", consentimiento="1"):
    data = {"documento": doc, "nombres": nombres, "apellidos": "Prueba", "nacimiento": nacimiento, "parentesco": parentesco}
    if consentimiento:
        data["consentimiento"] = consentimiento
    return client.post(f"/p/{token}/familia/agregar", data=data)


def responsable(conn):
    pid = make_patient(conn, "Carlos", "Prueba", doc="4001", celular=CEL)
    conn.commit()
    return pid, links.make_token(pid, conn=conn)


def test_agregar_un_menor_hereda_celular_y_registra_el_consentimiento_del_representante(client, conn):
    pid, token = responsable(conn)
    r = agregar(client, token)
    assert r.status_code == 303 and "Agregamos a Mateo" in unquote(r.headers["location"])
    conn.rollback()
    m = conn.execute("select * from paciente where documento='5001'").fetchone()
    assert m["celular"] == CEL and m["responsable_id"] == pid and m["parentesco"] == "hijo"
    assert m["consentimiento_por"] == pid and m["consentimiento_en"] is not None and m["consentimiento_version"]
    assert str(m["fecha_nacimiento"]) == "2018-03-04"
    pagina = client.get(f"/p/{token}").text
    assert "Mi familia" in pagina and "Mateo" in pagina and "Menor de edad" in pagina


@pytest.mark.parametrize("cambio, mensaje", [
    ({"consentimiento": ""}, "autorización"),
    ({"nacimiento": ""}, "fecha de nacimiento"),
    ({"nacimiento": "2999-01-01"}, "Revisa la fecha"),
    ({"parentesco": "vecino"}, "parentesco"),
    ({"doc": "4001"}, "su propio documento"),
])
def test_datos_invalidos_no_crean_a_nadie(client, conn, cambio, mensaje):
    _, token = responsable(conn)
    r = agregar(client, token, **cambio)
    assert r.status_code == 422 and mensaje in r.text
    conn.rollback()
    assert conn.execute("select count(*) n from paciente").fetchone()["n"] == 1


def test_vista_del_hogar_y_agendar_para_un_familiar(client, conn):
    pro = make_pro(conn)
    pid, token = responsable(conn)
    agregar(client, token)
    extrano = make_patient(conn, "Extraño", doc="9999", celular="+573009999999")
    ajena = book(conn, extrano, pro, at(2, "15:00"))
    conn.commit()
    hijo = conn.execute("select id from paciente where documento='5001'").fetchone()["id"]

    pagina = client.get(f"/p/{token}/agendar").text
    assert "¿Para quién es la cita?" in pagina and "Carlos (usted)" in pagina

    r = client.post(f"/p/{token}/agendar", data={"servicio": svc(conn), "profesional": pro, "para": hijo,
                                                  "inicio": at(3, "10:00").isoformat()})
    assert r.status_code == 200 and "La cita de Mateo quedó agendada" in unquote(r.headers["HX-Redirect"])
    conn.rollback()
    cita = conn.execute("select * from cita where paciente_id=%s", (hijo,)).fetchone()
    assert cita is not None
    # El aviso del hogar espera unos minutos por si agendan a alguien más, y le llega al responsable con el nombre.
    assert not outbox(conn, hijo) and not outbox(conn, pid)
    clock.freeze(clock.now(conn) + timedelta(minutes=6))
    tasks.cycle(conn)
    assert "• Mateo:" in outbox(conn, pid, "cita_agendada_hogar")[0]["texto"]

    book(conn, pid, pro, at(4, "09:00"))
    conn.commit()
    pagina = client.get(f"/p/{token}").text
    assert "Próximas citas de su familia" in pagina and "Mateo" in pagina and "Usted" in pagina
    assert f"/cancelar/{ajena}" not in pagina

    # Fuera del hogar: 404 y no se agenda nada
    r = client.post(f"/p/{token}/agendar", data={"servicio": svc(conn), "profesional": pro, "para": extrano,
                                                  "inicio": at(3, "11:00").isoformat()})
    assert r.status_code == 404
    assert client.get(f"/p/{token}/agendar?para={extrano}").status_code == 404
    conn.rollback()
    assert conn.execute("select count(*) n from cita where paciente_id=%s", (extrano,)).fetchone()["n"] == 1


def test_cambiar_y_cancelar_la_cita_de_un_familiar_y_no_la_de_otros(client, conn):
    pro = make_pro(conn)
    _, token = responsable(conn)
    agregar(client, token)
    hijo = conn.execute("select id from paciente where documento='5001'").fetchone()["id"]
    extrano = make_patient(conn, "Extraño", doc="9999", celular="+573009999999")
    cita = book(conn, hijo, pro, at(3, "10:00"))
    ajena = book(conn, extrano, pro, at(3, "15:00"))
    conn.commit()

    assert "Cita de <strong>Mateo</strong>" in client.get(f"/p/{token}/cambiar/{cita}").text
    r = client.post(f"/p/{token}/cambiar/{cita}", data={"inicio": at(4, "11:00").isoformat()})
    assert r.status_code == 200 and "la cita de Mateo" in unquote(r.headers["HX-Redirect"])
    conn.rollback()
    assert status(conn, cita) == "reprogramada"
    nueva = conn.execute("select id from cita where cita_anterior_id=%s", (cita,)).fetchone()["id"]

    assert "Cancelar la cita de Mateo" in client.get(f"/p/{token}/cancelar/{nueva}").text
    motivo = conn.execute("select id from motivo_cancelacion order by orden limit 1").fetchone()["id"]
    r = client.post(f"/p/{token}/cancelar/{nueva}", data={"motivo": motivo})
    assert r.status_code == 200 and "Cita de <strong>Mateo</strong>" in r.text and f'name="para" value="{hijo}"' in r.text
    conn.rollback()
    assert status(conn, nueva) == "cancelada"

    assert client.get(f"/p/{token}/cambiar/{ajena}").status_code == 404
    assert client.get(f"/p/{token}/cancelar/{ajena}").status_code == 404
    assert client.post(f"/p/{token}/cancelar/{ajena}", data={"motivo": motivo}).status_code == 404
    assert client.post(f"/p/{token}/cambiar/{ajena}", data={"inicio": at(4, "15:00").isoformat()}).status_code == 404
    conn.rollback()
    assert status(conn, ajena) != "cancelada"


def test_enlazar_a_un_paciente_existente_con_el_mismo_celular(client, conn):
    pid, token = responsable(conn)
    pareja = make_patient(conn, "Laura", doc="4002", celular=CEL)
    conn.commit()
    r = agregar(client, token, doc="4002", nombres="Laura", nacimiento="1990-01-01", parentesco="pareja")
    assert r.status_code == 303
    conn.rollback()
    p = conn.execute("select * from paciente where id=%s", (pareja,)).fetchone()
    assert p["responsable_id"] == pid and p["parentesco"] == "pareja" and p["consentimiento_por"] is None
    r = agregar(client, token, doc="4002", nombres="Laura", nacimiento="1990-01-01", parentesco="pareja")
    assert "ya estaba en su familia" in unquote(r.headers["location"])


def test_con_otro_celular_no_se_revela_nada_y_queda_solicitud(client, conn):
    _, token = responsable(conn)
    otra = make_patient(conn, "Ajena", doc="4003", celular="+573005550000")
    conn.commit()
    r = agregar(client, token, doc="4003", nombres="Ajena", nacimiento="1990-01-01", parentesco="otro")
    assert r.status_code == 200 and "se pondrá en contacto" in r.text and "Ajena" not in r.text
    conn.rollback()
    assert conn.execute("select responsable_id from paciente where id=%s", (otra,)).fetchone()["responsable_id"] is None
    assert conn.execute("select count(*) n from solicitud_contacto where documento='4003'").fetchone()["n"] == 1


def test_un_familiar_no_agrega_y_un_adulto_puede_dejar_de_compartir_pero_un_menor_no(client, conn):
    pid, token = responsable(conn)
    agregar(client, token)
    agregar(client, token, doc="4002", nombres="Laura", nacimiento="1990-01-01", parentesco="pareja")
    conn.rollback()
    hijo = conn.execute("select id from paciente where documento='5001'").fetchone()["id"]
    pareja = conn.execute("select id from paciente where documento='4002'").fetchone()["id"]
    t_hijo, t_pareja = links.make_token(hijo, conn=conn), links.make_token(pareja, conn=conn)

    assert "Su familia la gestiona Carlos" in client.get(f"/p/{t_pareja}/familia/agregar").text
    r = agregar(client, t_pareja, doc="5002", nombres="Sofía")
    assert r.status_code == 422 and "Su familia la gestiona Carlos" in r.text

    pagina = client.get(f"/p/{t_hijo}").text
    assert "Carlos también ve y gestiona sus citas" in pagina and "Dejar de compartir" not in pagina
    assert "Las citas de un menor" in unquote(client.post(f"/p/{t_hijo}/dejar-de-compartir").headers["location"])

    assert "Dejar de compartir" in client.get(f"/p/{t_pareja}").text
    client.post(f"/p/{t_pareja}/dejar-de-compartir")
    conn.rollback()
    assert conn.execute("select responsable_id from paciente where id=%s", (pareja,)).fetchone()["responsable_id"] is None
    assert conn.execute("select responsable_id from paciente where id=%s", (hijo,)).fetchone()["responsable_id"] == pid


def test_agendar_justo_despues_preselecciona_el_primer_espacio_libre(client, conn):
    pro = make_pro(conn)
    pid, token = responsable(conn)
    agregar(client, token)
    conn.rollback()
    hijo = conn.execute("select id from paciente where documento='5001'").fetchone()["id"]
    cita = book(conn, pid, pro, at(3, "10:00"))
    conn.commit()
    pagina = client.get(f"/p/{token}?cita={cita}").text
    assert "Agendar a Mateo justo después" in pagina
    href = re.search(r'href="([^"]*desde=[^"]*)"', pagina).group(1).replace("&amp;", "&")
    assert parse_qs(urlparse(href).query)["para"] == [str(hijo)]
    fin = conn.execute("select upper(rango) f from cita where id=%s", (cita,)).fetchone()["f"]
    r = client.get(href)
    marcado = re.search(r'value="([^"]+)" required checked', r.text).group(1)
    assert datetime.fromisoformat(marcado) >= fin
    assert datetime.fromisoformat(marcado) - fin < timedelta(hours=1)
    assert f'name="para" value="{hijo}"' in r.text


def test_ficha_del_panel_y_anonimizar(conn):
    pid = make_patient(conn, "Carlos", doc="4001", celular=CEL)
    resp = {"celular": CEL, "documento": "4001", "id": pid, "responsable_id": None}
    hijo, _ = familia.agregar(conn, resp, "5001", "Mateo", "Prueba", "2018-03-04", "hijo", True)
    adulto, _ = familia.agregar(conn, resp, "5003", "Abuela", "Prueba", (at(0, "00:00") - timedelta(days=365 * 70)).date().isoformat(),
                                "padre", True)
    r = familia.resumen(conn, pid)
    assert r["responsable"] is None and [f["id"] for f in r["familiares"]] == [hijo, adulto]
    assert r["familiares"][0]["menor"] and not r["familiares"][1]["menor"]
    r = familia.resumen(conn, hijo)
    assert r["responsable"]["id"] == pid and r["responsable"]["parentesco"] == "hijo" and r["menor"]
    privacidad.anonimizar_paciente(conn, pid)
    assert familia.familiares(conn, pid) == []
    assert familia.resumen(conn, hijo)["responsable"] is None


def test_limite_de_familiares(conn):
    pid = make_patient(conn, "Carlos", doc="4001", celular=CEL)
    resp = {"celular": CEL, "documento": "4001", "id": pid, "responsable_id": None}
    for i in range(familia.MAXIMO):
        familia.agregar(conn, resp, str(6000 + i), "Hijo", "", "2015-01-01", "hijo", True)
    with pytest.raises(familia.DatosInvalidos):
        familia.agregar(conn, resp, "7000", "Uno más", "", "2015-01-01", "hijo", True)


def test_la_entrada_publica_orienta_a_quien_agenda_para_su_familia(client):
    assert "Regístrese usted primero y agréguelos desde" in client.get("/agendar").text


@pytest.fixture(autouse=True)
def _sin_limite_identificacion():
    from estudia.web.app import reiniciar_limites_identificacion
    reiniciar_limites_identificacion()
    yield
    reiniciar_limites_identificacion()


def test_nombre_hostil_del_responsable_no_inyecta_js_en_la_confirmacion(client, conn):
    pid = make_patient(conn, "O'Connor');alert(1)//", "Prueba", doc="4101", celular=CEL)
    conn.commit()
    agregar(client, links.make_token(pid, conn=conn), doc="4102", nombres="Laura", nacimiento="1990-01-01",
            parentesco="pareja")
    conn.rollback()
    pareja = conn.execute("select id from paciente where documento='4102'").fetchone()["id"]
    html = client.get(f"/p/{links.make_token(pareja, conn=conn)}").text
    assert "onsubmit=" not in html and "<script>" not in html
    assert "data-confirmar=" in html and "O&#39;Connor" in html and "O'Connor');" not in html


def test_solicitud_de_familia_a_documento_ajeno_no_se_duplica(client, conn):
    _, token = responsable(conn)
    make_patient(conn, "Otro", "Prueba", doc="7001", celular="+573009998877")
    conn.commit()
    for _ in range(3):
        assert agregar(client, token, doc="7001", nombres="Otro", nacimiento="1990-01-01", parentesco="otro").status_code == 200
    conn.rollback()
    assert conn.execute("select count(*) n from solicitud_contacto where documento='7001'").fetchone()["n"] == 1
