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
# Avisos agrupados del hogar (docs/prd-familia.md §4 R9): un solo mensaje al celular compartido, dirigido al responsable.
# `{ids}` son las citas a las que aplica el botón, separadas por guiones. No hay "No podré ir" de un toque: cancelar varias
# citas así sería un error caro; se cancela cita por cita desde el enlace.
_CONF_HOGAR = [{"id": "confh:si:{ids}", "title": "Sí, asistiremos"},
               {"id": "confh:cambiar:{ids}", "title": "Cambiar o cancelar"}]

PLANTILLAS = {
    "cita_agendada": ("Hola, {nombre}. Su cita quedó agendada para el {fecha} a las {hora} con {profesional}. Le esperamos en {direccion}. Gracias por elegirnos.", "botones", []),
    "recordatorio_48h": ("Hola, {nombre}. Le recordamos su cita del {fecha} a las {hora} con {profesional}. ¿Nos confirma su asistencia?", "botones", _CONF),
    "recordatorio_24h": ("Hola, {nombre}. Mañana es su cita: {fecha} a las {hora} con {profesional}, en {direccion}. Le esperamos.", "botones", []),
    "segundo_intento": ("Hola, {nombre}. Aún no hemos recibido su confirmación para la cita del {fecha} a las {hora} con {profesional}. ¿Puede responder con un toque?", "botones", _CONF),
    "confirmacion_recibida": ("Gracias, {nombre}. Su cita del {fecha} a las {hora} quedó confirmada. Le esperamos en {direccion}.", "botones", []),
    "pedir_motivo": ("Listo, {nombre}. Cancelamos su cita del {fecha}. Para mejorar nuestro servicio, ¿nos cuenta el motivo? Elija una opción.", "lista", []),
    "cancelacion_recibida": ("Gracias, {nombre}. Su cita del {fecha} quedó cancelada. Cuando quiera retomarla, elija un nuevo espacio aquí: {enlace}", "botones", _AHORA_NO),
    "seguimiento_reasignacion": ("Hola, {nombre}. Queremos ayudarle a retomar la cita que canceló. Vea los espacios disponibles aquí: {enlace}", "botones", _AHORA_NO),
    "seguimiento_inasistencia": ("Hola, {nombre}. Le extrañamos en su cita del {fecha}. Si desea reagendarla, elija un espacio aquí: {enlace}", "botones", _AHORA_NO),
    "continuidad_tratamiento": ("Hola, {nombre}. Queremos acompañarle a continuar su plan de atención. Agende su próxima cita aquí: {enlace}", "botones", _AHORA_NO),
    "oferta_adelanto": ("Hola, {nombre}. Su cita podría adelantarse de {fecha_actual} a las {hora_actual} a {fecha_nueva} a las {hora_nueva}. ¿Desea hacerlo?", "botones",
                        [{"id": "oferta:si:{oferta_id}", "title": "Sí, adelantarla"},
                         {"id": "oferta:no:{oferta_id}", "title": "No, gracias"}]),
    "adelanto_confirmado": ("Listo, {nombre}. Adelantamos su cita: ahora es el {fecha} a las {hora} con {profesional}, en {direccion}. Esta es su nueva fecha.", "botones", []),
    "oferta_no_disponible": ("Hola, {nombre}. Ese espacio ya no está disponible. No se preocupe: su cita original sigue igual.", "botones", []),
    "baja_confirmada": ("Listo, {nombre}. No le enviaremos más mensajes automáticos por WhatsApp. Los correos, si los recibe, se cancelan con el enlace que traen. Si necesita algo, escríbanos o llámenos.",
                        "botones", []),
    "respuesta_tardia": ("Hola, {nombre}. Esa cita ya no está vigente. Si necesita ayuda, la clínica le acompaña con gusto.", "botones", []),
    "cambiar_fecha": ("Claro, {nombre}. Elija su nueva fecha aquí: {enlace}. Su cita actual se mantiene hasta que elija otra.", "botones", []),
    "seguimiento_pausado": ("Entendido, {nombre}. No insistiremos más sobre esto. Cuando quiera retomar, aquí estamos.", "botones", []),
    "cita_agendada_hogar": ("Hola, {nombre}. Le confirmamos lo que quedó agendado:\n{lista}\nLos esperamos en {direccion}. Gracias por elegirnos.", "botones", []),
    "recordatorio_48h_hogar": ("Hola, {nombre}. Le recordamos las próximas citas de su familia:\n{lista}\n¿Nos confirma la asistencia?", "botones", _CONF_HOGAR),
    "recordatorio_24h_hogar": ("Hola, {nombre}. Mañana tienen cita:\n{lista}\nLos esperamos en {direccion}.",
                               "botones", []),
    "segundo_intento_hogar": ("Hola, {nombre}. Mañana tienen cita:\n{lista}\nAún nos falta la confirmación de las que dicen «sin confirmar». ¿Puede responder con un toque?", "botones", _CONF_HOGAR),
    "confirmacion_recibida_hogar": ("Gracias, {nombre}. Quedaron confirmadas:\n{lista}\nLos esperamos en {direccion}.",
                                    "botones", []),
    "cambiar_hogar": ("Claro, {nombre}. Desde aquí puede cambiar o cancelar cada cita: {enlace}", "botones", []),
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
