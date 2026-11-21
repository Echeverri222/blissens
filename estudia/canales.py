"""Puerto del canal de mensajes (PRD #4, D10).

`messaging` no conoce al proveedor: habla con un adaptador de tres operaciones — enviar un mensaje ya compuesto,
verificar que una petición entrante es auténtica y traducirla a «botón o texto de tal remitente». Cada negocio tiene su
canal en `canal_negocio` (tipo, identificador externo y la REFERENCIA —nombre de variable de entorno— del secreto,
nunca el secreto).
"""
import hashlib
import hmac
import json
import os
from dataclasses import dataclass

from . import settings


@dataclass
class Entrante:
    id_mensaje: str            # identificador del proveedor (idempotencia)
    celular: str               # remitente
    boton: str | None = None
    texto: str | None = None


class Adaptador:
    tipo = ""
    medio = "mensajeria"   # «mensajeria» (WhatsApp y similares) o «correo»: un negocio tiene un canal activo por medio

    def identificar(self, cuerpo: dict) -> str | None:
        """Identificador del canal destino (para encaminar al negocio ANTES de verificar la firma)."""
        raise NotImplementedError

    def verificar(self, cuerpo_crudo: bytes, cabeceras, secreto: str) -> bool:
        raise NotImplementedError

    def traducir(self, cuerpo: dict) -> Entrante | None:
        raise NotImplementedError

    def enviar(self, conn, mensaje: dict, paciente: dict) -> None:
        raise NotImplementedError


class Simulado(Adaptador):
    """El canal de hoy: el mensaje queda en la bitácora y el simulador lo muestra. No tiene entrada real."""
    tipo = "simulado"

    def identificar(self, cuerpo):
        return None

    def verificar(self, cuerpo_crudo, cabeceras, secreto):
        return False

    def traducir(self, cuerpo):
        return None

    def enviar(self, conn, mensaje, paciente):
        return None


class Prueba(Adaptador):
    """Adaptador para probar el encaminamiento sin WhatsApp: firma HMAC-SHA256 en `X-Firma` y cuerpo JSON
    `{"canal": ..., "id": ..., "de": celular, "boton": ..., "texto": ...}`. No existe en producción."""
    tipo = "prueba"
    ENVIADOS: list[dict] = []

    def identificar(self, cuerpo):
        return cuerpo.get("canal")

    def verificar(self, cuerpo_crudo, cabeceras, secreto):
        esperada = hmac.new(secreto.encode(), cuerpo_crudo, hashlib.sha256).hexdigest()
        return hmac.compare_digest(esperada, cabeceras.get("x-firma", ""))

    def traducir(self, cuerpo):
        if not cuerpo.get("id") or not cuerpo.get("de"):
            return None
        return Entrante(str(cuerpo["id"]), str(cuerpo["de"]), cuerpo.get("boton"), cuerpo.get("texto"))

    def enviar(self, conn, mensaje, paciente):
        self.ENVIADOS.append({"mensaje_id": mensaje["id"], "celular": paciente["celular"], "texto": mensaje["texto"]})


class AdaptadorCorreo(Adaptador):
    """Base de los adaptadores de correo: no reciben nada; solo envían un correo ya compuesto (asunto y texto plano)."""
    medio = "correo"

    def identificar(self, cuerpo):
        return None

    def verificar(self, cuerpo_crudo, cabeceras, secreto):
        return False

    def traducir(self, cuerpo):
        return None


class CorreoSimulado(AdaptadorCorreo):
    """El correo de `local` y `demo`: no sale; queda en la bitácora y la bandeja del simulador lo muestra."""
    tipo = "correo_simulado"

    def enviar(self, conn, mensaje, paciente):
        return None


class CorreoPrueba(AdaptadorCorreo):
    """Proveedor de prueba: guarda lo «enviado» y puede fallar a voluntad (`FALLAR`). No existe en producción."""
    tipo = "correo_prueba"
    ENVIADOS: list[dict] = []
    FALLAR = False

    def enviar(self, conn, mensaje, paciente):
        if self.FALLAR:
            raise RuntimeError("El proveedor de prueba rechazó el correo")
        remitente = (canal_del_negocio(conn, "correo") or {}).get("id_externo")
        self.ENVIADOS.append({"mensaje_id": mensaje["id"], "de": remitente, "para": paciente["correo"],
                              "asunto": mensaje["asunto"], "texto": mensaje["texto"]})


