"""Solicitudes del sitio web (evaluación virtual, experiencias, contacto).

Cada una queda en `solicitud_contacto` con sus datos en columnas propias, con hasta `MAX_ADJUNTOS` fotos o PDF, y con dos
correos que salen de una tarea (nunca dentro de la petición): el aviso a la clínica, si el negocio configuró a quién
avisar, y el acuse a quien la envió, si dejó correo. La recepción la gestiona en Bandejas y puede vincularla a un paciente.
"""
from dataclasses import dataclass

from . import canales, clock, config, links, pacientes, settings, tasks

MAX_ADJUNTOS = 4
MAX_ADJUNTOS_TOTAL = 12              # entre lo que mandó al principio y lo que agregó después
MAX_BYTES = 5 * 1024 * 1024          # por archivo (lo mismo exige la base)
MAX_TOTAL = 12 * 1024 * 1024
INTERESES = {"evaluacion_virtual": ("Evaluación virtual", "Virtual assessment"),
             "experiencia": ("Experiencia", "Experience"),
             "contacto": ("Contacto", "Contact")}


class AdjuntoInvalido(Exception):
    pass


@dataclass
class Adjunto:
    nombre: str
    datos: bytes


def tipo_de(datos: bytes) -> str | None:
    """El tipo se decide por el contenido, no por la extensión ni por lo que diga el navegador."""
    if datos.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    if datos.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def validar_adjuntos(adjuntos: list[Adjunto]) -> list[tuple[str, str, bytes]]:
    """(nombre, tipo, datos) de cada archivo, o AdjuntoInvalido con la razón (`cantidad`, `tamano`, `tipo`)."""
    if len(adjuntos) > MAX_ADJUNTOS:
        raise AdjuntoInvalido("cantidad")
    if sum(len(a.datos) for a in adjuntos) > MAX_TOTAL or any(len(a.datos) > MAX_BYTES for a in adjuntos):
        raise AdjuntoInvalido("tamano")
    out = []
    for a in adjuntos:
        tipo = tipo_de(a.datos)
        if tipo is None:
            raise AdjuntoInvalido("tipo")
        nombre = "".join(ch for ch in a.nombre if ch.isprintable() and ch not in '/\\"')[-120:] or "archivo"
        out.append((nombre, tipo, a.datos))
    return out


def _guardar_adjuntos(conn, solicitud_id: int, adjuntos: list[tuple[str, str, bytes]], now) -> None:
    for n, tipo, datos in adjuntos:
        conn.execute("insert into solicitud_adjunto(solicitud_id, nombre, tipo, tamano, datos, creado_en) "
                     "values (%s,%s,%s,%s,%s,%s)", (solicitud_id, n, tipo, len(datos), datos, now))


def agregar_adjuntos(conn, solicitud_id: int, adjuntos: list[tuple[str, str, bytes]]) -> None:
    """Más archivos (ya validados) para una solicitud existente, hasta `MAX_ADJUNTOS_TOTAL` en ella. Si estaba gestionada,
    vuelve a la bandeja: la recepción tiene algo nuevo que mirar."""
    ya = conn.execute("select count(*) n from solicitud_adjunto where solicitud_id=%s", (solicitud_id,)).fetchone()["n"]
    if ya + len(adjuntos) > MAX_ADJUNTOS_TOTAL:
        raise AdjuntoInvalido("cantidad")
    _guardar_adjuntos(conn, solicitud_id, adjuntos, clock.now(conn))
    conn.execute("update solicitud_contacto set gestionada=false where id=%s", (solicitud_id,))


def crear(conn, *, interes: str, idioma: str, nombre: str, correo: str | None, celular: str, pais: str | None,
          paquete: str | None, mensaje: str | None, adjuntos: list[tuple[str, str, bytes]]) -> int:
    """Guarda la solicitud, la asocia a su paciente (el que ya tenga ese correo o WhatsApp, o un prospecto nuevo), guarda
    sus adjuntos y programa los correos. Los datos ya vienen validados."""
    from .web import copia
    now = clock.now(conn)
    paciente_id, _ = pacientes.atender_solicitud(conn, nombre=nombre, correo=correo, celular=celular)
    etiqueta = copia.INTERESES[interes] + (f" · {copia.PAQUETES[paquete]}" if paquete else "")
    sid = conn.execute(
        "insert into solicitud_contacto(documento, celular, nota, momento, origen, interes, idioma, nombre, correo, pais, "
        "paquete, mensaje, paciente_id) values ('—',%s,%s,%s,'sitio',%s,%s,%s,%s,%s,%s,%s,%s) returning id",
        (celular, f"Sitio web · {etiqueta}", now, interes, idioma, nombre, correo, pais, paquete, mensaje,
         paciente_id)).fetchone()["id"]
    _guardar_adjuntos(conn, sid, adjuntos, now)
    if config.get(conn, "correo_avisos_solicitudes"):
        tasks.schedule(conn, "correo_solicitud", now, {"solicitud_id": sid, "tipo": "aviso"})
    if correo:
        tasks.schedule(conn, "correo_solicitud", now, {"solicitud_id": sid, "tipo": "acuse"})
    return sid


# ----------------------------------------------------------------- correos

def _negocio(conn) -> str:
    return conn.execute("select nombre from negocio where id=(select negocio_activo())").fetchone()["nombre"]


def _enlace_personal(conn, s: dict) -> str | None:
    """La página de la persona (`/p/<enlace>`), solo si el correo de la solicitud es el que ella tiene en su ficha: el
    enlace va a ese buzón y nunca a quien escribió con el WhatsApp de otra persona."""
    if not s["paciente_id"]:
        return None
    p = conn.execute("select id, celular, correo, nombres, documento from paciente where id=%s", (s["paciente_id"],)).fetchone()
    from .privacidad import ANONIMO
    if p is None or not p["correo"] or p["correo"].lower() != (s["correo"] or "").lower() \
            or (p["documento"] is None and p["nombres"] == ANONIMO):
        return None
    return f"{settings.BASE_URL}/p/{links.make_token(p['id'], conn=conn, celular=p['celular'], correo=p['correo'])}"


