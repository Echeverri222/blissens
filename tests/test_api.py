"""API /api/v1 por HTTP: sesión, roles, aislamiento del especialista, bloqueos, desenlace y contrato (PRD #2 §7)."""
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from estudia import agenda, bandejas, clock, indicators, usuarios
from estudia.api.esquema import ARCHIVO, esquema
from estudia.web.app import app

from .conftest import NOW, at, book, button, make_patient, make_pro, press, status, svc

CLAVE = "clave-de-prueba"
API = "/api/v1"


def nuevo_cliente():
    return TestClient(app, follow_redirects=False)


def entrar(usuario, clave=CLAVE):
    c = nuevo_cliente()
    r = c.post(f"{API}/sesion", json={"usuario": usuario, "clave": clave})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def mundo(conn):
    pro1, pro2 = make_pro(conn, "Dra. Uno"), make_pro(conn, "Dr. Dos")
    usuarios.crear(conn, "recepcion", "Recepción", CLAVE, "auxiliar")
    usuarios.crear(conn, "esp1", "Dra. Uno", CLAVE, "especialista", pro1)
    usuarios.crear(conn, "esp2", "Dr. Dos", CLAVE, "especialista", pro2)
    p1, p2 = make_patient(conn, "Ana", "Pérez"), make_patient(conn, "Luis", "Gómez")
    conn.commit()
    return SimpleNamespace(pro1=pro1, pro2=pro2, p1=p1, p2=p2, aux=entrar("recepcion"), esp1=entrar("esp1"),
                           esp2=entrar("esp2"))


def rango(dia, ini, fin):
    return {"inicio": at(dia, ini).isoformat(), "fin": at(dia, fin).isoformat(), "motivo": "Reunión"}


def motivo_id(conn):
    return conn.execute("select id from motivo_cancelacion order by orden limit 1").fetchone()["id"]


# ------------------------------------------------------------------ 1. Ninguna ruta queda abierta

def test_every_api_route_requires_a_session():
    anon = nuevo_cliente()
    n = 0
    for path, ops in esquema()["paths"].items():
        if not path.startswith(API):
            continue
        for method in ops:
            if (method, path) in (("post", f"{API}/sesion"), ("get", f"{API}/marca")):
                continue
            r = anon.request(method.upper(), path.replace("{", "").replace("}", "").replace("_id", "1").replace(
                "profesional1", "1"), json={} if method != "get" else None)
            assert r.status_code == 401, (method, path, r.status_code)
            assert r.json()["codigo"] == "no_autenticado"
            n += 1
    assert n >= 40


# ------------------------------------------------------------------ 2. Matriz de roles

SOLO_AUXILIAR = [
    ("post", "/citas", {"paciente_id": 1, "profesional_id": 1, "servicio_id": 1, "inicio": "2026-12-01T09:00:00-05:00"}),
    ("post", "/citas/1/confirmar", None), ("get", "/resumen-dia", None),
    ("post", "/citas/1/cancelar", {"motivo_id": 1}),
    ("post", "/citas/1/cambiar-fecha", {"inicio": "2026-12-01T09:00:00-05:00"}),
    ("get", "/espacios?profesional_id=1&servicio_id=1", None),
    ("get", "/pacientes?q=a", None), ("post", "/pacientes", {"nombres": "A", "documento": "1", "celular": "3001112233",
                                                              "consentimiento": True}),
    ("get", "/pacientes/1", None), ("put", "/pacientes/1/correo", {"correo": "ana@example.com", "acepta": True}),
    ("get", "/bandejas", None), ("get", "/bandejas/no-confirmadas", None),
    ("get", "/bandejas/seguimientos", None), ("get", "/bandejas/en-riesgo", None), ("get", "/bandejas/cupos-libres", None),
    ("get", "/bandejas/sin-desenlace", None), ("get", "/bandejas/sin-interpretar", None),
    ("get", "/bandejas/contactos", None), ("get", "/bandejas/dados-de-baja", None),
    ("post", "/seguimientos/1/gestion", {"resultado": "acepto"}), ("post", "/mensajes/1/gestionar", None),
    ("post", "/contactos/1/gestionar", None), ("get", "/indicadores/resumen", None),
    ("get", "/indicadores/tendencia", None), ("get", "/indicadores/por-profesional", None),
    ("get", "/indicadores/por-servicio", None), ("get", "/indicadores/motivos", None),
    ("get", "/indicadores/tiempo-entre-citas", None), ("post", "/indicadores/cierre", None), ("get", "/sistema", None),
]
AMBOS_ROLES = [
    ("get", "/sesion", None), ("get", "/profesionales", None), ("get", "/servicios", None),
    ("get", "/motivos-cancelacion", None), ("get", "/agenda?desde=2026-11-16", None),
    ("get", "/bloqueos?desde=2026-11-16", None),
]


