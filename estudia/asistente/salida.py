"""Lo que sale de una herramienta: datos JSON seguros, sin campos sensibles y con tope de tamaño (PRD asistente, P5 y §5)."""
import json
from datetime import date, datetime, time
from decimal import Decimal

from psycopg.types.range import Range

from .. import clock

LIMITE_CARACTERES = 8000
LIMITE_TEXTO = 500
# Ninguna herramienta devuelve estos datos completos (P5): se quitan aunque un manejador los dejara pasar.
SENSIBLES = frozenset({"documento", "celular", "correo", "fecha_nacimiento", "datos_origen"})
SENSIBLES_PACIENTE = SENSIBLES | {"valor"}  # `servicio.valor` es un promedio interno, no un precio


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, Range):
        return {"inicio": jsonable(x.lower), "fin": jsonable(x.upper)}
    if isinstance(x, datetime):
        return x.astimezone(clock.TZ).isoformat()
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, time):
        return x.strftime("%H:%M")
    if isinstance(x, Decimal):
        return int(x) if x == x.to_integral_value() else float(x)
    if isinstance(x, str):
        return x if len(x) <= LIMITE_TEXTO else x[:LIMITE_TEXTO] + "…"
    if x is None or isinstance(x, (bool, int, float)):
        return x
    return str(x)


def sanear(x, prohibidas: frozenset[str]):
    if isinstance(x, dict):
        return {k: sanear(v, prohibidas) for k, v in x.items() if k not in prohibidas}
    if isinstance(x, list):
        return [sanear(v, prohibidas) for v in x]
    return x


def _tam(x) -> int:
    return len(json.dumps(x, ensure_ascii=False))


def _listas(x):
    if isinstance(x, list):
        yield x
        for v in x:
            yield from _listas(v)
    elif isinstance(x, dict):
        for v in x.values():
            yield from _listas(v)


def recortar(salida: dict, limite: int = LIMITE_CARACTERES) -> dict:
    """Quita filas del final de la lista más larga hasta que quepa; marca `truncado`."""
    if _tam(salida) <= limite:
        return salida
    salida = {**salida, "truncado": True}
    while _tam(salida) > limite:
        mayor = max(_listas(salida), key=len, default=None)
        if not mayor:
            return {"truncado": True, "aviso": "La respuesta era demasiado larga para mostrarla."}
        mayor.pop()
    return salida
