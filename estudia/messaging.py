"""Mensajería: plantillas, envío, recepción, bitácora, horario de envío y baja."""
import json
import re
from datetime import datetime, timedelta

from . import clock, config, settings, tasks

MAX_BUTTONS, MAX_BUTTON_TITLE = 3, 20
MAX_LIST_OPTIONS, MAX_LIST_TITLE = 10, 24

ROUTES: dict = {}  # prefijo de id de botón -> función(conn, paciente_id, partes, mensaje_id)


def route(prefix: str):
    def deco(fn):
        ROUTES[prefix] = fn
        return fn
    return deco


class MessageError(ValueError):
    pass


def validate(tipo: str, options: list[dict]) -> None:
    if tipo == "botones":
        if len(options) > MAX_BUTTONS:
            raise MessageError("Máximo 3 botones de respuesta")
        if any(len(o["title"]) > MAX_BUTTON_TITLE for o in options):
            raise MessageError("Título de botón de más de 20 caracteres")
    else:
        if len(options) > MAX_LIST_OPTIONS:
            raise MessageError("Máximo 10 opciones en una lista")
        if any(len(o["title"]) > MAX_LIST_TITLE for o in options):
            raise MessageError("Título de lista de más de 24 caracteres")


def patient_link(conn, patient_id: int, path: str = "") -> str:
    from .links import make_token
    return f"{settings.BASE_URL}/p/{make_token(patient_id, conn=conn)}{path}"


def render(conn, key: str, data: dict, options: list[dict] | None = None):
    tpl = conn.execute("select * from plantilla where clave=%s", (key,)).fetchone()
    if tpl is None:
        raise MessageError(f"Plantilla desconocida: {key}")
    text = tpl["texto"].format(**data)
    if options is None:
        options = [{"id": b["id"].format(**data), "title": b["title"]} for b in tpl["botones"]]
    validate(tpl["tipo"], options)
    return text, tpl["tipo"], options


def window_open(conn, now: datetime) -> bool:
    a, b = config.get(conn, "ventana_envio")
    return config.parse_hhmm(a) <= now.timetz().replace(tzinfo=None) < config.parse_hhmm(b)


def next_opening(conn, now: datetime) -> datetime:
    a, _ = config.get(conn, "ventana_envio")
    t = config.parse_hhmm(a)
    opening = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    return opening if opening > now else opening + timedelta(days=1)


def send(conn, patient_id: int, key: str, data: dict | None = None, *, direct: bool = False,
         entity: tuple[str, int] | None = None, options: list[dict] | None = None) -> int | None:
    """Envía una plantilla. `direct`: respuesta a una acción del paciente (sale siempre)."""
    p = conn.execute("select * from paciente where id=%s", (patient_id,)).fetchone()
    now = clock.now(conn)
    data = {"nombre": p["nombres"].split()[0].title(), "direccion": config.get(conn, "direccion"), **(data or {})}
    text, tipo, opts = render(conn, key, data, options)
    estado, momento = "entregado", now
    if not direct and not p["acepta_mensajes"]:
        estado = "omitido"
    elif not direct and not window_open(conn, now):
        estado, momento = "diferido", next_opening(conn, now)
    et, ei = entity or (None, None)
    row = conn.execute(
        "insert into mensaje(paciente_id, direccion, plantilla, texto, tipo, botones, entidad_tipo, entidad_id, "
        "estado_entrega, momento) values (%s,'saliente',%s,%s,%s,%s,%s,%s,%s,%s) returning id",
        (patient_id, key, text, tipo, json.dumps(opts), et, ei, estado, momento),
    ).fetchone()
    if estado == "diferido":
        tasks.schedule(conn, "entregar_mensaje", momento, {"mensaje_id": row["id"]})
    return row["id"]


def normalize_word(t: str) -> str:
    return re.sub(r"[^a-záéíóúñ]", "", t.strip().lower())


def receive(conn, patient_id: int, *, button_id: str | None = None, text: str | None = None,
            channel: str = "simulado") -> int:
    """Procesa un mensaje entrante (respuesta de botón/lista o texto libre)."""
    from . import router  # noqa: F401  (registra rutas)

    now = clock.now(conn)
    shown = text or ""
    if button_id:
        for m in conn.execute("select id, botones from mensaje where paciente_id=%s and direccion='saliente' "
                              "order by id desc limit 60", (patient_id,)):
            for b in m["botones"]:
                if b["id"] == button_id:
                    shown = b["title"]
                    conn.execute("update mensaje set respuesta=%s where id=%s", (button_id, m["id"]))
                    break
            else:
                continue
            break
    mid = conn.execute(
        "insert into mensaje(paciente_id, direccion, canal, texto, respuesta, momento, gestionado) "
        "values (%s,'entrante',%s,%s,%s,%s,%s) returning id",
        (patient_id, channel, shown, button_id, now, button_id is not None),
    ).fetchone()["id"]
    if button_id:
        prefix, *parts = button_id.split(":")
        fn = ROUTES.get(prefix)
        if fn is None:
            conn.execute("update mensaje set gestionado=false where id=%s", (mid,))
        else:
            fn(conn, patient_id, parts, mid)
    elif normalize_word(shown) == "baja":
        conn.execute("update paciente set acepta_mensajes=false where id=%s", (patient_id,))
        conn.execute("update mensaje set gestionado=true where id=%s", (mid,))
        send(conn, patient_id, "baja_confirmada", direct=True)
    else:
        conn.execute("update mensaje set gestionado=false where id=%s", (mid,))
    return mid