def test_role_matrix(mundo):
    for method, path, body in SOLO_AUXILIAR:
        r = mundo.esp1.request(method.upper(), API + path, json=body)
        assert r.status_code == 403 and r.json()["codigo"] == "sin_permiso", (method, path, r.status_code)
        r = mundo.aux.request(method.upper(), API + path, json=body)
        assert r.status_code not in (401, 403), (method, path, r.status_code, r.text)
    for method, path, body in AMBOS_ROLES:
        for cli in (mundo.aux, mundo.esp1):
            assert cli.request(method.upper(), API + path, json=body).status_code == 200, (method, path)


def test_state_changing_requests_only_accept_json(mundo):
    r = mundo.aux.post(f"{API}/pacientes", data={"nombres": "A", "documento": "1", "celular": "3001112233",
                                                   "consentimiento": "true"})
    assert r.status_code == 422 and r.json()["codigo"] == "solo_json"


def test_errors_share_one_shape(mundo):
    for r in (mundo.aux.post(f"{API}/pacientes", json={"nombres": "A"}), mundo.aux.get(f"{API}/citas/99999"),
              mundo.aux.get(f"{API}/agenda?desde=2026-01-01&hasta=2026-12-31")):
        assert set(r.json()) >= {"codigo", "mensaje"} and r.status_code in (404, 422)


# ------------------------------------------------------------------ 3. Aislamiento del especialista

def test_specialist_only_sees_own_agenda_even_when_asking_for_another(mundo, conn):
    c1 = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    c2 = book(conn, mundo.p2, mundo.pro2, at(1, "10:00"))
    conn.execute("insert into bloqueo(profesional_id, rango) values (%s, tstzrange(%s,%s))",
                 (mundo.pro2, at(2, "08:00"), at(2, "09:00")))
    conn.commit()
    q = f"{API}/agenda?desde={at(0, '08:00').date()}&hasta={at(7, '08:00').date()}"
    r = mundo.esp1.get(q + f"&profesional_id={mundo.pro2}")
    assert r.status_code == 200
    d = r.json()
    assert d["profesional_id"] == mundo.pro1 and [c["id"] for c in d["citas"]] == [c1]
    assert d["bloqueos"] == [] and {f["profesional_id"] for f in d["franjas"]} == {mundo.pro1}
    assert d["citas"][0]["inicio"].endswith("-05:00") and d["citas"][0]["paciente"] == "Ana Pérez"
    # la auxiliar ve todo o filtra
    assert {c["id"] for c in mundo.aux.get(q).json()["citas"]} == {c1, c2}
    assert [c["id"] for c in mundo.aux.get(q + f"&profesional_id={mundo.pro2}").json()["citas"]] == [c2]


def test_specialist_gets_404_for_resources_of_another_professional(mundo, conn):
    c2 = book(conn, mundo.p2, mundo.pro2, at(1, "10:00"))
    conn.execute("insert into bloqueo(profesional_id, rango) values (%s, tstzrange(%s,%s)) returning id",
                 (mundo.pro2, at(2, "08:00"), at(2, "09:00")))
    bid = conn.execute("select id from bloqueo").fetchone()["id"]
    hid = conn.execute("select id from historial_estado where cita_id=%s", (c2,)).fetchone()["id"]
    conn.commit()
    e1 = mundo.esp1
    assert e1.get(f"{API}/citas/{c2}").status_code == 404
    assert e1.post(f"{API}/citas/{c2}/desenlace", json={"desenlace": "atendida"}).status_code == 404
    assert e1.get(f"{API}/profesionales/{mundo.pro2}/horario").status_code == 404
    assert e1.get(f"{API}/profesionales/{mundo.pro1}/horario").status_code == 200
    assert e1.delete(f"{API}/bloqueos/{bid}").status_code == 404
    assert e1.post(f"{API}/bloqueos", json={**rango(3, "10:00", "11:00"), "profesional_id": mundo.pro2}).status_code == 404
    assert e1.post(f"{API}/historial/{hid}/revertir").status_code == 404
    assert e1.get(f"{API}/bloqueos?desde={at(0, '08:00').date()}&hasta={at(7, '08:00').date()}").json() == []
    assert mundo.esp2.get(f"{API}/citas/{c2}").status_code == 200


