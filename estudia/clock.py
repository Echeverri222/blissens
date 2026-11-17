"""Reloj único. Ninguna regla usa la hora del sistema ni la de la base directamente."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo("America/Bogota")
_frozen: datetime | None = None  # solo para pruebas


def freeze(dt: datetime | None) -> None:
    global _frozen
    _frozen = dt.astimezone(TZ) if dt else None


def advance(delta: timedelta) -> None:
    global _frozen
    assert _frozen is not None
    _frozen = _frozen + delta


def tz(conn) -> ZoneInfo:
    """Zona horaria del negocio activo (la de la sesión de la base); `TZ` es el valor por defecto del producto."""
    try:
        return ZoneInfo(conn.execute("select current_setting('TimeZone') z").fetchone()["z"])
    except Exception:
        return TZ


def now(conn) -> datetime:
    if _frozen is not None:
        return _frozen.astimezone(tz(conn))
    real = datetime.now(tz(conn))
    if demo_activo(conn):
        return real + timedelta(seconds=float(config.get(conn, "reloj_desfase_seg")))
    return real


def demo_activo(conn) -> bool:
    """El reloj simulado solo existe fuera de producción (PRD #4, D7); allí se ignora aunque esté en la base."""
    from . import settings
    return settings.ENTORNO != "produccion" and bool(config.get(conn, "demo_mode"))


def shift(conn, delta: timedelta) -> datetime:
    """Adelanta el reloj en modo demo (desfase guardado en la base, compartido por los procesos)."""
    cur = float(config.get(conn, "reloj_desfase_seg"))
    config.set_(conn, "reloj_desfase_seg", cur + delta.total_seconds())
    return now(conn)


def jump_to(conn, target: datetime) -> datetime:
    """Salta a una hora objetivo (desfase = objetivo - hora real)."""
    config.set_(conn, "reloj_desfase_seg", (target - datetime.now(tz(conn))).total_seconds())
    return now(conn)


def reset(conn) -> datetime:
    config.set_(conn, "reloj_desfase_seg", 0)
    return now(conn)