class CorreoSMTP(AdaptadorCorreo):
    """SMTP genérico (solo producción). `id_externo` del canal es el remitente y `secreto_ref` nombra la variable de
    entorno con la URL de conexión: `smtp://usuario:clave@servidor:587` (`smtps://` para TLS directo)."""
    tipo = "smtp"

    def enviar(self, conn, mensaje, paciente):
        import html
        import re
        import smtplib
        from email.message import EmailMessage
        from urllib.parse import unquote, urlparse

        canal = canal_del_negocio(conn, "correo")
        url = urlparse(secreto_de(canal) or "")
        if not url.hostname:
            raise RuntimeError("El canal de correo no tiene credenciales (revisa secreto_ref)")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = canal["id_externo"], paciente["correo"], mensaje["asunto"]
        baja = re.search(r"https?://\S+/correo/baja/\S+", mensaje["texto"])
        if baja:
            msg["List-Unsubscribe"] = f"<{baja.group(0)}>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg.set_content(mensaje["texto"])
        cuerpo = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', html.escape(mensaje["texto"]))
        msg.add_alternative("<html><body style=\"font-family:sans-serif\">"
                            + cuerpo.replace("\n", "<br>") + "</body></html>", subtype="html")
        directo = url.scheme == "smtps"
        with (smtplib.SMTP_SSL if directo else smtplib.SMTP)(url.hostname, url.port or (465 if directo else 587),
                                                             timeout=15) as s:
            if not directo:
                s.starttls()
            if url.username:
                s.login(unquote(url.username), unquote(url.password or ""))
            s.send_message(msg)


def _disponibles() -> dict[str, Adaptador]:
    out: dict[str, Adaptador] = {"simulado": Simulado()}
    if settings.ENTORNO != "produccion":
        out["prueba"] = Prueba()
        out["correo_simulado"] = CorreoSimulado()
        out["correo_prueba"] = CorreoPrueba()
    else:
        out["smtp"] = CorreoSMTP()
    return out


def adaptador(tipo: str) -> Adaptador | None:
    return _disponibles().get(tipo)


def canal_del_negocio(conn, medio: str = "mensajeria") -> dict | None:
    """El canal activo del negocio activo para ese medio (con un adaptador disponible en este entorno)."""
    for c in conn.execute("select * from canal_negocio where activo order by id").fetchall():
        a = adaptador(c["tipo"])
        if a is not None and a.medio == medio:
            return c
    return None


def tipo_activo(conn) -> str:
    c = canal_del_negocio(conn)
    return c["tipo"] if c else "simulado"


def adaptador_de_correo(conn) -> Adaptador | None:
    """Adaptador de correo del negocio. Sin canal propio, en `local` y `demo` el correo se simula (no sale); en
    producción, un negocio sin canal de correo no envía correos."""
    c = canal_del_negocio(conn, "correo")
    if c:
        return adaptador(c["tipo"])
    return adaptador("correo_simulado")


def enviar_mensaje(conn, mensaje_id: int) -> None:
    """Entrega por el canal del negocio un mensaje saliente ya guardado (no hace nada con el simulado)."""
    m = conn.execute("select * from mensaje where id=%s", (mensaje_id,)).fetchone()
    if m is None or m["direccion"] != "saliente":
        return
    a = adaptador(m["canal"])
    if a is None or a.tipo == "simulado":
        return
    p = conn.execute("select * from paciente where id=%s", (m["paciente_id"],)).fetchone()
    a.enviar(conn, m, p)


def secreto_de(canal: dict) -> str | None:
    ref = canal.get("secreto_ref")
    return os.environ.get(ref) if ref else None


def cuerpo_json(crudo: bytes) -> dict | None:
    try:
        d = json.loads(crudo)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None
