"""Indicadores fase 2 por la API (docs/prd-indicadores-fase2.md): valor de servicios, metas y quién resuelve los pendientes."""
from estudia import clock, usuarios

from .conftest import at, book, svc
from .test_api import API, CLAVE, entrar, mundo  # noqa: F401  (fixture)


def admin(conn):
    usuarios.crear(conn, "jefa", "Jefa", CLAVE, "auxiliar", administrador=True)
    conn.commit()
    return entrar("jefa")


# ------------------------------------------------------------------ R1: valor de los servicios

def test_service_value_is_admin_only_and_shows_in_catalogue(mundo, conn):
    sid = svc(conn)
    assert mundo.aux.put(f"{API}/admin/servicios/{sid}", json={"valor": 80000}).status_code == 403  # recepción sin administrar
    assert mundo.esp1.put(f"{API}/admin/servicios/{sid}", json={"valor": 80000}).status_code == 403
    jefa = admin(conn)
    r = jefa.put(f"{API}/admin/servicios/{sid}", json={"valor": 80000})
    assert r.status_code == 200 and r.json()["valor"] == 80000
    assert {s["id"]: s["valor"] for s in mundo.aux.get(f"{API}/servicios").json()}[sid] == 80000
    assert jefa.put(f"{API}/admin/servicios/{sid}", json={"valor": None}).json()["valor"] is None
    assert jefa.put(f"{API}/admin/servicios/{sid}", json={"valor": -1}).status_code == 422
    assert jefa.put(f"{API}/admin/servicios/99999", json={"valor": 1}).status_code == 404


# ------------------------------------------------------------------ R3: metas

def test_targets_are_validated_and_returned_in_the_summary(mundo, conn):
    jefa = admin(conn)
    assert mundo.aux.put(f"{API}/admin/metas", json={}).status_code == 403
    for malo in ({"inasistencia": {"max": 1.5}}, {"inasistencia": {"min": 0.1}}, {"asistencia": {"max": 0.9}},
                 {"dinero_perdido": {"max": -5}}, {"dinero_perdido": {"max": 1.5}}, {"otra": {"max": 1}}):
        assert jefa.put(f"{API}/admin/metas", json=malo).status_code == 422, malo
    metas = {"inasistencia": {"max": 0.15}, "asistencia": {"min": 0.8}, "dinero_perdido": {"max": 2000000}}
    assert jefa.put(f"{API}/admin/metas", json=metas).json() == metas
    assert jefa.get(f"{API}/admin/metas").json() == metas and mundo.aux.get(f"{API}/admin/metas").status_code == 403
    hoy = clock.now(conn).date()
    r = mundo.aux.get(f"{API}/indicadores/resumen?desde={hoy}&hasta={hoy}&comparar=true").json()
    assert r["metas"] == metas and r["valor_perdido"] == 0 and r["anterior"]["citas_sin_valor"] == 0
    assert jefa.put(f"{API}/admin/metas", json={}).json() == {}                       # vaciar quita las metas
    assert mundo.aux.get(f"{API}/indicadores/resumen?desde={hoy}&hasta={hoy}").json()["metas"] == {}


# ------------------------------------------------------------------ R4: quién resuelve

def test_panel_actions_record_who_and_when(mundo, conn):
    uid = conn.execute("select usuario_id from acceso a join usuario u on u.id=a.usuario_id where u.nombre_usuario='recepcion'"
                       ).fetchone()["usuario_id"]
    c = book(conn, mundo.p1, mundo.pro1, at(1, "09:00"))
    mid = conn.execute("insert into mensaje(paciente_id, direccion, texto, gestionado, momento) "
                       "values (%s,'entrante','hola',false,%s) returning id", (mundo.p1, at(0, "08:00"))).fetchone()["id"]
    conn.commit()
    assert mundo.aux.post(f"{API}/citas/{c}/confirmar", json={}).status_code == 200
    clock.freeze(at(1, "10:00"))
    assert mundo.aux.post(f"{API}/citas/{c}/desenlace", json={"desenlace": "no_asistio"}).status_code == 200
    quien = conn.execute("select estado_nuevo, usuario_id from historial_estado where cita_id=%s and estado_anterior is not null "
                         "order by id", (c,)).fetchall()
    assert [(h["estado_nuevo"], h["usuario_id"]) for h in quien] == [("confirmada", uid), ("no_asistio", uid)]

    assert mundo.aux.post(f"{API}/mensajes/{mid}/gestionar", json={}).status_code == 200
    m = conn.execute("select gestionado_en, gestionado_por from mensaje where id=%s", (mid,)).fetchone()
    assert m["gestionado_por"] == uid and m["gestionado_en"] == clock.now(conn)

    caso = conn.execute("select id from caso_seguimiento").fetchone()["id"]
    assert mundo.aux.post(f"{API}/seguimientos/{caso}/gestion", json={"resultado": "sin_respuesta"}).status_code == 200
    assert conn.execute("select cerrado_por from caso_seguimiento").fetchone()["cerrado_por"] is None  # no cierra el caso
    assert mundo.aux.post(f"{API}/seguimientos/{caso}/gestion", json={"resultado": "rechazo"}).status_code == 200
    assert conn.execute("select cerrado_por from caso_seguimiento").fetchone()["cerrado_por"] == uid

    hoy = clock.now(conn).date()
    p = mundo.aux.get(f"{API}/indicadores/pendientes?desde={hoy}&hasta={hoy}").json()
    assert p["mensajes"]["resueltos"] == 1 and p["seguimientos"]["resueltos"] == 1 and p["cierre_citas"]["resueltos"] == 1
    assert {x["usuario"] for x in p["por_usuario"]} == {"Recepción"}
    r = mundo.aux.get(f"{API}/indicadores/reagendamiento?desde={hoy}&hasta={hoy}").json()
    assert set(r["buckets"]) == {"mismo_dia", "1_3", "4_14", "15_60", "no_reagendo"} and r["total"] == 0


