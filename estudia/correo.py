"""Correo: canal simple y complementario de WhatsApp (PRD 5).

Solo tres correos por cita —agendada, recordatorio de 24 h y cancelada—, con los datos mínimos de la cita (nunca el
servicio ni nada clínico) y un enlace de baja propio. Reutiliza las reglas de envío de WhatsApp (ventana horaria,
diferido, negocio) pero tiene consentimiento propio (`acepta_correo`): quien se da de baja de uno sigue recibiendo el otro.
"""
import re
from datetime import timedelta

from itsdangerous import BadSignature, URLSafeSerializer

from . import canales, clock, config, messaging, settings, tasks
from .lifecycle import ALIVE

_DIRECCION = re.compile(r"[^@\s,;<>\"()\[\]\\]+@[^@\s,;<>\"()\[\]\\]+\.[^@\s,;<>\"()\[\]\\]+")
PIE = "Si no desea recibir más correos nuestros, use este enlace: {enlace_baja}"
CORREOS = {
    "agendada": (
        "Su cita del {fecha} – {negocio}",
        "Hola, {nombre}.\n\nSu cita quedó agendada.\n\n  Día: {fecha}\n  Hora: {hora}\n  Con: {profesional}\n"
        "  Lugar: {direccion}\n\nPara cambiarla o cancelarla: {enlace}\n\n" + PIE),
    "recordatorio": (
        "Mañana es su cita – {negocio}",
        "Hola, {nombre}.\n\nMañana es su cita.\n\n  Día: {fecha}\n  Hora: {hora}\n  Con: {profesional}\n"
        "  Lugar: {direccion}\n\nSi no puede venir, cámbiela o cancélela aquí: {enlace}\n\n" + PIE),
    "cancelada": (
        "Su cita del {fecha} quedó cancelada – {negocio}",
        "Hola, {nombre}.\n\nSu cita del {fecha} a las {hora} con {profesional} quedó cancelada.\n\n"
        "Cuando quiera agendar de nuevo, puede hacerlo aquí: {enlace}\n\n" + PIE),
}


# ----------------------------------------------------------------- baja y consentimiento

def _serializador() -> URLSafeSerializer:
    # La primera clave firma; todas verifican (rotar SECRET_KEY no invalida los enlaces de baja ya enviados).
    claves = [settings.SECRET_KEY] + ([settings.SECRET_KEY_ANTERIOR] if settings.SECRET_KEY_ANTERIOR else [])
    return URLSafeSerializer(claves, salt="baja-correo")


def token_baja(negocio_id: int, paciente_id: int) -> str:
    """Enlace de un solo propósito (solo da de baja el correo) y sin vencimiento: una baja debe poder hacerse siempre."""
    return _serializador().dumps([negocio_id, paciente_id])


def leer_token_baja(token: str) -> tuple[int, int] | None:
    try:
        v = _serializador().loads(token)
    except BadSignature:
        return None
    return (v[0], v[1]) if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v) else None


def es_direccion(correo: str) -> bool:
    return bool(_DIRECCION.fullmatch(correo.strip().lower()))


def registrar_consentimiento(conn, paciente_id: int, correo: str | None, acepta: bool) -> None:
    """Fija el correo del paciente y si autoriza recibir correos (con la fecha en que lo autorizó)."""
    from .pacientes import DatosInvalidos
    correo = (correo or "").strip().lower() or None
    if correo is not None and not _DIRECCION.fullmatch(correo):  # una sola dirección: sin comas, espacios ni saltos
        raise DatosInvalidos("La dirección de correo no es válida")
    if acepta and correo is None:
        raise DatosInvalidos("Para recibir correos se necesita una dirección de correo válida")
    conn.execute(
        "update paciente set correo=%s, acepta_correo=%s, consentimiento_correo_en=%s where id=%s",
        (correo, acepta, clock.now(conn) if acepta else None, paciente_id))


def dar_de_baja(conn, paciente_id: int) -> None:
    """Idempotente. No toca `acepta_mensajes`: la baja de WhatsApp es otra."""
    conn.execute("update paciente set acepta_correo=false where id=%s", (paciente_id,))


# ----------------------------------------------------------------- envío

def _componer(conn, tipo: str, paciente: dict, cita_id: int) -> tuple[str, str]:
    from .agenda import _info
    info = _info(conn, cita_id)
    negocio = conn.execute("select nombre from negocio where id=(select negocio_activo())").fetchone()["nombre"]
    ruta = "/agendar" if tipo == "cancelada" else ""
    data = {**info, "nombre": paciente["nombres"].split()[0].title(), "negocio": negocio,
            "direccion": config.get(conn, "direccion"),
            "enlace": messaging.patient_link(conn, paciente["id"], ruta),
            "enlace_baja": f"{settings.BASE_URL}/correo/baja/{token_baja(_negocio(conn), paciente['id'])}"}
    asunto, cuerpo = CORREOS[tipo]
    return asunto.format(**data), cuerpo.format(**data)


