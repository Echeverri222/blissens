"""El bucle de conversación con el modelo, igual para todos los perfiles (docs/prd-asistente.md, D2 y D3).

    conversar(actor, texto, conversacion_id=None, *, cliente=None) -> {"conversacion_id", "respuesta", "propuestas"}

Reglas que este módulo hace cumplir:
- Nunca se mantiene una conexión abierta mientras se espera al modelo (D2): antes de llamarlo se abre una conexión corta para
  comprobar límites y leer el historial, y se cierra; al terminar se abre otra para guardar. Cada herramienta abre la suya.
- Un mensaje se guarda completo o no se guarda (D3): un rechazo, un corte por `max_tokens`, un error de la API o pasar de 45 s
  devuelven la respuesta fija y no dejan ni medio turno. Sí dejan una fila `fallo` sin contenido, con los tokens gastados: un
  intento fallido cuenta para el tope diario y el presupuesto, o provocar fallos sería una forma de gastar sin límite.
- Una conversación es de quien la escribió. El tope diario de un paciente es de su hogar, pero un familiar no lee las
  conversaciones de su responsable ni al revés.
- Cada turno del asistente se guarda como la lista de bloques que devolvió el modelo y se reenvía sin tocarla.
- Los límites se cuentan en la base: los mensajes y los tokens de hoy salen de `asistente_mensaje`.
- Nunca se escribe el texto de las personas en el registro: solo perfil, nombres de herramientas, tokens y duración.
"""
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as hora

from .. import clock, config, db, familia, fmt, logs, settings
from .actor import Actor
from .catalogo import definiciones_api
from .despachador import ejecutar
from .instrucciones import INSTRUCCIONES, contexto, respuesta_fija

TIEMPO_MAXIMO_S = 45.0  # lo que puede tardar un mensaje completo, con todas sus llamadas al modelo y a las herramientas
BETA_FALLBACKS = "server-side-fallback-2026-07-01"
# Modelos con reserva del lado del servidor ante un rechazo del clasificador de seguridad (skill claude-api).
CON_RESERVA = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-fable-5-2"})


@dataclass(frozen=True)
class Ajustes:
    """Todo lo que cambia de un perfil a otro, en un solo lugar."""
    herramientas_por_mensaje: int
    largo_mensaje: int
    mensajes_por_conversacion: int | None
    clave_dia: str            # clave de `config` con el tope diario de mensajes
    max_tokens: int           # con margen: el razonamiento también gasta de aquí; la brevedad de la respuesta la pide el texto
    esfuerzo: str             # `output_config.effort`
    modelo: Callable[[], str]


AJUSTES = {
    "auxiliar": Ajustes(8, 1000, None, "asistente_mensajes_dia_usuario", 4096, "medium", lambda: settings.ASISTENTE_MODELO),
    "especialista": Ajustes(8, 1000, None, "asistente_mensajes_dia_usuario", 4096, "medium", lambda: settings.ASISTENTE_MODELO),
    "paciente": Ajustes(4, 300, 12, "asistente_mensajes_dia_paciente", 2048, "low", lambda: settings.ASISTENTE_MODELO_PACIENTE),
}
INTERRUPTOR = {"auxiliar": "asistente_equipo", "especialista": "asistente_equipo", "paciente": "asistente_pacientes"}


class AsistenteApagado(Exception):
    """Sin clave de la API o con el interruptor del negocio apagado."""


class ConversacionNoExiste(Exception):
    """El id no existe o es de otra persona u otro negocio (se comportan igual)."""


class TextoInvalido(Exception):
    pass


class _Fallo(Exception):
    """Algo impidió responder: el motivo es solo para el registro (nunca lleva texto de personas)."""


def _ajustes(actor: Actor) -> Ajustes:
    if actor.perfil not in AJUSTES:
        raise ValueError(f"El perfil {actor.perfil} no conversa con el modelo")
    return AJUSTES[actor.perfil]


def _conexion(actor: Actor):
    return db.connect(negocio=actor.negocio_id, usuario_id=actor.usuario_id)


def _hogar(conn, actor: Actor) -> list[int] | None:
    """Los pacientes del hogar de quien escribe: el tope diario es del hogar (comparten un celular)."""
    return familia.hogar(conn, actor.paciente_id)[1] if actor.perfil == "paciente" else None


