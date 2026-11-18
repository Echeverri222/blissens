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


def _disponibles() -> dict[str, Adaptador]:
    out: dict[str, Adaptador] = {"simulado": Simulado()}
    if settings.ENTORNO != "produccion":
        out["prueba"] = Prueba()
    return out


def adaptador(tipo: str) -> Adaptador | None:
    return _disponibles().get(tipo)


def canal_del_negocio(conn) -> dict | None:
    """El canal activo del negocio activo (si no tiene, usa el simulado)."""
    return conn.execute("select * from canal_negocio where activo order by id limit 1").fetchone()


def tipo_activo(conn) -> str:
    c = canal_del_negocio(conn)
    return c["tipo"] if c and adaptador(c["tipo"]) else "simulado"


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