def componer(conn, s: dict, tipo: str) -> tuple[str, str, str] | None:
    """(destinatario, asunto, texto) del correo, o None si ya no corresponde enviarlo."""
    negocio = _negocio(conn)
    if tipo == "aviso":
        destino = config.get(conn, "correo_avisos_solicitudes")
        if not destino:
            return None
        n = conn.execute("select count(*) n from solicitud_adjunto where solicitud_id=%s", (s["id"],)).fetchone()["n"]
        filas = [("Tipo", INTERESES[s["interes"]][0] + (f" · {s['paquete']}" if s["paquete"] else "")),
                 ("Nombre", s["nombre"]), ("Correo", s["correo"]), ("Celular", s["celular"] or None),
                 ("País", s["pais"]), ("Idioma", (s["idioma"] or "es").upper()),
                 ("Archivos adjuntos", str(n) if n else None), ("Mensaje", s["mensaje"])]
        cuerpo = "\n".join(f"  {k}: {v}" for k, v in filas if v)
        return (destino, f"Nueva solicitud web: {INTERESES[s['interes']][0]} – {s['nombre']}",
                f"Llegó una solicitud desde el sitio web de {negocio}.\n\n{cuerpo}\n\n"
                f"Respóndela y márcala como gestionada en el panel: {settings.BASE_URL}/panel/bandejas?b=contactos")
    if not s["correo"]:
        return None
    horas = config.get(conn, "plazo_respuesta_solicitud_horas")
    enlace = _enlace_personal(conn, s)
    primer = (s["nombre"] or "").split()[0].title() if s["nombre"] else ""
    if s["idioma"] == "en":
        return (s["correo"], f"We received your request – {negocio}",
                f"Hi {primer},\n\nThank you for writing to {negocio}. We received your request "
                f"({INTERESES[s['interes']][1].lower()}) and our team will reply within {horas} hours.\n\n"
                + (f"Follow your request and add photos or X-rays here: {enlace}\n\n" if enlace else "")
                + "If you need to add something, just reply to this email.\n\n"
                "You are receiving this message only because you sent a request on our website.")
    return (s["correo"], f"Recibimos tu solicitud – {negocio}",
            f"Hola {primer},\n\nGracias por escribirle a {negocio}. Recibimos tu solicitud "
            f"({INTERESES[s['interes']][0].lower()}) y nuestro equipo te responderá en las próximas {horas} horas.\n\n"
            + (f"Mira cómo va tu solicitud y agrega fotos o radiografías aquí: {enlace}\n\n" if enlace else "")
            + "Si quieres agregar algo, responde este correo.\n\n"
            "Recibes este mensaje solo porque enviaste una solicitud en nuestro sitio web.")


def entregar_correo(conn, solicitud_id: int, tipo: str) -> None:
    """Handler de la tarea `correo_solicitud`. Idempotente: cada correo sale una vez. Si el proveedor falla, la excepción
    sube y la tarea se reintenta."""
    columna = {"aviso": "aviso_enviado_en", "acuse": "acuse_enviado_en"}[tipo]
    s = conn.execute(f"select * from solicitud_contacto where id=%s and {columna} is null", (solicitud_id,)).fetchone()
    if s is None:   # ya salió, o se borró (p. ej. al anonimizar)
        return
    correo = componer(conn, s, tipo)
    adaptador = canales.adaptador_de_correo(conn)
    if correo is not None and adaptador is not None:
        destino, asunto, texto = correo
        adaptador.enviar(conn, {"id": None, "asunto": asunto, "texto": texto}, {"correo": destino})
    conn.execute(f"update solicitud_contacto set {columna}=%s where id=%s", (clock.now(conn), solicitud_id))


# ----------------------------------------------------------------- recepción

def adjuntos(conn, solicitud_id: int) -> list[dict]:
    return conn.execute("select id, nombre, tipo, tamano from solicitud_adjunto where solicitud_id=%s order by id",
                        (solicitud_id,)).fetchall()


def adjunto(conn, solicitud_id: int, adjunto_id: int) -> dict | None:
    return conn.execute("select nombre, tipo, datos from solicitud_adjunto where id=%s and solicitud_id=%s",
                        (adjunto_id, solicitud_id)).fetchone()


def vincular(conn, solicitud_id: int, paciente_id: int, usuario_id: int | None) -> dict:
    """La solicitud pasa a ser de ese paciente. Si el paciente no tiene correo, toma el de la solicitud (sin autorizar
    envíos: eso lo decide el paciente). Una evaluación virtual marca al paciente como internacional."""
    s = conn.execute("select * from solicitud_contacto where id=%s", (solicitud_id,)).fetchone()
    p = conn.execute("select * from paciente where id=%s", (paciente_id,)).fetchone()
    from .privacidad import ANONIMO
    if s is None or p is None or (p["documento"] is None and p["nombres"] == ANONIMO):
        return {}
    conn.execute("update solicitud_contacto set paciente_id=%s where id=%s", (paciente_id, solicitud_id))
    if s["correo"] and not p["correo"]:
        conn.execute("update paciente set correo=%s where id=%s", (s["correo"].lower(), paciente_id))
    if s["interes"] == "evaluacion_virtual" and not p["internacional"]:
        pacientes.marcar_segmentos(conn, paciente_id, True, p["deportista"], usuario_id)
    return {"paciente_id": paciente_id}