def _dueno(actor: Actor) -> tuple[str, int]:
    """Una conversación es de quien la escribió: ni el responsable lee las de su familiar ni el familiar las suyas."""
    return ("c.paciente_id=%s", actor.paciente_id) if actor.perfil == "paciente" else ("c.usuario_id=%s", actor.usuario_id)


def _inicio_del_dia(conn) -> datetime:
    ahora = clock.now(conn)
    return datetime.combine(ahora.date(), hora.min, tzinfo=ahora.tzinfo)


# Lo que cuenta para el tope diario: cada mensaje de la persona (los demás turnos 'user' son resultados de herramientas) y cada
# intento fallido.
CUENTA_HOY = "((m.rol='user' and m.contenido->0->>'type'='text') or m.rol='fallo')"


def _mensajes_hoy(conn, actor: Actor, hogar: list[int] | None) -> int:
    cond, valor = ("c.paciente_id = any(%s)", hogar) if actor.perfil == "paciente" else ("c.usuario_id=%s", actor.usuario_id)
    return conn.execute(
        f"select count(*) n from asistente_mensaje m join asistente_conversacion c on c.id=m.conversacion_id "
        f"where {cond} and {CUENTA_HOY} and m.creado_en >= %s", (valor, _inicio_del_dia(conn))).fetchone()["n"]


def _tokens_hoy(conn) -> int:
    return conn.execute("select coalesce(sum(tokens_entrada + tokens_salida), 0)::bigint n from asistente_mensaje where creado_en >= %s",
                        (_inicio_del_dia(conn),)).fetchone()["n"]


def _encendido(conn, actor: Actor) -> bool:
    return settings.asistente_configurado() and bool(config.get(conn, INTERRUPTOR[actor.perfil]))


def estado(actor: Actor) -> dict:
    """`{disponible, perfil, mensajes_restantes}`. Abre y cierra su propia conexión."""
    aj = _ajustes(actor)
    conn = _conexion(actor)
    try:
        tope = int(config.get(conn, aj.clave_dia))
        return {"disponible": _encendido(conn, actor), "perfil": actor.perfil,
                "mensajes_restantes": max(0, tope - _mensajes_hoy(conn, actor, _hogar(conn, actor)))}
    finally:
        conn.close()


# ----------------------------------------------------------------- lectura y escritura de turnos

def _turnos(conn, actor: Actor, conversacion_id: int) -> list[dict]:
    cond, valor = _dueno(actor)
    c = conn.execute(f"select c.id from asistente_conversacion c where c.id=%s and c.perfil=%s and {cond}",
                     (conversacion_id, actor.perfil, valor)).fetchone()
    if c is None:
        raise ConversacionNoExiste()
    return conn.execute("select rol, contenido, creado_en from asistente_mensaje where conversacion_id=%s and rol <> 'fallo' order by id",
                        (conversacion_id,)).fetchall()


def _guardar(actor: Actor, conversacion_id: int | None, turnos: list[tuple]) -> int:
    conn = _conexion(actor)
    try:
        ahora = clock.now(conn)
        if conversacion_id is None:
            conversacion_id = conn.execute(
                "insert into asistente_conversacion(perfil, usuario_id, paciente_id, creada_en, ultima_en) values (%s,%s,%s,%s,%s) "
                "returning id", (actor.perfil, actor.usuario_id, actor.paciente_id, ahora, ahora)).fetchone()["id"]
        else:
            conn.execute("update asistente_conversacion set ultima_en=%s where id=%s", (ahora, conversacion_id))
        for rol, contenido, entrada, salida in turnos:
            conn.execute("insert into asistente_mensaje(conversacion_id, rol, contenido, tokens_entrada, tokens_salida, creado_en) "
                         "values (%s,%s,%s,%s,%s,%s)", (conversacion_id, rol, json.dumps(contenido, ensure_ascii=False),
                                                         entrada, salida, ahora))
        conn.commit()
        return conversacion_id
    finally:
        conn.close()


def _anotar_fallo(actor: Actor, conversacion_id: int | None, tokens_entrada: int, tokens_salida: int) -> None:
    """Un intento fallido no deja turno, pero cuenta: una fila `fallo` sin contenido con los tokens que gastó. Sin conversación
    previa abre una que solo lleva esa fila (nadie recibe su id). Si ni esto se puede guardar, la respuesta fija sale igual."""
    try:
        _guardar(actor, conversacion_id, [("fallo", [], tokens_entrada, tokens_salida)])
    except Exception as e:
        logs.evento(evento="asistente", perfil=actor.perfil, negocio=actor.negocio_id, resultado=f"fallo_sin_anotar:{type(e).__name__}")