def _negocio(conn) -> int:
    return conn.execute("select negocio_activo() n").fetchone()["n"]


def enviar(conn, paciente_id: int, tipo: str, cita_id: int, *, direct: bool = False) -> int | None:
    """Registra el correo de una cita; la tarea `entregar_correo` lo envía. Devuelve el id del mensaje, o None si no corresponde ni registrarlo
    (el paciente no tiene correo, o ese correo ya salió para esa cita: reenviar es idempotente)."""
    p = conn.execute("select * from paciente where id=%s", (paciente_id,)).fetchone()
    if not p["correo"]:
        return None
    plantilla = f"correo_{tipo}"
    if conn.execute("select 1 from mensaje where canal='correo' and plantilla=%s and entidad_tipo='cita' and entidad_id=%s "
                    "and paciente_id=%s", (plantilla, cita_id, paciente_id)).fetchone():
        return None
    now = clock.now(conn)
    adaptador = canales.adaptador_de_correo(conn)
    # Nunca se envía en línea: el correo sale de la tarea, ya confirmada la cita (ni red dentro de la transacción de
    # agendar, ni correos de citas que luego se deshacen). `diferido` = pendiente de salir.
    estado, momento = "diferido", now
    if not p["acepta_correo"] or adaptador is None:
        estado = "omitido"
    elif not direct and not messaging.window_open(conn, now):
        momento = messaging.next_opening(conn, now)
    asunto, texto = _componer(conn, tipo, p, cita_id)
    mid = conn.execute(
        "insert into mensaje(paciente_id, direccion, plantilla, asunto, texto, tipo, botones, entidad_tipo, entidad_id, "
        "estado_entrega, momento, canal) values (%s,'saliente',%s,%s,%s,'correo','[]','cita',%s,%s,%s,'correo') returning id",
        (paciente_id, plantilla, asunto, texto, cita_id, estado, momento)).fetchone()["id"]
    if estado == "diferido":
        tasks.schedule(conn, "entregar_correo", momento, {"mensaje_id": mid, "intento": 1})
    return mid


def _intentar(conn, mensaje_id: int, intento: int) -> None:
    """Un envío por el proveedor. Si falla, no rompe nada: se reintenta con las tareas y, agotados los intentos, queda
    `fallido`. Mientras reintenta, el mensaje figura `diferido`."""
    m = conn.execute("select * from mensaje where id=%s", (mensaje_id,)).fetchone()
    p = conn.execute("select * from paciente where id=%s", (m["paciente_id"],)).fetchone()
    adaptador = canales.adaptador_de_correo(conn)
    try:
        if adaptador is None:
            raise RuntimeError("El negocio no tiene canal de correo")
        with conn.transaction():
            adaptador.enviar(conn, m, p)
    except Exception:
        if intento >= config.get(conn, "reintentos_tarea"):
            conn.execute("update mensaje set estado_entrega='fallido' where id=%s", (mensaje_id,))
            return
        cuando = clock.now(conn) + timedelta(seconds=30 * intento)
        conn.execute("update mensaje set estado_entrega='diferido', momento=%s where id=%s", (cuando, mensaje_id))
        tasks.schedule(conn, "entregar_correo", cuando, {"mensaje_id": mensaje_id, "intento": intento + 1})
        return
    conn.execute("update mensaje set estado_entrega='entregado' where id=%s", (mensaje_id,))


def entregar_diferido(conn, mensaje_id: int, intento: int) -> None:
    """Handler de la tarea: al abrir la ventana (o al reintentar) se revisa que el correo siga teniendo sentido."""
    m = conn.execute("select * from mensaje where id=%s and estado_entrega='diferido'", (mensaje_id,)).fetchone()
    if m is None:
        return
    p = conn.execute("select acepta_correo, correo from paciente where id=%s", (m["paciente_id"],)).fetchone()
    viva = True
    if m["plantilla"] in ("correo_recordatorio", "correo_agendada"):
        c = conn.execute("select estado, rango from cita where id=%s", (m["entidad_id"],)).fetchone()
        viva = c is not None and c["estado"] in ALIVE
    if not p["acepta_correo"] or not p["correo"] or not viva:
        conn.execute("update mensaje set estado_entrega='omitido' where id=%s", (mensaje_id,))
        return
    _intentar(conn, mensaje_id, intento)

