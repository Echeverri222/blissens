"""Alertas de Sistema en palabras: qué no salió, a quién le afecta, por qué y qué hacer.

Las tareas programadas guardan el error técnico (la traza de Python). La recepción no la necesita: necesita saber qué
paciente se quedó sin su aviso y qué hacer. La traza sigue disponible para quien administra el sistema."""
from datetime import timedelta

from . import clock

# Por tipo de tarea: qué es lo que no salió (en singular y plural) y qué hacer con cada paciente.
QUE_ES = {
    "recordatorio": ("No salió el recordatorio de una cita", "recordatorios de cita no salieron",
                     "Llama al paciente para recordarle la cita y confirmarla."),
    "avisar_agendadas": ("No salió el aviso de las citas agendadas", "avisos de citas agendadas no salieron",
                         "Llama al paciente y dile la fecha y hora de sus citas."),
    "intento_seguimiento": ("No salió un mensaje de seguimiento", "mensajes de seguimiento no salieron",
                            "Llama al paciente para retomar el seguimiento."),
    "agotar_caso": ("No se pudo cerrar un seguimiento sin respuesta", "seguimientos sin respuesta no se pudieron cerrar",
                    "Revisa el caso en Pendientes y ciérralo o llama al paciente."),
    "vencer_oferta": ("No se venció a tiempo una oferta de adelanto", "ofertas de adelanto no se vencieron a tiempo",
                      "Revisa en la agenda si el horario ofrecido sigue libre."),
    "entregar_mensaje": ("No se entregó un WhatsApp", "WhatsApp no se entregaron",
                         "Llama al paciente o vuelve a escribirle desde su ficha."),
    "entregar_correo": ("No se entregó un correo", "correos no se entregaron",
                        "Llama al paciente: el correo no le llegó."),
}
_OTRA = ("Una tarea automática falló", "tareas automáticas fallaron", "Avisa a quien administra el sistema.")

# Por qué falló, a partir de la última línea del error técnico.
INTERNA = "Falla interna del sistema. No se arregla desde aquí: avisa a quien administra el sistema."
CANAL = "El servicio de mensajes no respondió. Si sigue pasando, avisa a quien administra el sistema."
_INTERNAS = ("KeyError", "AttributeError", "TypeError", "ValueError", "IndexError", "NameError", "psycopg", "Undefined",
             "ProgrammingError", "AssertionError")
_CANAL = ("Timeout", "timed out", "Connection", "HTTP", "httpx", "requests", "SMTP", "502", "503", "504")


def causa(error: str | None) -> str:
    if not error:
        return "No quedó registrado por qué."
    ultima = error.strip().splitlines()[-1]
    if any(p in ultima for p in _CANAL):
        return CANAL
    if any(p in ultima for p in _INTERNAS):
        return INTERNA
    return ultima if "Traceback" not in error else INTERNA  # un motivo corto ya escrito para personas se deja tal cual


# El paciente y la cita de cada tarea, según lo que guarda en `datos`.
_PACIENTE_Y_CITA = """
with t as (select id, tipo, datos from tarea_programada where id = any(%s)),
ref as (
  select t.id,
         coalesce(c1.paciente_id, cs.paciente_id, c3.paciente_id, m.paciente_id, (t.datos->>'hogar')::bigint) as paciente_id,
         coalesce(c1.id, cs.cita_id, c3.id, case when m.entidad_tipo = 'cita' then m.entidad_id end) as cita_id
  from t
  left join cita c1 on t.tipo = 'recordatorio' and c1.id = (t.datos->>'cita_id')::bigint
  left join caso_seguimiento cs on t.tipo in ('intento_seguimiento', 'agotar_caso') and cs.id = (t.datos->>'caso_id')::bigint
  left join oferta_adelanto o on t.tipo = 'vencer_oferta' and o.id = (t.datos->>'oferta_id')::bigint
  left join cita c3 on c3.id = o.cita_id
  left join mensaje m on t.tipo in ('entregar_mensaje', 'entregar_correo') and m.id = (t.datos->>'mensaje_id')::bigint)
select ref.id, p.id as paciente_id, p.nombres || ' ' || p.apellidos as paciente, c.id as cita_id, lower(c.rango) as cita_inicio
from ref left join paciente p on p.id = ref.paciente_id left join cita c on c.id = ref.cita_id
"""


def fallidas(conn, limite: int = 50) -> list[dict]:
    """Las tareas que agotaron sus intentos, cada una con su explicación en palabras."""
    filas = conn.execute("select id, tipo, ejecutar_en, intentos, error from tarea_programada where estado='fallida' "
                         "order by ejecutar_en desc limit %s", (limite,)).fetchall()
    refs = {r["id"]: r for r in conn.execute(_PACIENTE_Y_CITA, ([f["id"] for f in filas],)).fetchall()} if filas else {}
    out = []
    for f in filas:
        uno, varias, que_hacer = QUE_ES.get(f["tipo"], _OTRA)
        r = refs.get(f["id"]) or {}
        out.append({**f, "titulo": uno, "titulo_varias": varias, "que_hacer": que_hacer, "causa": causa(f["error"]),
                    "paciente_id": r.get("paciente_id"), "paciente": r.get("paciente"),
                    "cita_id": r.get("cita_id"), "cita_inicio": r.get("cita_inicio")})
    return out


ATRASO = timedelta(minutes=15)


def atrasadas(conn) -> int:
    """Tareas que ya debieron salir hace más de 15 minutos: si hay, el proceso que envía los mensajes está detenido."""
    return conn.execute("select count(*) as n from tarea_programada where estado='pendiente' and ejecutar_en < %s",
                        (clock.now(conn) - ATRASO,)).fetchone()["n"]