def _propuestas_de(contenido: list[dict]) -> list[dict]:
    """Las propuestas que devolvieron las herramientas en un turno de resultados."""
    out = []
    for b in contenido:
        if b.get("type") == "tool_result" and isinstance(b.get("content"), str):
            try:
                r = json.loads(b["content"])
            except ValueError:
                continue
            if isinstance(r, dict) and isinstance(r.get("propuesta"), dict):
                out.append(r["propuesta"])
    return out


def _texto_de(contenido: list[dict]) -> str:
    return "".join(b["text"] for b in contenido if b.get("type") == "text").strip()


def leer(actor: Actor, conversacion_id: int) -> dict:
    """Una conversación propia para mostrarla de nuevo: cada turno con su texto y, en la respuesta, sus propuestas.

    `ConversacionNoExiste` si el id no existe o no es de este actor (da igual cuál de los dos).
    """
    _ajustes(actor)
    conn = _conexion(actor)
    try:
        filas = _turnos(conn, actor, conversacion_id)
    finally:
        conn.close()
    mensajes, pendientes = [], []
    for f in filas:
        c = f["contenido"]
        if f["rol"] == "user":
            if c and c[0].get("type") == "text":
                mensajes.append({"rol": "usuario", "texto": _texto_de(c[-1:]), "propuestas": []})
                pendientes = []
            else:
                pendientes += _propuestas_de(c)
        else:
            texto = _texto_de(c)
            if texto:
                mensajes.append({"rol": "asistente", "texto": texto, "propuestas": pendientes})
                pendientes = []
    return {"conversacion_id": conversacion_id, "mensajes": mensajes}


# ----------------------------------------------------------------- el modelo

def _bloque(b) -> dict:
    return b.model_dump(mode="json", by_alias=True, exclude_none=True)


def _reenviable(contenido: list[dict]) -> list[dict]:
    """Tras una reserva en mitad de la respuesta, el modelo no recibe de vuelta lo que vino antes del bloque `fallback`
    (razonamiento ni llamadas a herramientas); el bloque se queda donde estaba. Sin reserva, el turno va tal cual."""
    marca = max((i for i, b in enumerate(contenido) if b.get("type") == "fallback"), default=None)
    if marca is None:
        return contenido
    return [b for i, b in enumerate(contenido) if i > marca or b.get("type") not in ("thinking", "redacted_thinking", "tool_use")]


def cliente_de_la_api():
    """El cliente real de la API (una sola instancia). Las pruebas pasan uno falso a `conversar`."""
    global _CLIENTE
    llave = (settings.ASISTENTE_PROVEEDOR, settings.AWS_REGION if settings.en_bedrock() else settings.ANTHROPIC_API_KEY)
    if _CLIENTE is None or _CLIENTE[0] != llave:
        import anthropic
        if settings.en_bedrock():  # credenciales de AWS por la cadena de siempre (o AWS_BEARER_TOKEN_BEDROCK)
            cliente = anthropic.AnthropicBedrockMantle(aws_region=settings.AWS_REGION, max_retries=1)
        else:
            cliente = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=1)
        _CLIENTE = (llave, cliente)
    return _CLIENTE[1]


def id_del_modelo(modelo: str) -> str:
    """El id que entiende el proveedor: en Bedrock los modelos de Claude llevan el prefijo `anthropic.`."""
    if settings.en_bedrock() and not modelo.startswith("anthropic."):
        return f"anthropic.{modelo}"
    return modelo


_CLIENTE = None


def _peticion(actor: Actor, aj: Ajustes, mensajes: list[dict]) -> dict:
    """La petición a `client.beta.messages.create`. El sistema y las herramientas son fijos por perfil, así que se cachean:
    `cache_control` en la raíz marca el último bloque cacheable (el historial crece sin cambiar lo anterior)."""
    modelo = aj.modelo()
    p = {"model": id_del_modelo(modelo), "max_tokens": aj.max_tokens, "system": INSTRUCCIONES[actor.perfil],
         "tools": definiciones_api(actor.perfil), "messages": mensajes, "cache_control": {"type": "ephemeral"},
         "output_config": {"effort": aj.esfuerzo}}
    # El razonamiento siempre va activo en estos modelos (se omite `thinking`); no se envían `temperature`, `tool_choice` forzado
    # ni un turno del asistente al final (prefill): los rechazan.
    if modelo in CON_RESERVA and not settings.en_bedrock():  # Bedrock no tiene la reserva del servidor (`fallbacks`)
        p.update(betas=[BETA_FALLBACKS], fallbacks="default")
    return p


