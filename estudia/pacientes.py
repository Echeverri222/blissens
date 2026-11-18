"""Pacientes: alta desde el panel o la API (PRD #2 §6.2)."""
from . import clock


class DocumentoExistente(Exception):
    pass


class DatosInvalidos(Exception):
    pass


def create(conn, nombres: str, apellidos: str, documento: str, celular: str, consentimiento: bool) -> int:
    from .data import normalize_phone

    nombres, apellidos, documento = nombres.strip(), apellidos.strip(), "".join(ch for ch in documento if ch.isdigit())
    phone = normalize_phone(celular)
    if not nombres or not documento:
        raise DatosInvalidos("Faltan los nombres o el documento")
    if not phone:
        raise DatosInvalidos("El celular debe tener 10 dígitos y empezar por 3")
    if not consentimiento:
        raise DatosInvalidos("Se necesita la autorización del paciente para tratar sus datos")
    if conn.execute("select 1 from paciente where documento=%s", (documento,)).fetchone():
        raise DocumentoExistente("Ya existe un paciente con ese documento")
    now = clock.now(conn)
    return conn.execute(
        "insert into paciente(nombres, apellidos, documento, celular, consentimiento_en, creado_en) "
        "values (%s,%s,%s,%s,%s,%s) returning id", (nombres, apellidos, documento, phone, now, now)).fetchone()["id"]
