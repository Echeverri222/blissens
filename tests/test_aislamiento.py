"""Aislamiento entre negocios, entornos, migraciones y ciclo por turnos (PRD #4 §10). Siempre con el rol de aplicación."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from estudia import arranque, db, links, migrate, negocios, settings, tasks, usuarios
from estudia.api.operacion import limite_cambio_clave, limite_login
from estudia.web.app import crear_app

from .conftest import ADMIN, URL, at, make_patient, make_pro
from .test_api import API, CLAVE, nuevo_cliente


@pytest.fixture(autouse=True)
def _limpiar_limites():
    limite_login.reiniciar()
    limite_cambio_clave.reiniciar()
    yield
    limite_login.reiniciar()
    limite_cambio_clave.reiniciar()


def negocio_b(nombre="otra", zona="America/Bogota") -> int:
    a = db.connect_admin(ADMIN)
    nid = negocios.crear(a, nombre, "Otra Clínica", zona)
    a.commit()
    a.close()
    return nid


def tablas_de_negocio(conn) -> list[str]:
    return [r["table_name"] for r in conn.execute(
        "select table_name from information_schema.columns where table_schema='public' and column_name='negocio_id' "
        "and table_name not in ('sesion','acceso') order by 1")]


@pytest.fixture
def dos(conn):
    """Blissens (1) con datos y un negocio B con datos equivalentes."""
    pa = make_patient(conn, doc="111")
    make_pro(conn)
    conn.commit()
    nb = negocio_b()
    cb = db.connect(URL, negocio=nb)
    pb = make_patient(cb, doc="111")  # mismo documento que en A: no debe delatar nada
    make_pro(cb, "Dr. B")
    cb.commit()
    yield {"a": 1, "b": nb, "pa": pa, "pb": pb, "cb": cb}
    cb.close()


def test_inventario_todas_las_tablas_tienen_rls_forzado_y_el_rol_no_es_privilegiado(conn):
    a = db.connect_admin(ADMIN)
    sin = a.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='public' and c.relkind='r' and not (c.relrowsecurity and c.relforcerowsecurity)").fetchall()
    assert sin == [], f"tablas sin RLS forzado: {sin}"
    r = a.execute("select rolsuper, rolbypassrls from pg_roles where rolname='estudia_app'").fetchone()
    assert not r["rolsuper"] and not r["rolbypassrls"]
    assert not a.execute("select 1 from pg_tables where schemaname='public' and tableowner='estudia_app'").fetchone()
    assert conn.execute("select current_user u").fetchone()["u"] == "estudia_app"
    a.close()


def test_fuga_en_la_base_para_cada_tabla_de_negocio(dos):
    cb = dos["cb"]
    for t in tablas_de_negocio(cb):
        assert cb.execute(f"select count(*) n from {t} where negocio_id=%s", (dos["a"],)).fetchone()["n"] == 0, t
        if t == "auditoria_acceso":  # solo admite insertar y leer
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cb.execute("delete from auditoria_acceso")
            cb.rollback()
            continue
        assert cb.execute(f"delete from {t} where negocio_id=%s", (dos["a"],)).rowcount == 0, t
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # insertar indicando el negocio A
        cb.execute("insert into paciente(negocio_id, nombres) values (%s,'X')", (dos["a"],))
    cb.rollback()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # apuntar a un registro de A
        cb.execute("insert into mensaje(paciente_id, direccion, texto, momento) values (%s,'saliente','x', now())",
                   (dos["pa"],))
    cb.rollback()


def test_sin_negocio_activo_no_se_lee_ni_se_escribe(conn, dos):
    sin = db.connect(URL, negocio=None)
    for t in tablas_de_negocio(sin):
        assert sin.execute(f"select count(*) n from {t}").fetchone()["n"] == 0, t
    with pytest.raises(psycopg.Error):
        sin.execute("insert into paciente(nombres) values ('X')")
    sin.rollback()
    sin.close()


def test_la_unicidad_no_delata_al_otro_negocio(dos):
    assert dos["pa"] != dos["pb"]  # mismo documento en ambos negocios funcionó (la fixture lo hizo)


def test_http_un_recurso_de_otro_negocio_es_404_y_el_selector_exige_acceso(conn, dos):
    cb = dos["cb"]
    usuarios.crear(conn, "solo_a", "Solo A", CLAVE, "auxiliar")
    usuarios.crear(cb, "solo_b", "Solo B", CLAVE, "auxiliar")
    usuarios.crear(conn, "ambos", "Ambos", CLAVE, "auxiliar")
    conn.commit()
    usuarios.dar_acceso(cb, "ambos", "auxiliar")
    cb.commit()
    b = nuevo_cliente()
    assert b.post(f"{API}/sesion", json={"usuario": "solo_b", "clave": CLAVE}).status_code == 200
    assert b.get(f"{API}/pacientes/{dos['pa']}").status_code == 404
    assert b.get(f"{API}/pacientes/{dos['pb']}").status_code == 200
    assert b.post(f"{API}/sesion/negocio", json={"negocio_id": dos["a"]}).status_code == 404
    m = nuevo_cliente()
    r = m.post(f"{API}/sesion", json={"usuario": "ambos", "clave": CLAVE}).json()
    assert r["negocio"] is None and len(r["negocios"]) == 2
    assert m.get(f"{API}/pacientes/{dos['pa']}").status_code == 409  # negocio_requerido
    assert m.post(f"{API}/sesion/negocio", json={"negocio_id": dos["b"]}).status_code == 200
    assert m.get(f"{API}/pacientes/{dos['pa']}").status_code == 404
    assert m.post(f"{API}/sesion/negocio", json={"negocio_id": dos["a"]}).status_code == 200
    assert m.get(f"{API}/pacientes/{dos['pa']}").status_code == 200


def test_quitar_el_acceso_cierra_la_sesion_activa_y_la_clave_de_un_usuario_compartido_no_se_cambia(conn, dos):
    cb = dos["cb"]
    usuarios.crear(conn, "admin_a", "Admin A", CLAVE, "auxiliar", administrador=True)
    usuarios.crear(conn, "compartido", "Comp", CLAVE, "auxiliar")
    usuarios.crear(conn, "extra", "Extra", CLAVE, "auxiliar", administrador=True)
    conn.commit()
    usuarios.dar_acceso(cb, "compartido", "auxiliar")
    cb.commit()
    c = nuevo_cliente()
    c.post(f"{API}/sesion", json={"usuario": "compartido", "clave": CLAVE})
    c.post(f"{API}/sesion/negocio", json={"negocio_id": dos["a"]})
    with pytest.raises(usuarios.ClaveDeOtroNegocio):
        usuarios.restablecer_clave(conn, "compartido", "otra-clave-9", temporal=True)
    usuarios.desactivar(conn, "compartido")
    conn.commit()
    assert c.get(f"{API}/sesion").status_code == 401
    # no afecta al otro negocio
    d = nuevo_cliente()
    assert d.post(f"{API}/sesion", json={"usuario": "compartido", "clave": CLAVE}).status_code == 200
    usuarios.desactivar(conn, "extra")
    with pytest.raises(usuarios.UltimoAdministrador):
        usuarios.desactivar(conn, "admin_a")


def test_agendar_con_prefijo_trata_el_documento_de_otro_negocio_como_nuevo_y_enlaces_no_cruzan(conn, dos):
    conn.execute("update paciente set celular='+573001112233' where id=%s", (dos["pa"],))
    conn.commit()
    cli = TestClient(crear_app("local"), follow_redirects=False)
    r = cli.post("/n/otra/agendar/identificar", data={"documento": "999", "celular": "3001112233"})
    assert "primera vez" in r.text
    token_a = links.make_token(dos["pa"], dos["a"])
    assert cli.get(f"/p/{token_a}").status_code == 200
    assert cli.get("/n/inexistente/agendar").status_code == 404
    forjado = links.make_token(dos["pa"], dos["b"])  # paciente de A con negocio B: B no lo tiene
    assert cli.get(f"/p/{forjado}").status_code == 404
    assert cli.get("/p/basura").status_code == 404


def test_zona_horaria_del_negocio(conn):
    nid = negocio_b("tokio", "Asia/Tokyo")
    c = db.connect(URL, negocio=nid)
    from estudia import clock
    assert clock.tz(c).key == "Asia/Tokyo"
    assert clock.now(c).utcoffset().total_seconds() == 9 * 3600
    assert clock.tz(conn).key == "America/Bogota"


def test_ciclo_por_turnos_un_negocio_atrasado_no_retrasa_a_otro(conn, dos):
    cb = dos["cb"]
    for _ in range(3):
        tasks.schedule(conn, "inexistente_a", at(-1, "08:00"))
    conn.commit()
    tasks.schedule(cb, "inexistente_b", at(-1, "08:00"))
    cb.commit()
    r = tasks.cycle(max_tasks=1)
    assert set(r) == {1, dos["b"]}
    hechas_b = cb.execute("select count(*) n from tarea_programada where tipo='inexistente_b' and estado<>'pendiente' "
                          "or (tipo='inexistente_b' and intentos>0)").fetchone()["n"]
    assert hechas_b == 1


def test_entornos_rutas_presentes_y_ausentes(monkeypatch, conn):
    from estudia import settings
    monkeypatch.setattr(settings, "TICK_SECRETO", "")
    prod = TestClient(crear_app("produccion"))
    assert prod.get("/simulador").status_code == 404 and prod.post("/tick").status_code == 404
    assert prod.get("/salud").status_code == 200
    monkeypatch.setattr(settings, "TICK_SECRETO", "secreto-de-prueba-123")
    prod = TestClient(crear_app("produccion"))
    assert prod.post("/tick").status_code == 401
    assert prod.post("/tick", headers={"X-Tick-Secreto": "secreto-de-prueba-123"}).status_code == 200
    demo = TestClient(crear_app("demo"))
    assert demo.get("/simulador").status_code == 401 and demo.post("/tick").status_code == 401
    assert demo.post("/tick", headers={"X-Tick-Secreto": "secreto-de-prueba-123"}).status_code == 200
    assert TestClient(crear_app("local")).post("/tick").status_code == 200


def test_en_produccion_el_desfase_del_reloj_se_ignora(conn, monkeypatch):
    from estudia import clock, config, settings
    clock.freeze(None)
    config.set_(conn, "reloj_desfase_seg", 86400 * 30)
    antes = clock.now(conn)
    monkeypatch.setattr(settings, "ENTORNO", "produccion")
    assert (antes - clock.now(conn)).total_seconds() > 86400 * 29


def test_migraciones_subir_bajar_y_comparar_esquema():
    a = db.connect_admin(ADMIN.rsplit("/", 1)[0] + "/postgres")
    a.autocommit = True
    a.execute("drop database if exists estudia_mig")
    a.execute("create database estudia_mig")
    url = ADMIN.rsplit("/", 1)[0] + "/estudia_mig"
    try:
        migrate.run(url, hasta="002")

        def esquema():
            c = db.connect_admin(url)
            r = c.execute("select table_name, column_name, data_type, is_nullable from information_schema.columns "
                          "where table_schema='public' and table_name<>'migracion' order by 1,2").fetchall()
            c.close()
            return r
        base = esquema()
        migrate.run(url, hasta="006")
        assert migrate.verificar(url) == []
        migrate.bajar(url, 4)  # 006, 005, 004, 003
        assert esquema() == base
        assert migrate.run(url) and migrate.verificar(url) == []
        assert not migrate.run(url)  # al día
        with pytest.raises(migrate.SinReversa):
            migrate.bajar(url, 15)  # deshace de la 022 a la 007; la 007 contrae y es irreversible
        assert migrate.run(url) == ["008_canal_idempotencia.sql", "009_cerrar_api_de_datos.sql",
                                    "010_funciones_auxiliares_privadas.sql", "011_correo.sql", "012_familia.sql",
                                    "013_valor_servicio.sql", "014_resolucion_pendientes.sql", "015_asistente.sql",
                                    "016_segmentos.sql", "017_familia_fk_negocio.sql", "018_solicitud_web.sql",
                                    "019_asistente_visitante.sql", "020_prospecto.sql", "022_contacto_paciente.sql"]
        # una migración ya aplicada y modificada hace fallar
        c = db.connect_admin(url)
        c.execute("update migracion set huella='x' where nombre='003_negocio.sql'")
        c.commit()
        c.close()
        with pytest.raises(migrate.MigracionModificada):
            migrate.run(url)
    finally:
        a.execute("drop database if exists estudia_mig")
        a.close()


def test_nuevo_negocio_por_comando_agenda_en_su_prefijo(conn):
    a = db.connect_admin(ADMIN)
    negocios.crear(a, "demo-dos", "Demo Dos")
    a.commit()
    a.close()
    cli = TestClient(crear_app("local"), follow_redirects=False)
    r = cli.get("/n/demo-dos/agendar")
    assert r.status_code == 200 and "Demo Dos" in r.text
    assert nuevo_cliente().get("/agendar").text.count("Blissens") >= 1


def test_asistente_un_negocio_no_ve_ni_toca_las_conversaciones_de_otro_ni_las_cuelga(conn, dos):
    cb = dos["cb"]
    cid = conn.execute("insert into asistente_conversacion(perfil, paciente_id) values ('paciente', %s) returning id",
                       (dos["pa"],)).fetchone()["id"]
    conn.execute("insert into asistente_mensaje(conversacion_id, rol, contenido) values (%s,'user','[]'::jsonb)", (cid,))
    conn.commit()
    for t in ("asistente_conversacion", "asistente_mensaje"):
        assert cb.execute(f"select count(*) n from {t}").fetchone()["n"] == 0, t
        assert cb.execute(f"update {t} set negocio_id=negocio_id where negocio_id=%s", (dos["a"],)).rowcount == 0, t
        assert cb.execute(f"delete from {t} where negocio_id=%s", (dos["a"],)).rowcount == 0, t
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # indicando el negocio A
        cb.execute("insert into asistente_conversacion(negocio_id, perfil, paciente_id) values (%s,'paciente',%s)",
                   (dos["a"], dos["pb"]))
    cb.rollback()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # colgar un mensaje de la conversación de A
        cb.execute("insert into asistente_mensaje(conversacion_id, rol, contenido) values (%s,'user','[]'::jsonb)", (cid,))
    cb.rollback()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # una conversación de B sobre un paciente de A
        cb.execute("insert into asistente_conversacion(perfil, paciente_id) values ('paciente', %s)", (dos["pa"],))
    cb.rollback()
    assert conn.execute("select count(*) n from asistente_mensaje").fetchone()["n"] == 1


def test_fk_compuesta_familia_bloquea_cruce_entre_negocios(dos):
    cb = dos["cb"]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cb.execute(
            "insert into paciente(nombres, documento, celular, responsable_id) values ('Hijo', '222', '+573001112244', %s)",
            (dos["pa"],),
        )
    cb.rollback()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cb.execute(
            "insert into paciente(nombres, documento, celular, consentimiento_por) values ('Hijo', '223', '+573001112245', %s)",
            (dos["pa"],),
        )
    cb.rollback()


def test_arranque_produccion_rechaza_sslmode_debil_y_clave_demo(conn, monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "secreto-real-de-produccion")
    monkeypatch.setattr(settings, "BASE_URL", "https://app.ejemplo.com")
    for mala_url in (URL, f"{URL}?sslmode=disable", f"{URL}?sslmode=allow", f"{URL}?sslmode=prefer"):
        monkeypatch.setattr(settings, "DATABASE_URL", mala_url)
        assert any("sslmode" in p or "TLS" in p for p in arranque.problemas("produccion", conn=conn))
    monkeypatch.setattr(settings, "DATABASE_URL", f"{URL}?sslmode=require")
    assert arranque.problemas("produccion", conn=conn) == []
    usuarios.crear(conn, "demo_residual", "Demo Residual", usuarios.DEMO_CLAVE, "auxiliar")
    conn.commit()
    p_demo = arranque.problemas("produccion", conn=conn)
    assert any("demo_residual" in p for p in p_demo)
    usuarios.desactivar(conn, "demo_residual")
    conn.commit()
    assert arranque.problemas("produccion", conn=conn) == []