def _llamar(ejecutor: ThreadPoolExecutor, cliente, limite: float, peticion: dict):
    restante = limite - time.monotonic()
    if restante <= 0:
        raise _Fallo("tiempo")
    futuro = ejecutor.submit(lambda: cliente.beta.messages.create(**peticion, timeout=restante))
    try:
        return futuro.result(timeout=restante)
    except TimeoutError:
        raise _Fallo("tiempo") from None
    except Exception as e:
        raise _Fallo(f"api:{type(e).__name__}") from None


def _contexto(conn, actor: Actor) -> str:
    negocio = conn.execute("select nombre from negocio where id=%s", (actor.negocio_id,)).fetchone()["nombre"]
    if actor.perfil == "paciente":
        persona = familia.primer_nombre(conn.execute("select nombres from paciente where id=%s", (actor.paciente_id,)).fetchone())
    else:
        persona = familia.primer_nombre(actor.usuario.get("nombre"))
    ahora = clock.now(conn)
    return contexto(negocio, persona, f"{fmt.DIAS[ahora.weekday()]} {ahora:%Y-%m-%d %H:%M} (hora del negocio)")


# Lo que viaja ya consultado con cada mensaje, en <precargado>: responde lo más común ("¿quién sigue?", "¿a qué hora es mi
# cita?", "¿dónde quedan?") sin una vuelta más al modelo. Pasa por el despachador (permisos, alcance y auditoría de siempre).
# Va solo en el mensaje actual: el historial guarda el turno sin él, así una conversación larga no repite fotos viejas del día.
def _precarga_de(perfil: str, hoy: date) -> list[tuple[str, dict]]:
    return {
        "auxiliar": [("resumen_dia", {}), ("agenda", {"desde": hoy.isoformat(), "hasta": hoy.isoformat()}),
                     ("datos_del_negocio", {}), ("servicios", {}), ("motivos_cancelacion", {})],
        "especialista": [("mi_dia", {}), ("datos_del_negocio", {})],
        "paciente": [("mis_citas", {}), ("servicios", {}), ("datos_del_negocio", {})],
    }.get(perfil, [])


def herramientas_precargadas(perfil: str) -> list[str]:
    """Los nombres de lo que viaja en <precargado> para ese perfil (`agenda`, solo la de hoy)."""
    return [n for n, _ in _precarga_de(perfil, date.today())]


def precarga(actor: Actor, hoy: date, *, conexion=None, vistos: list | None = None) -> str:
    """El bloque <precargado> del mensaje actual; vacío si el perfil no tiene o todo falló. Con `vistos`, deja ahí cada salida
    (de ahí salen los enlaces a pacientes de la respuesta)."""
    partes = []
    for nombre, args in _precarga_de(actor.perfil, hoy):
        salida = ejecutar(actor, nombre, args, conexion=conexion)
        if "error" in salida:
            continue  # sin ese dato el modelo llama la herramienta si la necesita
        if vistos is not None:
            vistos.append(salida)
        etiqueta = f"{nombre} (hoy)" if nombre == "agenda" else nombre
        partes.append(f"{etiqueta}: {json.dumps(salida, ensure_ascii=False, separators=(',', ':'), default=str)}")
    if not partes:
        return ""
    return "<precargado>\n" + "\n".join(partes) + "\n</precargado>"


def _respuesta(actor: Actor, motivo: str, conversacion_id: int | None) -> dict:
    return {"conversacion_id": conversacion_id, "respuesta": respuesta_fija(actor.perfil, motivo), "propuestas": []}


