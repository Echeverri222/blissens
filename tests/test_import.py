from datetime import date

import openpyxl
import pytest

from estudia import data, indicators, settings


def build(tmp_path):
    e = openpyxl.Workbook()
    ws = e.active
    ws.append(["Nombre Sucursal", "# Paciente", "Nombre Paciente", "Apellidos Paciente", "# Tratamiento", "Especialidad",
               "Tratamiento o Diagnóstico", "Nombre Profesional Tratan", "Apellidos Profesional Tra", "# Cita",
               "Fecha Cita", "Estado actual cita", "Anulado", "Atendido", "No asiste"])
    rows = [
        ("S", "1.0", "Ana", "Prueba Uno", "10.0", "RO", "Diagnóstico", "Doc", "Uno", "100.0", "2026-08-03", "Atendido", "No", "Sí", "No"),
        ("S", "1.0", "Ana", "Prueba Uno", "10.0", "RO", "Diagnóstico", "Doc", "Uno", "101.0", "2026-08-10", "Cambio de fecha", "No", "No", "No"),
        ("S", "2.0", "Beto", "Prueba Dos", "11.0", "RO", "Tratamiento", "Doc", "Uno", "102.0", "2026-08-03", "Anulado por pcte. via Whatsapp", "Sí", "No", "No"),
        ("S", "2.0", "Beto", "Prueba Dos", "11.0", "RO", "Tratamiento", "Doc", "Uno", "103.0", "2026-08-04", "No asiste", "No", "No", "Sí"),
        ("S", "3.0", "Cami", "Prueba Tres", "12.0", "RO", "Tratamiento", "Doc", "Uno", "104.0", "2026-08-05", "Confirmado whatsapp", "No", "No", "No"),
        ("S", "3.0", "Cami", "Prueba Tres", "12.0", "RO", "Tratamiento", "Doc", "Uno", "105.0", "2026-08-05", "Notif. fallida", "No", "No", "No"),
    ]
    for r in rows:
        ws.append(r)
    e.save(tmp_path / "Agenda citas y estados .xlsx")
    a = openpyxl.Workbook()
    wa = a.active
    wa.append(["# Cita", "Estado Cita", "Fecha Cita", "Hora Inicio Cita", "Hora Fin Cita", "Comentario Cita", "# Paciente",
               "#Número de identificación", "Fecha de nac.", "E-Mail", "Teléfono", "Celular", "Observaciones clínicas"])
    arows = [
        ("100.0", "Atendido", "2026-08-03", "09:00:00", "09:30:00", "Revision limpieza", "1.0", "9000001", "1901-01-01", "a@ejemplo.com", None, "3001112233", "alergia: X"),
        ("101.0", "Cambio de fecha", "2026-08-10", "09:00:00", "09:30:00", None, "1.0", "9000001", "1901-01-01", None, None, "3001112233", None),
        ("102.0", "Anulado", "2026-08-03", "10:00:00", "10:30:00", "Resina", "2.0", "9000002", "1990-05-05", None, None, "12345", None),
        ("103.0", "No asiste", "2026-08-04", "10:00:00", "10:30:00", None, "2.0", "9000002", "1990-05-05", None, None, "+57 300 999 8877", None),
        ("104.0", "Confirmado whatsapp", "2026-08-05", "11:00:00", "11:30:00", "Control", "3.0", "9000003", None, None, None, None, None),
        ("105.0", "Notif. fallida", "2026-08-05", "11:00:00", "11:30:00", "Control", "3.0", "9000003", None, None, None, None, None),
    ]
    for r in arows:
        wa.append(r)
    a.save(tmp_path / "Agenda y citas .xlsx")


def test_import_maps_states_merges_files_and_normalizes(conn, tmp_path):
    build(tmp_path)
    stats = data.importar(conn, tmp_path)
    assert stats["citas"] == 6
    st = {r["external_id"]: r["estado"] for r in conn.execute("select external_id, estado from cita")}
    assert st == {"cita:100": "atendida", "cita:101": "reprogramada", "cita:102": "cancelada", "cita:103": "no_asistio",
                  "cita:104": "confirmada", "cita:105": "programada"}
    p = {r["external_id"]: r for r in conn.execute("select * from paciente")}
    assert p["1"]["celular"] == "+573001112233" and p["1"]["fecha_nacimiento"] is None   # fecha centinela descartada
    assert p["2"]["celular"] == "+573009998877" and p["2"]["fecha_nacimiento"].year == 1990
    assert p["3"]["celular"] is None
    assert conn.execute("select count(*) n from paciente where celular='+573000012345' or celular='+5712345'").fetchone()["n"] == 0