# ------------------------------------------------------------------ R10: título del profesional

def test_titulo_del_profesional_solo_lo_cambia_quien_administra(mundo, conn):
    pid = mundo.aux.get(f"{API}/profesionales").json()[0]["id"]
    assert mundo.aux.put(f"{API}/admin/profesionales/{pid}", json={"titulo": "Dra."}).status_code == 403
    jefa = admin(conn)
    r = jefa.put(f"{API}/admin/profesionales/{pid}", json={"titulo": " Dra. "})
    assert r.status_code == 200 and r.json()["titulo"] == "Dra."
    assert {p["id"]: p["titulo"] for p in mundo.aux.get(f"{API}/profesionales").json()}[pid] == "Dra."
    assert jefa.put(f"{API}/admin/profesionales/{pid}", json={"titulo": ""}).json()["titulo"] == ""
    assert jefa.put(f"{API}/admin/profesionales/{pid}", json={"titulo": "x" * 21}).status_code == 422
    assert jefa.put(f"{API}/admin/profesionales/99999", json={"titulo": "Dr."}).status_code == 404


# ------------------------------------------------------------------ R11: motivos de cancelación activos

def test_motivos_por_defecto_y_admin_los_elige_y_ordena(mundo, conn):
    etiquetas = lambda r: [m["etiqueta"] for m in r.json()]  # noqa: E731
    assert etiquetas(mundo.aux.get(f"{API}/motivos-cancelacion")) == ["Salud", "Trabajo o estudio", "Viaje", "Motivo económico", "Otro"]
    assert mundo.aux.get(f"{API}/admin/motivos-cancelacion").status_code == 403
    jefa = admin(conn)
    todos = jefa.get(f"{API}/admin/motivos-cancelacion").json()
    assert len(todos) == 8 and [m["activo"] for m in todos] == [True] * 5 + [False] * 3  # los inactivos no se borran
    ids = {m["etiqueta"]: m["id"] for m in todos}
    nuevo = [ids["Viaje"], ids["Salud"], ids["Transporte"]]
    r = jefa.put(f"{API}/admin/motivos-cancelacion", json={"activos": nuevo})
    assert r.status_code == 200
    assert etiquetas(mundo.aux.get(f"{API}/motivos-cancelacion")) == ["Viaje", "Salud", "Transporte", "Otro"]  # "Otro" siempre al final y activo
    assert jefa.put(f"{API}/admin/motivos-cancelacion", json={"activos": [i for e, i in ids.items() if e != "Otro"][:6]}).status_code == 422  # 6 sin contar "Otro"
    assert jefa.put(f"{API}/admin/motivos-cancelacion", json={"activos": [99999]}).status_code == 404
    assert etiquetas(mundo.aux.get(f"{API}/motivos-cancelacion"))[-1] == "Otro"


def test_el_motivo_inactivo_sigue_valido_para_el_historico(mundo, conn):
    inactivo = conn.execute("select id from motivo_cancelacion where etiqueta='Transporte'").fetchone()["id"]
    assert inactivo not in [m["id"] for m in mundo.aux.get(f"{API}/motivos-cancelacion").json()]
    from estudia import catalog
    assert inactivo not in [m["id"] for m in catalog.motivos_activos(conn)]
    assert conn.execute("select count(*) as n from motivo_cancelacion").fetchone()["n"] == 8
