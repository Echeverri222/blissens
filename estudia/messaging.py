"""Mensajería: plantillas, envío, recepción, bitácora, horario de envío y baja."""
import json
import re
from datetime import datetime, timedelta

from . import canales, clock, config, settings, tasks

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
        from .catalog import PLANTILLAS  # un negocio creado antes de que existiera la plantilla usa la del producto
        if key not in PLANTILLAS:
            raise MessageError(f"Plantilla desconocida: {key}")
        texto, tipo, botones = PLANTILLAS[key]
        tpl = {"texto": texto, "tipo": tipo, "botones": botones}
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


def _primer(nombres: str | None) -> str:
    partes = (nombres or "").split()
    return partes[0].title() if partes else ""


def send(conn, patient_id: int, key: str, data: dict | None = None, *, direct: bool = False,
         entity: tuple[str, int] | None = None, options: list[dict] | None = None) -> int | None:
    """Envía una plantilla. `direct`: respuesta a una acción del paciente (sale siempre)."""
    p = conn.execute("select * from paciente where id=%s", (patient_id,)).fetchone()
    now = clock.now(conn)
    data = {"nombre": _primer(p["nombres"]), "direccion": config.get(conn, "direccion"), **(data or {})}
    text, tipo, opts = render(conn, key, data, options)
    estado, momento, detalle = "entregado", now, None
    from . import pacientes
    if pacientes.bloquea_mensaje(p, direct):
        estado, detalle = "omitido", "no_contactar"
    elif not direct and not p["acepta_mensajes"]:
        estado = "omitido"
    elif not pacientes.celular_usable(p):
        estado, detalle = "omitido", "celular"  # sin número que sirva no hay a quién escribirle; tampoco cuenta como intento
    elif not direct and not window_open(conn, now):
        estado, momento = "diferido", next_opening(conn, now)
    et, ei = entity or (None, None)
    row = conn.execute(
        "insert into mensaje(paciente_id, direccion, plantilla, texto, tipo, botones, entidad_tipo, entidad_id, "
        "estado_entrega, momento, canal, detalle) values (%s,'saliente',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
        (patient_id, key, text, tipo, json.dumps(opts), et, ei, estado, momento, canales.tipo_activo(conn), detalle),
    ).fetchone()
    if estado == "diferido":
        tasks.schedule(conn, "entregar_mensaje", momento, {"mensaje_id": row["id"]})
    elif estado == "entregado":
        canales.enviar_mensaje(conn, row["id"])
    return row["id"]


def lista_de_citas(conn, citas: list[dict], raiz_id: int, marcar: set[int] = frozenset()) -> str:
    """Una línea por cita para los avisos agrupados del hogar: quién, cuándo y con quién."""
    from . import familia, fmt
    lineas = []
    for c in sorted(citas, key=lambda c: (c["rango"].lower, c["id"])):  # solo citas con hora
        r = conn.execute("select p.nombres, pr.nombre as profesional from paciente p, profesional pr "
                         "where p.id=%s and pr.id=%s", (c["paciente_id"], c["profesional_id"])).fetchone()
        quien = "Usted" if c["paciente_id"] == raiz_id else (familia.primer_nombre(r) or "Su familiar")
        cuando = fmt.fecha_hora(c["rango"].lower.astimezone(clock.TZ)) if c["rango"] else fmt.fecha(c["dia"])
        lineas.append(f"• {quien}: {cuando}, con {r['profesional']}{' (sin confirmar)' if c['id'] in marcar else ''}")
    return "\n".join(lineas)


def ids_de_boton(citas: list[dict]) -> str:
    return "-".join(str(c["id"]) for c in citas)


def normalize_word(t: str) -> str:
    return re.sub(r"[^a-záéíóúñ]", "", t.strip().lower())


def receive(conn, patient_id: int, *, button_id: str | None = None, text: str | None = None,
            channel: str = "simulado", id_externo: str | None = None) -> int:
    """Procesa un mensaje entrante (respuesta de botón/lista o texto libre)."""
    from . import familia, router  # noqa: F401  (router registra rutas)

    now = clock.now(conn)
    shown = text or ""
    matched = False
    if button_id:
        # El celular es del hogar: el botón puede ser de un mensaje que se le envió a un familiar. La respuesta queda
        # registrada en quien recibió ese mensaje.
        hogar = familia.hogar(conn, patient_id)[1]
        for m in conn.execute(
            "select id, paciente_id, botones from mensaje where paciente_id = any(%s) "
            "and direccion='saliente' and estado_entrega='entregado' order by id desc limit 60",
            (hogar,),
        ):
            for b in m["botones"] or []:
                if isinstance(b, dict) and b.get("id") == button_id:
                    shown = b["title"]
                    patient_id = m["paciente_id"]
                    conn.execute("update mensaje set respuesta=%s where id=%s", (button_id, m["id"]))
                    matched = True
                    break
            else:
                continue
            break
    # Quien responde por WhatsApp tiene un celular que sirve (R8), sea cual fuera su estado.
    conn.execute("update paciente set celular_estado='valido' where id = any(%s) and celular_estado <> 'valido' "
                 "and celular is not null", (familia.hogar(conn, patient_id)[1],))
    mid = conn.execute(
        "insert into mensaje(paciente_id, direccion, canal, texto, respuesta, momento, gestionado, id_externo) "
        "values (%s,'entrante',%s,%s,%s,%s,%s,%s) returning id",
        (patient_id, channel, shown, button_id, now, matched, id_externo),
    ).fetchone()["id"]
    if button_id:
        if matched:
            prefix, *parts = button_id.split(":")
            fn = ROUTES.get(prefix)
            if fn is None or fn(conn, patient_id, parts, mid) is False:
                conn.execute("update mensaje set gestionado=false where id=%s", (mid,))
    elif normalize_word(shown) == "baja":
        # el celular es del hogar: la baja vale para todos sus miembros
        conn.execute("update paciente set acepta_mensajes=false where id = any(%s)",
                     (familia.hogar(conn, patient_id)[1],))
        conn.execute("update mensaje set gestionado=true where id=%s", (mid,))
        send(conn, patient_id, "baja_confirmada", direct=True)
    else:
        conn.execute("update mensaje set gestionado=false where id=%s", (mid,))
    return mid