def test_import_infers_service_keeps_yes_no_and_skips_clinical_notes(conn, tmp_path):
    build(tmp_path)
    data.importar(conn, tmp_path)
    c = conn.execute("select s.nombre, c.datos_origen, c.rango from cita c join servicio s on s.id=c.servicio_id "
                     "where external_id='cita:100'").fetchone()
    assert c["nombre"] == "Limpieza" and c["datos_origen"]["Atendido"] == "Sí" and c["rango"] is not None
    assert "alergia" not in str(conn.execute("select * from paciente").fetchall()).lower()
    other = conn.execute("select s.nombre from cita c join servicio s on s.id=c.servicio_id where external_id='cita:101'").fetchone()
    assert other["nombre"] == "Valoración o revisión"  # «RO» sin otro servicio en el comentario


def test_import_is_idempotent_and_never_sends_messages_or_cases(conn, tmp_path):
    build(tmp_path)
    data.importar(conn, tmp_path)
    data.importar(conn, tmp_path)
    assert conn.execute("select count(*) n from cita").fetchone()["n"] == 6
    assert conn.execute("select count(*) n from paciente").fetchone()["n"] == 3
    assert conn.execute("select count(*) n from mensaje").fetchone()["n"] == 0
    assert conn.execute("select count(*) n from caso_seguimiento").fetchone()["n"] == 0
    assert conn.execute("select count(*) n from tarea_programada").fetchone()["n"] == 0


def test_overlapping_live_imported_appointments_keep_only_date(conn, tmp_path):
    build(tmp_path)
    data.importar(conn, tmp_path)
    # 104 (confirmada) y 105 (programada) comparten profesional y hora: la segunda conserva solo la fecha
    rows = conn.execute("select external_id, rango from cita where external_id in ('cita:104','cita:105') order by id").fetchall()
    assert rows[0]["rango"] is not None and rows[1]["rango"] is None


def test_phone_normalization():
    assert data.normalize_phone("3001112233") == "+573001112233"
    assert data.normalize_phone("3001112233.0") == "+573001112233"
    assert data.normalize_phone("+57 300 111 2233") == "+573001112233"
    assert data.normalize_phone("12345") is None and data.normalize_phone(None) is None


# ---------------------------------------------------------------- R1: semántica de Dentalink (filas sintéticas)

def build_r1(tmp_path, comentario_deportista="Paciente Deportista, viene con su club"):
    """Cada fila es una situación: variantes de «anulado», un «Confirmado» pasado, una futura, «No Aplica» y «RO»."""
    cols_e = ["Nombre Sucursal", "# Paciente", "Nombre Paciente", "Apellidos Paciente", "Antigüedad paciente", "# Tratamiento",
              "Especialidad", "Tratamiento o Diagnóstico", "Nombre Profesional Tratante", "Apellidos Profesional Tratante",
              "# Cita", "Fecha Cita", "Estado actual cita"]
    filas = [  # (paciente, antigüedad, especialidad, cita, fecha, estado, comentario)
        ("1.0", "No Aplica", "RO", "200.0", "2026-08-03", "Anulado", None),
        ("2.0", "2 años", "RO", "201.0", "2026-08-04", "Anulado por pte. vía WhatsApp", "Limpieza"),
        ("3.0", "2 años", "RO", "202.0", "2026-08-05", "ANULADO  por  PCTE   via whatsapp", None),
        ("4.0", "2 años", "Odontología", "203.0", "2026-08-06", "Confirmado", comentario_deportista),
        ("5.0", "2 años", "RO", "204.0", "2026-12-01", "Confirmado por teléfono", "Resina"),
    ]
    e = openpyxl.Workbook()
    we = e.active
    we.append(cols_e)
    a = openpyxl.Workbook()
    wa = a.active
    wa.append(["# Cita", "Hora Inicio Cita", "Hora Fin Cita", "Comentario Cita", "#Número de identificación Paciente",
               "Fecha de nac.", "E-Mail", "Celular", "Tipo Paciente"])
    for i, (pac, ant, esp, cita, fecha, estado, com) in enumerate(filas):
        we.append(["S", pac, f"Nombre{i}", f"Apellido{i}", ant, f"{10 + i}.0", esp, "Tratamiento", "Doc", "Uno", cita, fecha, estado])
        wa.append([cita, f"{9 + i}:00:00", f"{9 + i}:30:00", com, f"90000{i}", "1990-05-05", f"p{i}@ejemplo.com", "3001112233", "Normal"])
    e.save(tmp_path / "Agenda citas y estados .xlsx")
    a.save(tmp_path / "Agenda y citas .xlsx")


