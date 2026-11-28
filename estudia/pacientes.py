"""Pacientes: alta desde el panel o la API (PRD #2 §6.2)."""
import re

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


def marcar_segmentos(conn, paciente_id: int, internacional: bool, deportista: bool, usuario_id: int | None) -> dict:
    """La recepción marca o desmarca los segmentos de alto valor (internacional, deportista). Su decisión manda: la
    importación ya no la cambia. Devuelve las marcas como quedaron."""
    return conn.execute(
        "update paciente set internacional=%s, deportista=%s, segmento_origen='recepcion', segmento_marcado_en=%s, "
        "segmento_marcado_por=%s where id=%s returning internacional, deportista, segmento_origen, segmento_marcado_en",
        (internacional, deportista, clock.now(conn), usuario_id, paciente_id)).fetchone()


# ----------------------------------------------------------------- prospectos (docs/adr/0010-prospectos-sin-documento.md)

def es_prospecto(p: dict) -> bool:
    return p.get("etapa") == "prospecto"


def buscar_por_contacto(conn, correo: str | None, celular: str | None) -> tuple[dict | None, bool]:
    """La persona que ya tiene ese correo (sin importar mayúsculas) o, si no, ese WhatsApp (por sus dígitos). Devuelve
    (paciente, por_correo). Entre los que comparten celular (un hogar) se prefiere al responsable, no al familiar."""
    if correo:
        p = conn.execute("select * from paciente where lower(correo)=lower(%s) order by (responsable_id is null) desc, id "
                         "limit 1", (correo,)).fetchone()
        if p:
            return p, True
    digitos = "".join(ch for ch in (celular or "") if ch.isdigit())
    if digitos:
        p = conn.execute("select * from paciente where regexp_replace(celular, '\\D', '', 'g')=%s "
                         "order by (responsable_id is null) desc, id limit 1", (digitos,)).fetchone()
        if p:
            return p, False
    return None, False


def atender_solicitud(conn, *, nombre: str, correo: str | None, celular: str | None) -> tuple[int, bool]:
    """El paciente al que se asocia una solicitud del sitio: el que ya existe con ese correo o WhatsApp (un paciente con
    documento no cambia de etapa ni de datos) o un prospecto nuevo, con el segmento internacional y sin autorización de mensajes automáticos (no la dio). Devuelve
    (paciente_id, por_correo). Nunca se completan los datos de quien ya existe: así quien escribe con el correo o el WhatsApp
    de otra persona no puede cambiárselos."""
    existente, por_correo = buscar_por_contacto(conn, correo, celular)
    if existente:
        return existente["id"], por_correo
    from . import config
    now = clock.now(conn)
    pid = conn.execute(
        "insert into paciente(nombres, apellidos, correo, celular, etapa, consentimiento_en, consentimiento_version, creado_en, "
        "internacional, segmento_origen, segmento_marcado_en, acepta_mensajes) "
        "values (%s,'',%s,%s,'prospecto',%s,%s,%s,true,'sitio_web',%s,false) "
        "returning id", (nombre, correo or None, celular or None, now, config.get(conn, "consentimiento_version"), now, now)
    ).fetchone()["id"]
    return pid, bool(correo)


def completar_documento(conn, paciente_id: int, documento: str, celular: str | None = None) -> dict | None:
    """La recepción le pone el documento (y, si hace falta, el celular) a un prospecto: pasa a paciente. None si no existe;
    DocumentoExistente si otro paciente del negocio ya tiene ese documento."""
    from .data import normalize_phone
    p = conn.execute("select * from paciente where id=%s", (paciente_id,)).fetchone()
    if p is None:
        return None
    if not es_prospecto(p):
        raise DatosInvalidos("Esa persona ya es paciente")
    documento = "".join(ch for ch in documento if ch.isdigit())
    if not documento:
        raise DatosInvalidos("Escribe el documento")
    phone = p["celular"]
    if celular and celular.strip():
        phone = normalize_phone(celular) or re.sub(r"[^\d+()\- ]", "", celular)[:30].strip()
        if len("".join(ch for ch in phone if ch.isdigit())) < 7:
            raise DatosInvalidos("El celular no parece válido")
    if conn.execute("select 1 from paciente where documento=%s and id<>%s", (documento, paciente_id)).fetchone():
        raise DocumentoExistente("Ya existe un paciente con ese documento")
    if not phone:
        raise DatosInvalidos("Para atenderlo en la clínica hace falta su celular")
    return conn.execute(
        "update paciente set documento=%s, celular=%s, etapa='paciente' where id=%s "
        "returning id, etapa, documento, celular", (documento, phone, paciente_id)).fetchone()
