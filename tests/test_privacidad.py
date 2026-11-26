"""Ganchos de privacidad: registro de accesos, retención apagada por defecto, exportar y anonimizar un paciente."""
import json
from datetime import timedelta

from fastapi.testclient import TestClient

from estudia import clock, config, data, db, negocios, privacidad, usuarios
from estudia.web.app import app

from .conftest import ADMIN, NOW, at, book, make_patient, make_pro


def _entrar():
    c = TestClient(app)
    assert c.post("/api/v1/sesion", json={"usuario": "auxiliar", "clave": usuarios.DEMO_CLAVE}).status_code == 200
    return c


def test_consultas_de_pacientes_dejan_registro_sin_el_texto_buscado(conn):
    data.seed(conn)
    conn.commit()
    c = _entrar()
    pid = conn.execute("select id from paciente order by id limit 1").fetchone()["id"]
    cid = conn.execute("select id from cita order by id limit 1").fetchone()["id"]
    assert c.get("/api/v1/pacientes?q=zzz-secreto").status_code == 200
    assert c.get(f"/api/v1/pacientes/{pid}").status_code == 200
    assert c.get(f"/api/v1/citas/{cid}").status_code == 200
    assert c.get("/api/v1/agenda?desde=2026-11-16&hasta=2026-11-17").status_code == 200  # no se registra
    filas = conn.execute("select accion, paciente_id, cita_id, peticion from auditoria_acceso order by id").fetchall()
    assert [f["accion"] for f in filas] == ["buscar_paciente", "ver_ficha", "ver_cita"]
    assert filas[1]["paciente_id"] == pid and filas[2]["cita_id"] == cid
    assert all("zzz-secreto" not in (f["peticion"] or "") for f in filas)
    assert conn.execute("select count(*) n from auditoria_acceso").fetchone()["n"] == 3


def test_la_retencion_no_borra_nada_por_defecto_y_si_se_configura_borra(conn):
    pro, pa = make_pro(conn), make_patient(conn)
    book(conn, pa, pro, at(3, "10:00"))
    conn.commit()
    antes = conn.execute("select count(*) n from mensaje").fetchone()["n"]
    assert antes > 0
    clock.freeze(NOW + timedelta(days=400))
    assert privacidad.depurar(conn) == {}
    assert conn.execute("select count(*) n from mensaje").fetchone()["n"] == antes
    config.set_(conn, "retencion_mensajes_dias", 90)
    assert privacidad.depurar(conn)["mensajes"] == antes
    assert conn.execute("select count(*) n from cita").fetchone()["n"] == 1  # las citas no se tocan


def test_exportar_y_anonimizar_conserva_los_hechos_de_la_cita(conn):
    pro, pa = make_pro(conn), make_patient(conn, "Ana", "Pérez", doc="123456")
    book(conn, pa, pro, at(3, "10:00"))
    conn.commit()
    ex = privacidad.exportar_paciente(conn, pa)
    assert ex["paciente"]["nombres"] == "Ana" and len(ex["citas"]) == 1 and ex["mensajes"]
    json.dumps(ex)
    privacidad.anonimizar_paciente(conn, pa)
    p = conn.execute("select * from paciente where id=%s", (pa,)).fetchone()
    assert p["nombres"] == privacidad.ANONIMO and p["documento"] is None and p["celular"] is None
    assert not conn.execute("select 1 from mensaje where paciente_id=%s and texto<>'[eliminado]'", (pa,)).fetchone()
    assert conn.execute("select count(*) n from cita where paciente_id=%s", (pa,)).fetchone()["n"] == 1


def test_exportar_un_negocio_solo_saca_sus_filas(conn, tmp_path):
    make_patient(conn, "Ana")
    conn.commit()
    a = db.connect_admin(ADMIN)
    otro = negocios.crear(a, "otro", "Otro")
    db.fijar(a, otro)
    a.execute("insert into paciente(nombres) values ('Ajeno')")
    a.commit()
    negocios.exportar(a, otro, str(tmp_path / "o.json"))
    a.close()
    d = json.loads((tmp_path / "o.json").read_text())
    assert [p["nombres"] for p in d["paciente"]] == ["Ajeno"]