def _pacientes_en(x, out: dict[str, int]) -> None:
    """Junta `nombre completo -> paciente_id` de lo que devolvieron las herramientas (filas con `paciente_id` y su nombre, un
    `paciente: {id, nombre}` o una lista `pacientes` de `{id, nombre}`)."""
    if isinstance(x, list):
        for v in x:
            _pacientes_en(v, out)
    elif isinstance(x, dict):
        pid, nombre = x.get("paciente_id"), x.get("paciente")
        if not isinstance(nombre, str) and x.get("nombres") and x.get("apellidos"):
            nombre = f"{x['nombres']} {x['apellidos']}"
        if isinstance(pid, int) and isinstance(nombre, str):
            out.setdefault(nombre, pid)
        for k, v in x.items():
            if k in ("paciente", "pacientes") and isinstance(v, (dict, list)):
                for q in (v if isinstance(v, list) else [v]):
                    if isinstance(q, dict) and isinstance(q.get("id"), int) and isinstance(q.get("nombre"), str):
                        out.setdefault(q["nombre"], q["id"])
            if isinstance(v, (dict, list)):
                _pacientes_en(v, out)


def enlaces(perfil: str, respuesta: str, vistos: list) -> list[dict]:
    """Los nombres de pacientes que la respuesta menciona tal cual, con la ruta a su ficha en el panel. Sale de los datos que
    ya leyó el asistente: no cuesta tokens. Solo para recepción (el paciente no navega fichas)."""
    if perfil != "auxiliar":
        return []
    nombres: dict[str, int] = {}
    _pacientes_en(vistos, nombres)
    return [{"texto": n, "ruta": f"/pacientes/{pid}"} for n, pid in sorted(nombres.items(), key=lambda t: -len(t[0]))
            if len(n) > 3 and n in respuesta]


