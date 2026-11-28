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


# ----------------------------------------------------------------- no contactar (docs/prd-respuestas-clinica.md, R6)

MOTIVOS_NO_CONTACTAR = ("queja", "cobro", "fallecido", "otro")
ETIQUETA_NO_CONTACTAR = {"queja": "Queja activa", "cobro": "Cobro jurídico", "fallecido": "Fallecido", "otro": "No contactar"}
# Fragmento para las consultas que arman listas de trabajo o envíos automáticos (alias `p` de `paciente`).
SQL_CONTACTABLE = "p.no_contactar is null"
SQL_NO_FALLECIDO = "p.no_contactar is distinct from 'fallecido'"


def contactable(conn, paciente_id: int) -> bool:
    """¿Se le puede escribir o llamar por iniciativa de la clínica? Gancho para recuperación, controles, planes y ofertas."""
    r = conn.execute("select no_contactar from paciente where id=%s", (paciente_id,)).fetchone()
    return r is not None and r["no_contactar"] is None


def bloquea_mensaje(p: dict, directo: bool) -> bool:
    """`fallecido` no recibe nada; con otra marca solo salen las respuestas directas a lo que la persona acaba de hacer."""
    motivo = p.get("no_contactar")
    return motivo == "fallecido" or (motivo is not None and not directo)


def celular_usable(p: dict) -> bool:
    return bool(p.get("celular")) and p.get("celular_estado", "sin_verificar") in ("sin_verificar", "valido")


def no_contactar(conn, paciente_id: int, motivo: str, nota: str | None, usuario_id: int | None) -> dict | None:
    """Marca al paciente como "No contactar". Cierra como `anulado` sus casos de seguimiento abiertos. None si no existe."""
    if motivo not in MOTIVOS_NO_CONTACTAR:
        raise DatosInvalidos("Elige un motivo válido")
    nota = (nota or "").strip()[:200] or None
    now = clock.now(conn)
    r = conn.execute(
        "update paciente set no_contactar=%s, no_contactar_en=%s, no_contactar_por=%s, no_contactar_nota=%s where id=%s "
        "returning id, no_contactar, no_contactar_en, no_contactar_nota", (motivo, now, usuario_id, nota, paciente_id)).fetchone()
    if r is None:
        return None
    conn.execute("update caso_seguimiento set estado='anulado', cerrado_en=%s, cerrado_por=%s "
                 "where paciente_id=%s and estado='abierto'", (now, usuario_id, paciente_id))
    return r


def quitar_no_contactar(conn, paciente_id: int) -> dict | None:
    return conn.execute(
        "update paciente set no_contactar=null, no_contactar_en=null, no_contactar_por=null, no_contactar_nota=null "
        "where id=%s returning id, no_contactar, no_contactar_en, no_contactar_nota", (paciente_id,)).fetchone()