def test_el_registro_estructurado_no_lleva_datos_personales(conn, capsys):
    data.seed(conn)
    conn.commit()
    c = _entrar()
    pid = conn.execute("select id from paciente order by id limit 1").fetchone()["id"]
    c.get("/api/v1/pacientes?q=Zzz")
    c.get(f"/api/v1/pacientes/{pid}")
    lineas = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    ficha = next(x for x in lineas if x["ruta"].endswith("/pacientes/{paciente_id}"))
    assert ficha["negocio"] == 1 and ficha["usuario"] and ficha["estado"] == 200 and ficha["ms"] >= 0
    texto = json.dumps(lineas)
    assert "Zzz" not in texto and f"pacientes/{pid}\"" not in texto


def _conversacion(conn, pa, hace_dias=0):
    ultima = clock.now(conn) - timedelta(days=hace_dias)
    cid = conn.execute("insert into asistente_conversacion(perfil, paciente_id, creada_en, ultima_en) values ('paciente',%s,%s,%s) "
                       "returning id", (pa, ultima, ultima)).fetchone()["id"]
    conn.execute("insert into asistente_mensaje(conversacion_id, rol, contenido, creado_en) values (%s,'user',%s,%s)",
                 (cid, json.dumps([{"type": "text", "text": "hola"}]), ultima))
    return cid


def test_asistente_exportar_incluye_las_conversaciones_y_anonimizar_las_borra_y_limpia_el_consentimiento(conn):
    pa = make_patient(conn, "Ana", "Pérez", doc="123456")
    otra = make_patient(conn, "Luis", "Gómez", doc="654321")
    conn.execute("update paciente set acepta_asistente=true, consentimiento_asistente_en=now(), consentimiento_asistente_por=%s "
                 "where id=%s", (pa, pa))
    _conversacion(conn, pa)
    _conversacion(conn, otra)
    conn.commit()
    ex = privacidad.exportar_paciente(conn, pa)
    assert len(ex["asistente"]) == 1 and "hola" in json.dumps(ex["asistente"], ensure_ascii=False)
    json.dumps(ex, default=str)
    privacidad.anonimizar_paciente(conn, pa)
    p = conn.execute("select * from paciente where id=%s", (pa,)).fetchone()
    assert p["acepta_asistente"] is False and p["consentimiento_asistente_en"] is None and p["consentimiento_asistente_por"] is None
    assert conn.execute("select count(*) n from asistente_conversacion where paciente_id=%s", (pa,)).fetchone()["n"] == 0
    assert conn.execute("select count(*) n from asistente_conversacion where paciente_id=%s", (otra,)).fetchone()["n"] == 1
    assert conn.execute("select count(*) n from asistente_mensaje").fetchone()["n"] == 1  # los mensajes se fueron en cascada


def test_asistente_la_depuracion_borra_por_retencion_asistente_dias_y_solo_informa_si_borro(conn):
    pa = make_patient(conn)
    vieja, reciente = _conversacion(conn, pa, 40), _conversacion(conn, pa, 10)
    conn.commit()
    assert privacidad.depurar(conn) == {"asistente": 1}  # 30 días por defecto
    ids = [r["id"] for r in conn.execute("select id from asistente_conversacion")]
    assert ids == [reciente] and vieja not in ids
    assert conn.execute("select count(*) n from asistente_mensaje").fetchone()["n"] == 1
    assert privacidad.depurar(conn) == {}
    config.set_(conn, "retencion_asistente_dias", 5)
    assert privacidad.depurar(conn) == {"asistente": 1}
    assert conn.execute("select count(*) n from asistente_conversacion").fetchone()["n"] == 0