def test_specialist_sees_minimum_patient_data(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    conn.commit()
    d = mundo.esp1.get(f"{API}/citas/{c}").json()
    assert set(d["paciente"]) == {"id", "nombre", "celular"} and d["paciente"]["nombre"] == "Ana Pérez"
    assert d["historial"][0]["estado_nuevo"] in ("programada", "confirmada")
    assert "documento" not in json.dumps(d)


# ------------------------------------------------------------------ 4. Sesión

def test_login_ok_and_same_message_for_unknown_user_and_wrong_password(mundo):
    r = nuevo_cliente().post(f"{API}/sesion", json={"usuario": "ESP1", "clave": CLAVE})  # sin distinguir mayúsculas
    assert r.status_code == 200
    s = r.json()
    assert s["rol"] == "especialista" and s["profesional_id"] == mundo.pro1 and s["profesional"] == "Dra. Uno"
    assert s["hora_sistema"].startswith("2026-11-16T08:00:00-05:00") and s["modo_demo"] is True
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    a = nuevo_cliente().post(f"{API}/sesion", json={"usuario": "esp1", "clave": "incorrecta1"})
    b = nuevo_cliente().post(f"{API}/sesion", json={"usuario": "no-existe", "clave": "incorrecta1"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_session_is_stored_as_fingerprint_not_value(mundo, conn):
    token = mundo.aux.cookies.get("estudia_sesion")
    huellas = [r["huella"] for r in conn.execute("select huella from sesion")]
    assert token and token not in huellas and all(len(h) == 64 for h in huellas)
    assert "scrypt" in conn.execute("select clave_hash from usuario where nombre_usuario='esp1'").fetchone()["clave_hash"]


def test_lockout_after_five_failures_and_unlock_over_time(mundo, conn, monkeypatch):
    t = [usuarios._ahora()]
    monkeypatch.setattr(usuarios, "_ahora", lambda: t[0])
    c = nuevo_cliente()
    for _ in range(4):
        assert c.post(f"{API}/sesion", json={"usuario": "esp1", "clave": "mala-clave"}).status_code == 401
    r = c.post(f"{API}/sesion", json={"usuario": "esp1", "clave": "mala-clave"})
    assert r.status_code == 429 and r.json()["codigo"] == "inicio_bloqueado"
    assert c.post(f"{API}/sesion", json={"usuario": "esp1", "clave": CLAVE}).status_code == 429  # ni con la buena
    t[0] += timedelta(minutes=16)
    assert c.post(f"{API}/sesion", json={"usuario": "esp1", "clave": CLAVE}).status_code == 200


def test_session_expires_renews_with_use_and_ignores_the_demo_clock(mundo, conn, monkeypatch):
    t = [usuarios._ahora()]
    monkeypatch.setattr(usuarios, "_ahora", lambda: t[0])
    c = entrar("recepcion")
    t[0] += timedelta(hours=11)
    assert c.get(f"{API}/sesion").status_code == 200           # y se renueva
    t[0] += timedelta(hours=11)
    assert c.get(f"{API}/sesion").status_code == 200
    clock.freeze(NOW + timedelta(days=30))                     # adelantar el reloj de demo no cierra sesiones
    assert c.get(f"{API}/sesion").status_code == 200
    t[0] += timedelta(hours=13)
    assert c.get(f"{API}/sesion").status_code == 401


def test_logout_deletes_the_session(mundo):
    token = mundo.aux.cookies.get("estudia_sesion")
    assert mundo.aux.delete(f"{API}/sesion").status_code == 200
    viejo = nuevo_cliente()
    viejo.cookies.set("estudia_sesion", token)
    assert viejo.get(f"{API}/sesion").status_code == 401


def test_changing_password_closes_other_sessions_only(mundo):
    otra = entrar("esp1")
    r = mundo.esp1.post(f"{API}/sesion/clave", json={"actual": CLAVE, "nueva": "otra-clave-9"})
    assert r.status_code == 200
    assert mundo.esp1.get(f"{API}/sesion").status_code == 200 and otra.get(f"{API}/sesion").status_code == 401
    assert mundo.esp1.post(f"{API}/sesion/clave", json={"actual": "mal-mal-mal", "nueva": "otra-clave-9"}).status_code == 401
    assert mundo.esp1.post(f"{API}/sesion/clave", json={"actual": "otra-clave-9", "nueva": "corta"}).status_code == 422
    assert nuevo_cliente().post(f"{API}/sesion", json={"usuario": "esp1", "clave": "otra-clave-9"}).status_code == 200


def test_deactivated_user_loses_access_immediately(mundo, conn):
    usuarios.desactivar(conn, "esp1")
    conn.commit()
    assert mundo.esp1.get(f"{API}/sesion").status_code == 401
    assert nuevo_cliente().post(f"{API}/sesion", json={"usuario": "esp1", "clave": CLAVE}).status_code == 401


def test_user_rules(conn):
    pro = make_pro(conn)
    with pytest.raises(usuarios.UsuarioInvalido):
        usuarios.crear(conn, "x", "X", CLAVE, "especialista")                 # especialista sin profesional
    with pytest.raises(usuarios.UsuarioInvalido):
        usuarios.crear(conn, "y", "Y", CLAVE, "auxiliar", pro)                # auxiliar con profesional
    with pytest.raises(usuarios.ClaveInvalida):
        usuarios.crear(conn, "z", "Z", "corta", "auxiliar")
    usuarios.crear(conn, "Ana", "Ana", CLAVE, "auxiliar")
    with pytest.raises(usuarios.UsuarioInvalido):
        usuarios.crear(conn, "ANA", "Otra", CLAVE, "auxiliar")                # único sin distinguir mayúsculas


def test_demo_users_are_created_with_fake_data(conn):
    from estudia import data
    n = data.seed(conn, patients=12)
    assert {u["usuario"] for u in n["usuarios"]} == {"auxiliar", "especialista1", "especialista2"}
    assert conn.execute("select count(*) n from acceso where rol='especialista' and profesional_id is not null").fetchone()["n"] == 2


# ------------------------------------------------------------------ 5. Bloqueos

def test_block_in_free_range_removes_the_slot_for_patients(mundo, conn):
    s = svc(conn)
    assert at(1, "14:00") in agenda.day_slots(conn, mundo.pro1, s, at(1, "14:00").date())
    conn.rollback()
    r = mundo.esp1.post(f"{API}/bloqueos", json=rango(1, "14:00", "15:00"))
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["profesional_id"] == mundo.pro1 and b["creado_por"] == "Dra. Uno" and b["motivo"] == "Reunión"
    assert at(1, "14:00") not in agenda.day_slots(conn, mundo.pro1, s, at(1, "14:00").date())
    assert at(1, "15:00") in agenda.day_slots(conn, mundo.pro1, s, at(1, "14:00").date())


def test_block_over_a_live_appointment_is_rejected_listing_the_conflicts(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "10:00"))
    conn.commit()
    r = mundo.esp1.post(f"{API}/bloqueos", json=rango(1, "09:45", "10:15"))
    assert r.status_code == 409 and r.json()["codigo"] == "bloqueo_con_citas"
    assert [x["id"] for x in r.json()["citas"]] == [c] and r.json()["citas"][0]["paciente"] == "Ana Pérez"
    assert status(conn, c) in ("programada", "confirmada")
    assert conn.execute("select count(*) n from bloqueo").fetchone()["n"] == 0


def test_block_validation(mundo):
    assert mundo.esp1.post(f"{API}/bloqueos", json=rango(1, "15:00", "14:00")).status_code == 422
    pasado = {"inicio": (NOW - timedelta(hours=3)).isoformat(), "fin": (NOW - timedelta(hours=2)).isoformat(), "motivo": ""}
    assert mundo.esp1.post(f"{API}/bloqueos", json=pasado).status_code == 422
    assert mundo.esp1.post(f"{API}/bloqueos", json=rango(1, "05:00", "06:00")).status_code == 201   # fuera del horario
    assert mundo.aux.post(f"{API}/bloqueos", json=rango(1, "14:00", "15:00")).status_code == 422    # falta profesional
    assert mundo.aux.post(f"{API}/bloqueos", json={**rango(1, "14:00", "15:00"), "profesional_id": mundo.pro2}).status_code == 201


def test_block_voids_overlapping_open_slots_and_pending_offers(mundo, conn):
    a = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    b = book(conn, mundo.p2, mundo.pro1, at(1, "11:00"))
    agenda.cancel(conn, a, "paciente", "enlace", reason_id=motivo_id(conn))
    cupo = conn.execute("select * from cupo_liberado").fetchone()
    assert cupo["estado"] == "en_oferta"
    boton = button(conn, mundo.p2, "oferta_adelanto")
    conn.commit()
    assert mundo.esp1.post(f"{API}/bloqueos", json=rango(1, "08:30", "09:30")).status_code == 201
    assert conn.execute("select estado from cupo_liberado").fetchone()["estado"] == "anulado"
    assert conn.execute("select estado from oferta_adelanto").fetchone()["estado"] == "anulada"
    press(conn, mundo.p2, boton)                                          # responde a la oferta anulada
    assert [m["plantilla"] for m in conn.execute("select plantilla from mensaje where paciente_id=%s and direccion='saliente' "
                                                 "order by id", (mundo.p2,))][-1] == "oferta_no_disponible"
    assert status(conn, b) in ("programada", "confirmada")


def test_deleting_a_block_gives_the_slots_back_and_past_blocks_stay(mundo, conn):
    s = svc(conn)
    bid = mundo.esp1.post(f"{API}/bloqueos", json=rango(1, "14:00", "15:00")).json()["id"]
    assert mundo.esp1.delete(f"{API}/bloqueos/{bid}").status_code == 200
    assert at(1, "14:00") in agenda.day_slots(conn, mundo.pro1, s, at(1, "14:00").date())
    conn.rollback()
    bid = mundo.esp1.post(f"{API}/bloqueos", json=rango(1, "14:00", "15:00")).json()["id"]
    clock.freeze(at(1, "16:00"))
    r = mundo.esp1.delete(f"{API}/bloqueos/{bid}")
    assert r.status_code == 409 and r.json()["codigo"] == "bloqueo_pasado"


def test_overlapping_blocks_do_not_subtract_shared_time_twice(conn):
    from estudia import horario
    pro = make_pro(conn)
    base = indicators._minutes_available(conn, pro, at(1, "08:00").date())
    horario.create_block(conn, pro, at(1, "08:00"), at(1, "09:00"), "a")
    horario.create_block(conn, pro, at(1, "08:30"), at(1, "09:30"), "b")
    assert indicators._minutes_available(conn, pro, at(1, "08:00").date()) == base - 90


def test_reverting_into_a_blocked_range_is_rejected(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    agenda.cancel(conn, c, "paciente", "enlace", reason_id=motivo_id(conn))
    h = conn.execute("select id from historial_estado where estado_nuevo='cancelada'").fetchone()["id"]
    conn.commit()
    assert mundo.esp1.post(f"{API}/bloqueos", json=rango(1, "08:30", "09:30")).status_code == 201
    r = mundo.aux.post(f"{API}/historial/{h}/revertir")
    assert r.status_code == 409 and r.json()["codigo"] == "no_reversible" and "bloqueado" in r.json()["mensaje"]
    assert status(conn, c) == "cancelada"


def test_a_freed_range_that_is_blocked_does_not_open_a_slot(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    conn.execute("update cita set estado='cancelada' where id=%s", (c,))
    conn.execute("insert into bloqueo(profesional_id, rango) values (%s, tstzrange(%s,%s))",
                 (mundo.pro1, at(1, "08:30"), at(1, "09:30")))
    from estudia import slots
    assert slots.register_slot(conn, mundo.pro1, agenda.rng(at(1, "09:00"), 30), c, "cancelacion") is None
    assert conn.execute("select count(*) n from cupo_liberado").fetchone()["n"] == 0


# ------------------------------------------------------------------ 6. Desenlace

def test_outcome_is_rejected_before_the_appointment_starts(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    conn.commit()
    for cli in (mundo.esp1, mundo.aux):
        r = cli.post(f"{API}/citas/{c}/desenlace", json={"desenlace": "atendida"})
        assert r.status_code == 409 and r.json()["codigo"] == "desenlace_anticipado"
    assert status(conn, c) in ("programada", "confirmada")


def test_outcome_records_actor_and_user_and_no_show_opens_follow_up(mundo, conn):
    c1 = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    c2 = book(conn, mundo.p2, mundo.pro1, at(1, "10:00"))
    conn.commit()
    clock.freeze(at(1, "10:30"))
    assert mundo.esp1.post(f"{API}/citas/{c1}/desenlace", json={"desenlace": "no_asistio"}).status_code == 200
    assert mundo.aux.post(f"{API}/citas/{c2}/desenlace", json={"desenlace": "atendida"}).status_code == 200
    assert conn.execute("select tipo from caso_seguimiento where cita_id=%s", (c1,)).fetchone()["tipo"] == "inasistencia"
    h = {x["cita_id"]: x for x in conn.execute("select h.*, u.nombre_usuario from historial_estado h left join usuario u "
                                               "on u.id=h.usuario_id where h.estado_nuevo in ('no_asistio','atendida')")}
    assert (h[c1]["actor"], h[c1]["nombre_usuario"]) == ("especialista", "esp1")
    assert (h[c2]["actor"], h[c2]["nombre_usuario"]) == ("auxiliar", "recepcion")
    d = mundo.esp1.get(f"{API}/citas/{c1}").json()
    assert d["historial"][-1]["usuario"] == "Dra. Uno" and d["historial"][-1]["actor"] == "especialista"
    assert mundo.esp1.post(f"{API}/citas/{c1}/desenlace", json={"desenlace": "atendida"}).status_code == 409


def test_specialist_reverts_only_own_outcome(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    conn.commit()
    clock.freeze(at(1, "09:30"))
    mundo.esp1.post(f"{API}/citas/{c}/desenlace", json={"desenlace": "no_asistio"})
    detalle = mundo.esp1.get(f"{API}/citas/{c}").json()["historial"]
    nacimiento, desenlace = detalle[0]["id"], detalle[-1]["id"]
    assert mundo.esp1.post(f"{API}/historial/{nacimiento}/revertir").status_code == 403
    r = mundo.esp1.post(f"{API}/historial/{desenlace}/revertir")
    assert r.status_code == 200
    assert status(conn, c) in ("programada", "confirmada")
    assert conn.execute("select estado from caso_seguimiento where cita_id=%s", (c,)).fetchone()["estado"] == "anulado"
    ultimo = mundo.esp1.get(f"{API}/citas/{c}").json()["historial"]
    assert ultimo[-1]["actor"] == "especialista" and ultimo[-1]["revierte_id"] == desenlace
    assert next(h for h in ultimo if h["id"] == desenlace)["revertido"] is True


# ------------------------------------------------------------------ 7. Cancelar y cambiar fecha por la auxiliar

def test_auxiliar_cancel_has_the_same_effects_as_the_patient(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(2, "09:00"))
    conn.commit()
    r = mundo.aux.post(f"{API}/citas/{c}/cancelar", json={"motivo_id": motivo_id(conn), "texto": "Llamó"})
    assert r.status_code == 200, r.text
    assert status(conn, c) == "cancelada"
    assert conn.execute("select count(*) n from cancelacion where cita_id=%s", (c,)).fetchone()["n"] == 1
    assert conn.execute("select count(*) n from cupo_liberado where cita_origen_id=%s", (c,)).fetchone()["n"] == 1
    assert conn.execute("select tipo from caso_seguimiento where cita_id=%s", (c,)).fetchone()["tipo"] == "cancelacion"
    h = conn.execute("select h.actor, u.nombre_usuario from historial_estado h join usuario u on u.id=h.usuario_id "
                     "where h.cita_id=%s and h.estado_nuevo='cancelada'", (c,)).fetchone()
    assert (h["actor"], h["nombre_usuario"]) == ("auxiliar", "recepcion")
    assert mundo.aux.post(f"{API}/citas/{c}/cancelar", json={"motivo_id": motivo_id(conn)}).status_code == 409


def test_auxiliar_reschedule_creates_a_linked_appointment(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(2, "09:00"))
    conn.commit()
    r = mundo.aux.post(f"{API}/citas/{c}/cambiar-fecha", json={"inicio": at(3, "10:00").isoformat()})
    assert r.status_code == 200, r.text
    nueva = r.json()["cita_id"]
    assert status(conn, c) == "reprogramada"
    assert conn.execute("select cita_anterior_id, origen from cita where id=%s", (nueva,)).fetchone() == {
        "cita_anterior_id": c, "origen": "auxiliar"}
    assert conn.execute("select actor from historial_estado where cita_id=%s and estado_nuevo='reprogramada'",
                        (c,)).fetchone()["actor"] == "auxiliar"
    book(conn, mundo.p2, mundo.pro1, at(3, "11:00"))
    conn.commit()
    ocupado = mundo.aux.post(f"{API}/citas/{nueva}/cambiar-fecha", json={"inicio": at(3, "11:00").isoformat()})
    assert ocupado.status_code == 409 and ocupado.json()["codigo"] == "espacio_ocupado"
    conn.rollback()
    assert status(conn, nueva) in ("programada", "confirmada")


def test_auxiliar_books_and_slot_conflicts_return_409(mundo, conn):
    body = {"paciente_id": mundo.p1, "profesional_id": mundo.pro1, "servicio_id": svc(conn), "inicio": at(2, "09:00").isoformat()}
    r = mundo.aux.post(f"{API}/citas", json=body)
    assert r.status_code == 201
    assert mundo.aux.post(f"{API}/citas", json={**body, "paciente_id": mundo.p2}).json()["codigo"] == "espacio_ocupado"
    dias = mundo.aux.get(f"{API}/espacios?profesional_id={mundo.pro1}&servicio_id={svc(conn)}&dias=3").json()["dias"]
    assert dias and all(h.endswith("-05:00") for h in dias[0]["horas"])


def test_patients_search_create_and_full_record(mundo, conn):
    nuevo = {"nombres": "Rosa", "apellidos": "Mejía", "documento": "555.666", "celular": "300 111 2233", "consentimiento": True}
    r = mundo.aux.post(f"{API}/pacientes", json=nuevo)
    assert r.status_code == 201
    pid = r.json()["paciente_id"]
    assert mundo.aux.post(f"{API}/pacientes", json=nuevo).json()["codigo"] == "documento_existente"
    assert mundo.aux.post(f"{API}/pacientes", json={**nuevo, "documento": "9", "consentimiento": False}).status_code == 422
    assert mundo.aux.post(f"{API}/pacientes", json={**nuevo, "documento": "9", "celular": "123"}).status_code == 422
    assert [p["id"] for p in mundo.aux.get(f"{API}/pacientes", params={"q": "Mejía"}).json()] == [pid]
    row = conn.execute("select * from paciente where id=%s", (pid,)).fetchone()
    assert row["documento"] == "555666" and row["celular"] == "+573001112233" and row["consentimiento_en"] is not None
    c = book(conn, pid, mundo.pro1, at(2, "09:00"))
    conn.commit()
    f = mundo.aux.get(f"{API}/pacientes/{pid}").json()
    assert f["paciente"]["nombres"] == "Rosa" and [x["id"] for x in f["citas"]] == [c]
    assert f["historial"][0]["cita_id"] == c and f["mensajes"]
    assert mundo.aux.get(f"{API}/pacientes/99999").status_code == 404


# ------------------------------------------------------------------ 8. Paridad con las funciones de dominio

def test_trays_and_actions_match_the_domain_functions(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    conn.execute("update cita set estado='no_confirmada' where id=%s", (c,))
    conn.execute("insert into mensaje(paciente_id, direccion, texto, gestionado, momento) values (%s,'entrante','hola',false,%s)",
                 (mundo.p2, NOW))
    conn.execute("insert into solicitud_contacto(documento, celular, nota, momento) values ('1','+573000000000','n',%s)", (NOW,))
    conn.commit()
    cnt = mundo.aux.get(f"{API}/bandejas").json()
    assert cnt == {"no_confirmadas": len(bandejas.no_confirmadas(conn)), "seguimientos": len(bandejas.seguimientos(conn)),
                   "en_riesgo": len(bandejas.en_riesgo(conn)), "cupos_libres": len(bandejas.cupos_libres(conn)),
                   "sin_desenlace": len(bandejas.sin_desenlace(conn)), "sin_interpretar": 1, "contactos": 1,
                   "dados_de_baja": len(bandejas.dados_de_baja(conn))}
    assert [r["cita_id"] for r in mundo.aux.get(f"{API}/bandejas/no-confirmadas").json()] == [c]
    mid = mundo.aux.get(f"{API}/bandejas/sin-interpretar").json()[0]["id"]
    sid = mundo.aux.get(f"{API}/bandejas/contactos").json()[0]["id"]
    assert mundo.aux.post(f"{API}/mensajes/{mid}/gestionar").status_code == 200
    assert mundo.aux.post(f"{API}/contactos/{sid}/gestionar").status_code == 200
    assert mundo.aux.get(f"{API}/bandejas/sin-interpretar").json() == [] and mundo.aux.get(f"{API}/bandejas/contactos").json() == []
    assert mundo.aux.post("/api/v1/mensajes/9999/gestionar").status_code == 404


def test_follow_up_action_and_indicators_match_the_domain(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    clock.freeze(at(1, "10:00"))
    agenda.mark_outcome(conn, c, "no_asistio")
    caso = conn.execute("select id from caso_seguimiento").fetchone()["id"]
    conn.commit()
    assert mundo.aux.get(f"{API}/bandejas/seguimientos").json()[0]["id"] == caso
    assert mundo.aux.post(f"{API}/seguimientos/{caso}/gestion", json={"resultado": "rechazo", "detalle": "No quiere"}).status_code == 200
    assert conn.execute("select estado from caso_seguimiento").fetchone()["estado"] == "rechazado"
    assert mundo.aux.post(f"{API}/seguimientos/{caso}/gestion", json={"resultado": "acepto"}).status_code == 409

    cierre = mundo.aux.post(f"{API}/indicadores/cierre")
    assert cierre.status_code == 200 and cierre.json()["dias"] >= 1
    assert mundo.aux.post(f"{API}/indicadores/cierre").json() == cierre.json()                # idempotente
    f = {"desde": at(-5, "08:00").date(), "hasta": at(5, "08:00").date(), "profesional_id": None, "servicio_id": None}
    q = f"?desde={f['desde']}&hasta={f['hasta']}"
    conn.rollback()
    r = mundo.aux.get(f"{API}/indicadores/resumen{q}").json()
    assert r == json.loads(json.dumps(indicators.summary(conn, f))) and r["no_asistio"] == 1
    assert mundo.aux.get(f"{API}/indicadores/tendencia{q}").json()[0]["no_asistio"] == 1
    sem = mundo.aux.get(f"{API}/indicadores/tendencia{q}&agrupar=semana").json()
    assert sum(p["no_asistio"] for p in sem) == 1
    assert mundo.aux.get(f"{API}/indicadores/por-profesional{q}").json()[0]["nombre"] == "Dra. Uno"
    assert mundo.aux.get(f"{API}/indicadores/por-servicio{q}").status_code == 200
    assert mundo.aux.get(f"{API}/indicadores/motivos{q}").status_code == 200
    assert set(mundo.aux.get(f"{API}/indicadores/tiempo-entre-citas{q}").json()) == {"por_servicio", "por_paciente_dias"}
    s = mundo.aux.get(f"{API}/sistema").json()
    assert s["ultimo_cierre"] == clock.now(conn).date().isoformat() and s["configuracion"]["paso_min"] == 30
    assert s["tareas_pendientes"] >= 0 and s["tareas_fallidas"] == []


def test_agenda_range_limits_and_imported_appointments_without_time(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    conn.execute("insert into cita(paciente_id, profesional_id, servicio_id, dia, rango, estado, origen) "
                 "values (%s,%s,%s,%s,null,'atendida','importacion')", (mundo.p1, mundo.pro1, svc(conn), at(1, "09:00").date()))
    conn.commit()
    d0, d1 = at(0, "08:00").date(), at(41, "08:00").date()
    ok = mundo.aux.get(f"{API}/agenda?desde={d0}&hasta={d1}")
    assert ok.status_code == 200 and len(ok.json()["citas_sin_hora"]) == 1 and [x["id"] for x in ok.json()["citas"]] == [c]
    assert mundo.aux.get(f"{API}/agenda?desde={d0}&hasta={at(42, '08:00').date()}").status_code == 422
    assert mundo.aux.get(f"{API}/agenda?desde={d1}&hasta={d0}").status_code == 422
    assert mundo.aux.get(f"{API}/agenda?desde={d0}").json()["hasta"] == str(d0)
    assert mundo.aux.get(f"{API}/agenda?desde={d0}&profesional_id=99999").status_code == 404


# ------------------------------------------------------------------ 9. Contrato

def test_openapi_file_matches_the_api():
    assert ARCHIVO.exists(), "Falta docs/openapi.json: ejecuta `make api-esquema`"
    assert json.loads(ARCHIVO.read_text()) == esquema(), "La API cambió: ejecuta `make api-esquema`"


def test_every_operation_declares_a_typed_response_and_phi_free_examples():
    for path, ops in esquema()["paths"].items():
        if path.startswith(API):
            for method, op in ops.items():
                ok = [c for c in op["responses"] if c.startswith("2")]
                assert ok and "content" in op["responses"][ok[0]], (method, path)
    assert "documento" not in json.dumps(esquema()["components"]["schemas"]["PacienteMinimo"])


# ------------------------------------------------------------------ 10. Recorrido de aceptación (§3.4)

def test_acceptance_walkthrough(conn):
    pro1, pro2 = make_pro(conn, "Dra. Uno"), make_pro(conn, "Dr. Dos")
    usuarios.crear(conn, "auxiliar", "Auxiliar", CLAVE, "auxiliar")
    usuarios.crear(conn, "especialista1", "Dra. Uno", CLAVE, "especialista", pro1)
    ana, luis = make_patient(conn, "Ana", "Pérez"), make_patient(conn, "Luis", "Gómez")
    mia = book(conn, ana, pro1, at(1, "09:00"))
    ajena = book(conn, luis, pro2, at(1, "09:00"))
    conflicto = book(conn, luis, pro1, at(2, "10:00"))
    conn.commit()
    anon = nuevo_cliente()
    # 1. sin sesión
    assert anon.get(f"{API}/agenda?desde=2026-11-16").status_code == 401
    # 2. iniciar sesión
    esp = nuevo_cliente()
    s = esp.post(f"{API}/sesion", json={"usuario": "especialista1", "clave": CLAVE}).json()
    assert (s["rol"], s["profesional_id"]) == ("especialista", pro1) and s["hora_sistema"] and s["nombre"] == "Dra. Uno"
    assert esp.get(f"{API}/sesion").json()["usuario"] == "especialista1"
    cookie = esp.cookies.get("estudia_sesion")
    # 3. agenda de la semana: solo lo suyo aunque pida otro profesional
    a = esp.get(f"{API}/agenda?desde={at(0, '08:00').date()}&hasta={at(6, '08:00').date()}&profesional_id={pro2}").json()
    assert {c["id"] for c in a["citas"]} == {mia, conflicto} and a["franjas"] and a["profesional_id"] == pro1
    # 4. detalle propio / ajeno
    assert esp.get(f"{API}/citas/{mia}").status_code == 200 and esp.get(f"{API}/citas/{ajena}").status_code == 404
    # 5. bloqueo en rango libre: el espacio deja de estar disponible
    assert esp.post(f"{API}/bloqueos", json=rango(3, "14:00", "15:00")).status_code == 201
    assert at(3, "14:00") not in agenda.day_slots(conn, pro1, svc(conn), at(3, "14:00").date())
    conn.rollback()
    # 6. bloqueo sobre cita viva: 409 con la lista
    r = esp.post(f"{API}/bloqueos", json=rango(2, "10:00", "11:00"))
    assert r.status_code == 409 and [c["id"] for c in r.json()["citas"]] == [conflicto]
    # 7. adelantar el reloj y registrar no asistió
    clock.freeze(at(1, "09:30"))
    assert esp.post(f"{API}/citas/{mia}/desenlace", json={"desenlace": "no_asistio"}).status_code == 200
    assert conn.execute("select count(*) n from caso_seguimiento where cita_id=%s and estado='abierto'", (mia,)).fetchone()["n"] == 1
    assert esp.get(f"{API}/citas/{mia}").json()["historial"][-1]["actor"] == "especialista"
    # 8. operación de auxiliar con rol de especialista
    assert esp.get(f"{API}/bandejas").status_code == 403
    # 9. auxiliar: cancela la cita en conflicto, repite el bloqueo y consulta
    aux = entrar("auxiliar")
    motivos = aux.get(f"{API}/motivos-cancelacion").json()
    assert aux.post(f"{API}/citas/{conflicto}/cancelar", json={"motivo_id": motivos[0]["id"]}).status_code == 200
    assert aux.post(f"{API}/bloqueos", json={**rango(2, "10:00", "11:00"), "profesional_id": pro1}).status_code == 201
    assert aux.get(f"{API}/bandejas").status_code == 200
    assert aux.get(f"{API}/pacientes/{ana}").status_code == 200
    assert aux.get(f"{API}/indicadores/resumen").status_code == 200
    # 10. cerrar sesión: la cookie anterior deja de servir
    assert esp.delete(f"{API}/sesion").status_code == 200
    viejo = nuevo_cliente()
    viejo.cookies.set("estudia_sesion", cookie)
    assert viejo.get(f"{API}/sesion").status_code == 401
