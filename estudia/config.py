"""Configuración guardada en la base, con valores por defecto (PRD §6.9)."""
import json
from datetime import time

DEFAULTS = {
    "recordatorios_horas": [48, 24],
    "umbral_tardia_horas": 24,
    "cadencia_seguimiento_dias": [0, 3, 7, 15],
    "dias_hasta_agotar": 7,
    "vigencia_oferta_min": 30,
    "antelacion_minima_cupo_horas": 2,
    "max_ofertas_por_cupo": 5,
    "max_ofertas_paciente_semana": 2,
    "dias_riesgo": 30,
    "horizonte_dias": 60,
    "antelacion_minima_agendar_horas": 2,
    "paso_min": 30,
    "ventana_envio": ["07:00", "20:00"],
    "vigencia_enlace_dias": 30,
    "reintentos_tarea": 3,
    "direccion": "Blissens Odontología, Calle 00 # 00-00, Bogotá",
    "demo_mode": True,
    "reloj_desfase_seg": 0,
    "ultimo_diario": None,
}


def get(conn, key):
    row = conn.execute("select valor from configuracion where clave=%s", (key,)).fetchone()
    return row["valor"] if row else DEFAULTS[key]


def set_(conn, key, value):
    conn.execute(
        "insert into configuracion(clave, valor) values (%s, %s) "
        "on conflict (clave) do update set valor = excluded.valor",
        (key, json.dumps(value)),
    )


def effective(conn) -> dict:
    out = dict(DEFAULTS)
    for r in conn.execute("select clave, valor from configuracion"):
        out[r["clave"]] = r["valor"]
    return out


def parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))