def test_estados_con_tildes_puntuacion_y_espacios_se_reconocen(conn, tmp_path):
    build_r1(tmp_path)
    stats = data.importar(conn, tmp_path)
    assert stats["estado_desconocido"] == 0
    assert data.estado_de("Anulado por pcte. vía WhatsApp") == ("cancelada", "whatsapp")
    assert data.estado_de("  Confirmado por TELÉFONO ") == ("confirmada", None)
    assert data.estado_de("algo nuevo") is None


def test_anulado_es_cancelacion_de_la_clinica_sin_motivo_y_sin_caso(conn, tmp_path):
    build_r1(tmp_path)
    data.importar(conn, tmp_path)
    canales = {r["external_id"]: (r["canal"], r["motivo_id"]) for r in conn.execute(
        "select c.external_id, x.canal, x.motivo_id from cancelacion x join cita c on c.id=x.cita_id")}
    assert canales == {"cita:200": ("clinica", None), "cita:201": ("whatsapp", None), "cita:202": ("whatsapp", None)}
    assert conn.execute("select count(*) n from caso_seguimiento").fetchone()["n"] == 0
    assert conn.execute("select count(*) n from mensaje").fetchone()["n"] == 0
    origen = conn.execute("select datos_origen from cita where external_id='cita:201'").fetchone()["datos_origen"]
    assert origen["estado_origen"] == "Anulado por pte. vía WhatsApp"
    data.importar(conn, tmp_path)  # repetir no duplica
    assert conn.execute("select count(*) n from cancelacion").fetchone()["n"] == 3


def test_lo_que_anulo_la_clinica_no_cuenta_como_cancelacion_del_paciente(conn, tmp_path):
    build_r1(tmp_path)
    data.importar(conn, tmp_path)
    indicators.close_range(conn, date(2026, 8, 1), date(2026, 8, 31))
    s = indicators.summary(conn, {"desde": date(2026, 8, 1), "hasta": date(2026, 8, 31)})
    assert s["cancelaciones"] == 2   # solo las dos del paciente por WhatsApp


def test_confirmado_pasado_queda_por_depurar_y_no_cuenta_como_atendido(conn, tmp_path):
    build_r1(tmp_path)
    stats = data.importar(conn, tmp_path)
    assert stats["por_depurar"] == 1   # la del 6 de agosto; la de diciembre es futura
    estado = conn.execute("select estado from cita where external_id='cita:203'").fetchone()["estado"]
    assert estado == "confirmada"
    s = indicators.summary(conn, {"desde": date(2026, 8, 1), "hasta": date(2026, 8, 31)})
    assert s["inasistencia_por_depurar"] == 1 and s["atendidas"] == 0
    assert s["inasistencia"] is None   # nadie atendió ni faltó oficialmente
    assert s["inasistencia_con_pendientes"] == 1.0   # (0 + 1) / (0 + 0 + 1)


def test_no_aplica_marca_paciente_nuevo_y_ro_es_valoracion(conn, tmp_path):
    build_r1(tmp_path)
    data.importar(conn, tmp_path)
    c = {r["external_id"]: r for r in conn.execute(
        "select c.external_id, c.datos_origen, s.nombre servicio from cita c join servicio s on s.id=c.servicio_id")}
    assert c["cita:200"]["datos_origen"]["paciente_nuevo"] is True
    assert "paciente_nuevo" not in c["cita:201"]["datos_origen"]
    assert c["cita:200"]["servicio"] == "Valoración o revisión"
    assert c["cita:201"]["servicio"] == "Limpieza"            # el comentario manda sobre «RO»
    assert c["cita:204"]["servicio"] == "Resina u operatoria"


