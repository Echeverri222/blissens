import openpyxl
import pytest

from estudia import data
from .conftest import outbox


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
    assert other["nombre"] == "Otro"


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
