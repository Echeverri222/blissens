"""Formato de fechas en español."""
from datetime import date, datetime

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def fecha(d: date | datetime) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def hora(d: datetime) -> str:
    h = d.hour % 12 or 12
    return f"{h}:{d.minute:02d} {'a. m.' if d.hour < 12 else 'p. m.'}"


def fecha_hora(d: datetime) -> str:
    return f"{fecha(d)} a las {hora(d)}"