def test_el_comentario_marca_el_segmento_pero_no_se_guarda(conn, tmp_path):
    build_r1(tmp_path)
    stats = data.importar(conn, tmp_path)
    assert stats["segmentados"] == 1
    p = conn.execute("select deportista from paciente where external_id='4'").fetchone()
    assert p["deportista"] is True
    todo = " ".join(str(conn.execute(f"select * from {t}").fetchall()) for t in ("paciente", "cita", "historial_estado", "tratamiento"))
    assert "club" not in todo.lower() and "Deportista" not in todo


def test_importa_citas_futuras_vivas_sin_mensajes(conn, tmp_path):
    build_r1(tmp_path)
    data.importar(conn, tmp_path)
    f = conn.execute("select estado, origen from cita where external_id='cita:204'").fetchone()
    assert f["estado"] == "confirmada" and f["origen"] == "importacion"
    assert conn.execute("select count(*) n from tarea_programada").fetchone()["n"] == 0


# ---------------------------------------------------------------- R23: importación anonimizada

def test_anonimo_no_deja_nombres_documentos_celulares_ni_estado_original(conn, tmp_path):
    build_r1(tmp_path)
    data.importar(conn, tmp_path, anonimo=True)
    pacientes = conn.execute("select * from paciente order by id").fetchall()
    assert [p["nombres"] for p in pacientes] == [f"Paciente{n:03d}" for n in range(1, 6)]
    assert all(p["apellidos"] == "" and p["documento"] is None and p["correo"] is None for p in pacientes)
    assert all(p["celular"].startswith("+57300000") for p in pacientes)
    assert all(p["fecha_nacimiento"] == date(1990, 7, 1) for p in pacientes)
    tablas = [r["table_name"] for r in conn.execute(
        "select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")]
    volcado = " ".join(str(conn.execute(f"select * from {t}").fetchall()) for t in tablas if t not in ("migracion",)).lower()
    for prohibido in ("nombre0", "apellido0", "nombre4", "90000", "3001112233", "@ejemplo.com", "pte. vía whatsapp", "estado_origen",
                      "club", "1990-05-05"):
        assert prohibido not in volcado, prohibido
    assert "paciente_nuevo" in volcado   # lo que no identifica sí se conserva


def test_anonimo_corre_las_fechas_semanas_completas_y_conserva_el_dia_de_la_semana(conn, tmp_path):
    build_r1(tmp_path)
    data.importar(conn, tmp_path, anonimo=True)
    originales = {"cita:1": date(2026, 8, 3), "cita:2": date(2026, 8, 4), "cita:3": date(2026, 8, 5), "cita:4": date(2026, 8, 6),
                  "cita:5": date(2026, 12, 1)}
    dias = {r["external_id"]: r["dia"] for r in conn.execute("select external_id, dia from cita")}
    assert set(dias) == set(originales)
    desfases = {(dias[k] - originales[k]).days for k in originales}
    assert len(desfases) == 1                     # el mismo corrimiento para todas
    (d,) = desfases
    assert d != 0 and d % 7 == 0                  # semanas completas: el día de la semana se conserva


def test_anonimo_puede_anonimizar_tambien_a_los_profesionales(conn, tmp_path):
    build_r1(tmp_path)
    data.importar(conn, tmp_path, anonimo=True, anonimo_profesionales=True)
    assert [r["nombre"] for r in conn.execute("select nombre from profesional")] == ["Especialista A"]
    data.importar(conn, tmp_path, anonimo=True)
    assert "Doc Uno" in [r["nombre"] for r in conn.execute("select nombre from profesional")]


def test_anonimo_se_niega_fuera_del_entorno_local(monkeypatch):
    monkeypatch.setattr(settings, "ENTORNO", "produccion")
    monkeypatch.setattr("sys.argv", ["data", "importar", "--anonimo"])
    with pytest.raises(SystemExit, match="local"):
        data.main()
