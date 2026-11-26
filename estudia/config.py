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
    "agrupar_avisos_min": 5,            # espera para juntar en un mensaje las citas que un hogar agenda seguidas
    "direccion": "Blissens Odontología, Calle 00 # 00-00, Bogotá",
    "termino_negocio": "la clínica",
    "texto_consentimiento": "Autorizo a {nombre} a tratar mis datos personales para gestionar mis citas y enviarme mensajes\n"
                            "      sobre ellas (Ley 1581 de 2012). Puedo pedir la baja respondiendo BAJA.",
    "consentimiento_version": "1",
    "demo_mode": True,
    "reloj_desfase_seg": 0,
    "ultimo_diario": None,
    "sesion_horas": 12,
    "retencion_mensajes_dias": None,    # None = no se borra nada (por defecto)
    "retencion_auditoria_dias": None,
    "retencion_sesiones_dias": None,
    "retencion_tareas_dias": None,
    "max_intentos_login": 5,
    "bloqueo_login_min": 15,
    # Metas de los indicadores: {"inasistencia": {"max": 0.15}, "asistencia": {"min": 0.8}, ...}; cada clave es opcional.
    "metas_indicadores": {},
}


def plataforma(key):
    """Valores de la plataforma (sesión e ingreso): no son de un negocio porque el usuario no lo es."""
    return DEFAULTS[key]


def get(conn, key):
    row = conn.execute("select valor from configuracion where clave=%s", (key,)).fetchone()
    return row["valor"] if row else DEFAULTS[key]


def set_(conn, key, value):
    conn.execute(
        "insert into configuracion(clave, valor) values (%s, %s) "
        "on conflict (negocio_id, clave) do update set valor = excluded.valor",
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
