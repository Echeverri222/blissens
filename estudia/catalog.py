"""Catálogos que viajan con el proyecto: servicios, motivos y plantillas de mensajes (PRD §6.6, §6.9)."""
import json

SERVICIOS = [  # nombre, duración, autoagendable, admite adelanto
    ("Valoración o revisión", 30, True, True),
    ("Limpieza", 30, True, True),
    ("Control de ortodoncia o alineadores", 30, True, True),
    ("Urgencia", 30, True, True),
    ("Resina u operatoria", 60, False, True),
    ("Blanqueamiento", 60, False, True),
    ("Preparación de rehabilitación", 90, False, False),
    ("Cirugía", 120, False, False),
]

MOTIVOS = ["Salud", "Trabajo o estudio", "Viaje", "Transporte", "Motivo económico", "Confusión de fecha",
           "Ya no la necesito", "Otro"]

_CONF = [{"id": "conf:si:{cita_id}", "title": "Sí, asistiré"},
         {"id": "conf:no:{cita_id}", "title": "No podré ir"},
         {"id": "conf:cambiar:{cita_id}", "title": "Cambiar fecha"}]
_AHORA_NO = [{"id": "seg:ahora_no:{caso_id}", "title": "Ahora no"}]

PLANTILLAS = {
    "cita_agendada": ("¡Hola {nombre}! Tu cita quedó agendada para el {fecha} a las {hora} con {profesional}. "
                      "Te esperamos en {direccion}. ¡Gracias por elegirnos!", "botones", []),
    "recordatorio_48h": ("Hola {nombre}, te recordamos tu cita del {fecha} a las {hora} con {profesional}. "
                         "¿Nos confirmas tu asistencia?", "botones", _CONF),
    "recordatorio_24h": ("Hola {nombre}, mañana es tu cita: {fecha} a las {hora} con {profesional}, en {direccion}. "
                         "¡Te esperamos!", "botones", []),
    "segundo_intento": ("Hola {nombre}, aún no hemos recibido tu confirmación para la cita del {fecha} a las {hora} "
                        "con {profesional}. ¿Puedes responder con un toque?", "botones", _CONF),
    "confirmacion_recibida": ("¡Gracias, {nombre}! Tu cita del {fecha} a las {hora} quedó confirmada. "
                              "Te esperamos en {direccion}.", "botones", []),
    "pedir_motivo": ("Listo {nombre}, cancelamos tu cita del {fecha}. Para mejorar nuestro servicio, "
                     "¿nos cuentas el motivo? Elige una opción.", "lista", []),
    "cancelacion_recibida": ("Gracias, {nombre}. Tu cita del {fecha} quedó cancelada. Cuando quieras retomarla, "
                             "elige un nuevo espacio aquí: {enlace}", "botones", _AHORA_NO),
    "seguimiento_reasignacion": ("Hola {nombre}, queremos ayudarte a retomar la cita que cancelaste. "
                                 "Mira los espacios disponibles aquí: {enlace}", "botones", _AHORA_NO),
    "seguimiento_inasistencia": ("Hola {nombre}, te extrañamos en tu cita del {fecha}. Si quieres reagendarla, "
                                 "elige un espacio aquí: {enlace}", "botones", _AHORA_NO),
    "continuidad_tratamiento": ("Hola {nombre}, queremos acompañarte a continuar tu plan de atención. "
                                "Agenda tu próxima cita aquí: {enlace}", "botones", _AHORA_NO),
    "oferta_adelanto": ("Hola {nombre}, tu cita podría adelantarse de {fecha_actual} a las {hora_actual} a "
                        "{fecha_nueva} a las {hora_nueva}. ¿Quieres hacerlo?", "botones",
                        [{"id": "oferta:si:{oferta_id}", "title": "Sí, adelantarla"},
                         {"id": "oferta:no:{oferta_id}", "title": "No, gracias"}]),
    "adelanto_confirmado": ("¡Listo, {nombre}! Adelantamos tu cita: ahora es el {fecha} a las {hora} con "
                            "{profesional}, en {direccion}. Esta es tu nueva fecha.", "botones", []),
    "oferta_no_disponible": ("Hola {nombre}, ese espacio ya no está disponible. No te preocupes: tu cita original "
                             "sigue igual.", "botones", []),
    "baja_confirmada": ("Listo {nombre}, no te enviaremos más mensajes automáticos por WhatsApp. Los correos, si los "
                        "recibes, se cancelan con el enlace que traen. Si necesitas algo, escríbenos o llámanos.",
                        "botones", []),
    "respuesta_tardia": ("Hola {nombre}, esa cita ya no está vigente. Si necesitas ayuda, la clínica te acompaña "
                         "con gusto.", "botones", []),
    "cambiar_fecha": ("Claro, {nombre}. Elige tu nueva fecha aquí: {enlace}. Tu cita actual se mantiene hasta "
                      "que elijas otra.", "botones", []),
    "seguimiento_pausado": ("Entendido, {nombre}. No insistiremos más sobre esto. Cuando quieras retomar, "
                            "aquí estamos.", "botones", []),
}


def load(conn) -> None:
    """Copia el catálogo del producto al negocio activo. Solo añade lo que falta: nunca pisa lo que el negocio editó."""
    for nombre, dur, auto, adel in SERVICIOS:
        conn.execute(
            "insert into servicio(nombre, duracion_min, autoagendable, admite_adelanto) values (%s,%s,%s,%s) "
            "on conflict (negocio_id, nombre) do nothing", (nombre, dur, auto, adel))
    for i, m in enumerate(MOTIVOS, start=1):
        conn.execute("insert into motivo_cancelacion(etiqueta, orden) values (%s,%s) on conflict (negocio_id, etiqueta) do nothing",
                     (m, i))
    for clave, (texto, tipo, botones) in PLANTILLAS.items():
        conn.execute(
            "insert into plantilla(clave, texto, tipo, botones) values (%s,%s,%s,%s) "
            "on conflict (negocio_id, clave) do nothing",
            (clave, texto, tipo, json.dumps(botones)))


def default_hours(conn, professional_id: int) -> None:
    """Lunes a viernes, 07:30–12:00 y 13:00–17:30."""
    for dia in range(5):
        for desde, hasta in (("07:30", "12:00"), ("13:00", "17:30")):
            conn.execute("insert into horario_atencion(profesional_id, dia_semana, desde, hasta) values (%s,%s,%s,%s)",
                         (professional_id, dia, desde, hasta))