def conversar(actor: Actor, texto: str, conversacion_id: int | None = None, *, cliente=None) -> dict:
    """Un mensaje de la persona y la respuesta del asistente. Devuelve `{conversacion_id, respuesta, propuestas}`.

    - Lanza `AsistenteApagado` (interruptor del negocio apagado o sin clave), `TextoInvalido` (vacío o demasiado largo) y
      `ConversacionNoExiste`.
    - Un tope diario, el de la conversación o el presupuesto de tokens, un rechazo, un corte por `max_tokens`, un error de la API,
      demasiadas herramientas o pasar de `TIEMPO_MAXIMO_S` NO lanzan nada: devuelven la respuesta fija del perfil, con
      `propuestas` vacío, y no guardan ningún turno (un fallo del modelo deja solo su fila `fallo`, que cuenta para los topes).
      `conversacion_id` es el recibido (puede ser None).
    - `cliente`: algo con `.beta.messages.create(**kwargs)`; sin él se usa el cliente real de la API.
    """
    aj = _ajustes(actor)
    texto = (texto or "").strip()
    if not texto or len(texto) > aj.largo_mensaje:
        raise TextoInvalido(f"El mensaje debe tener entre 1 y {aj.largo_mensaje} caracteres.")
    if cliente is None and not settings.asistente_configurado():
        raise AsistenteApagado()
    inicio = time.monotonic()
    limite = inicio + TIEMPO_MAXIMO_S

    # 1. Conexión corta: interruptor, límites, historial y contexto. Se cierra antes de llamar al modelo.
    conn = _conexion(actor)
    try:
        if not config.get(conn, INTERRUPTOR[actor.perfil]):
            raise AsistenteApagado()
        hogar = _hogar(conn, actor)
        historial = [{"role": f["rol"], "content": _reenviable(f["contenido"]) if f["rol"] == "assistant" else f["contenido"]}
                     for f in (_turnos(conn, actor, conversacion_id) if conversacion_id is not None else [])]
        if _tokens_hoy(conn) >= int(config.get(conn, "asistente_tokens_dia")):
            return _respuesta(actor, "no_disponible", conversacion_id)
        if _mensajes_hoy(conn, actor, hogar) >= int(config.get(conn, aj.clave_dia)):
            return _respuesta(actor, "limite", conversacion_id)
        if aj.mensajes_por_conversacion is not None and conversacion_id is not None:
            humanos = sum(1 for f in historial if f["role"] == "user" and f["content"][0].get("type") == "text")
            if humanos >= aj.mensajes_por_conversacion:
                return _respuesta(actor, "limite", conversacion_id)
        marco = _contexto(conn, actor)
        hoy = clock.now(conn).date()
    finally:
        conn.close()

    # 2. El bucle, sin conexión abierta.
    cliente = cliente or cliente_de_la_api()
    entrada = [{"type": "text", "text": marco}, {"type": "text", "text": texto}]
    vistos: list = []
    precargado = precarga(actor, hoy, vistos=vistos)
    envio = [entrada[0], {"type": "text", "text": precargado}, entrada[1]] if precargado else entrada
    mensajes = historial + [{"role": "user", "content": envio}]
    nuevos: list[tuple] = [("user", entrada, 0, 0)]
    propuestas: list[dict] = []
    usadas: list[str] = []
    tokens_entrada = tokens_salida = 0
    cache = {"cache_leidos": 0, "cache_escritos": 0}
    ejecutor = ThreadPoolExecutor(max_workers=1)
    try:
        try:
            while True:
                r = _llamar(ejecutor, cliente, limite, _peticion(actor, aj, mensajes))
                u = r.usage
                entrada_r = ((getattr(u, "input_tokens", 0) or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
                             + (getattr(u, "cache_read_input_tokens", 0) or 0))
                salida_r = getattr(u, "output_tokens", 0) or 0
                tokens_entrada, tokens_salida = tokens_entrada + entrada_r, tokens_salida + salida_r
                cache["cache_leidos"] += getattr(u, "cache_read_input_tokens", 0) or 0
                cache["cache_escritos"] += getattr(u, "cache_creation_input_tokens", 0) or 0
                if r.stop_reason not in ("end_turn", "stop_sequence", "tool_use"):
                    raise _Fallo(f"parada:{r.stop_reason}")  # refusal, max_tokens y cualquier otra
                contenido = [_bloque(b) for b in r.content]
                reenvio = _reenviable(contenido)
                nuevos.append(("assistant", contenido, entrada_r, salida_r))
                mensajes.append({"role": "assistant", "content": reenvio})
                if r.stop_reason != "tool_use":
                    respuesta = _texto_de(contenido)
                    if not respuesta:
                        raise _Fallo("sin_texto")
                    break
                llamadas = [b for b in reenvio if b.get("type") == "tool_use"]
                if len(usadas) + len(llamadas) > aj.herramientas_por_mensaje:
                    raise _Fallo("herramientas")
                resultados = []
                for b in llamadas:
                    if time.monotonic() >= limite:
                        raise _Fallo("tiempo")
                    usadas.append(b["name"])
                    salida = ejecutar(actor, b["name"], b.get("input") if isinstance(b.get("input"), dict) else {})
                    vistos.append(salida)
                    resultados.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(salida, ensure_ascii=False),
                                       **({"is_error": True} if "error" in salida else {})})
                nuevos.append(("user", resultados, 0, 0))
                mensajes.append({"role": "user", "content": resultados})
                propuestas += _propuestas_de(resultados)
            id_guardado = _guardar(actor, conversacion_id, nuevos)
        except _Fallo as f:
            _anotar_fallo(actor, conversacion_id, tokens_entrada, tokens_salida)
            return _terminar(actor, usadas, tokens_entrada, tokens_salida, inicio, f"fallo:{f}", _respuesta(actor, "fallo", conversacion_id),
                             cache)
        except Exception as e:  # no se pudo guardar, o una falla inesperada: tampoco se guarda medio turno
            _anotar_fallo(actor, conversacion_id, tokens_entrada, tokens_salida)
            return _terminar(actor, usadas, tokens_entrada, tokens_salida, inicio, f"error:{type(e).__name__}",
                             _respuesta(actor, "fallo", conversacion_id), cache)
    finally:
        ejecutor.shutdown(wait=False, cancel_futures=True)
    return _terminar(actor, usadas, tokens_entrada, tokens_salida, inicio, "ok",
                     {"conversacion_id": id_guardado, "respuesta": respuesta, "propuestas": propuestas,
                      "enlaces": enlaces(actor.perfil, respuesta, vistos)}, cache)


def _terminar(actor: Actor, usadas, tokens_entrada, tokens_salida, inicio, resultado, salida: dict, cache: dict | None = None) -> dict:
    """Deja una línea en el registro (sin ningún texto de personas) y devuelve la salida. `tokens_entrada` incluye lo leído y
    lo escrito en el caché, que aparecen aparte: el caché cambia mucho lo que cuesta el mensaje."""
    logs.evento(evento="asistente", perfil=actor.perfil, negocio=actor.negocio_id, herramientas=usadas,
                tokens_entrada=tokens_entrada, **(cache or {}), tokens_salida=tokens_salida, resultado=resultado,
                ms=round((time.monotonic() - inicio) * 1000, 1))
    return salida
