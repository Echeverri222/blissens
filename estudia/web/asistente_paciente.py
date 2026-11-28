"""El asistente en la página personal del paciente (docs/prd-asistente.md, §7). Solo se registra si hay clave de la API.

Rutas (todas bajo `/p/{token}`, y todas 404 si el negocio no encendió `asistente_pacientes`, como si no existieran):
- `GET  /asistente`: el consentimiento aparte o, aceptado, el chat.
- `POST /asistente`: un mensaje (`texto` o un botón guiado, y `conversacion`). HTMX recibe solo los globos nuevos.
- `POST /asistente/consentimiento`: `accion` = `aceptar`, `rechazar` o `retirar`.
- `POST /contacto`: pide que la clínica llame (la confirma la persona con un botón de una propuesta o el botón «Que me llamen»).

El texto del asistente es salida del modelo, o sea no confiable: va por el autoescape de Jinja como texto plano (los saltos de
línea los pone el CSS). Nunca se le aplica `linkify`, `|safe` ni Markdown.

`POST /asistente` no mantiene una conexión abierta mientras espera al modelo (D2): el enlace se resuelve con una conexión corta
que se cierra antes de llamar a `conversar`, que abre las suyas.

Este módulo importa `web.app` solo dentro de funciones: `crear_app` lo importa a él al construir la aplicación.
"""
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import clock, config
from ..asistente import Actor, consentimiento
from ..asistente import conversacion as modelo
from ..asistente.instrucciones import respuesta_fija
from .limite import LimiteVentana

router = APIRouter()

# Segunda línea de defensa: el tope de verdad (por hogar y por día) está en la base. Por IP y en memoria.
limite_asistente = LimiteVentana(maximo=30, segundos=600)

# Los botones guiados del chat: lo que se escribe en nombre de la persona.
GUIADOS = {
    "cita": "¿Cuándo es mi cita?",
    "agendar": "Quiero agendar una cita.",
    "cambiar": "Quiero cambiar una cita.",
    "cancelar": "Quiero cancelar una cita.",
}
NOTA_CONTACTO = "Pidió contacto desde el asistente"
CONTACTOS_POR_DIA = 3  # solicitudes de contacto del asistente por paciente en 24 horas


def cliente_del_modelo():
    """Dependencia que entrega el cliente de la API; `None` usa el real. Las pruebas la sustituyen con un cliente falso."""
    return None


def _conn_enlace(request: Request, token: str):
    from .app import conn_enlace
    yield from conn_enlace(request, token)


def _render(request: Request, nombre: str, status_code: int = 200, **ctx):
    from .app import render
    return render(request, nombre, status_code, **ctx)


def _paciente(conn, token: str) -> dict:
    from .app import patient_from_token
    p = patient_from_token(conn, token)
    if p["etapa"] == "prospecto":  # sin documento no hay citas que gestionar con el asistente: la clínica lo contacta
        raise HTTPException(404, "Este enlace no es válido o ya venció. Pide uno nuevo a la clínica.")
    return p


def _exigir_disponible(request: Request, conn) -> None:
    """Sin el interruptor del negocio la función no existe: el mismo 404 de una ruta inexistente."""
    if not getattr(request.app.state, "asistente", False) or not config.get(conn, "asistente_pacientes"):
        raise HTTPException(404, "Not Found")


def _hx(request: Request) -> bool:
    return bool(request.headers.get("HX-Request"))


def _estado_http(request: Request, codigo: int) -> int:
    """HTMX no cambia nada con un 4xx: un fragmento con un mensaje va con 200; el formulario sin JavaScript, con el código."""
    return 200 if _hx(request) else codigo


def _resolver(request: Request, token: str) -> tuple[dict, int, dict]:
    """El enlace con una conexión corta que se cierra al volver: (paciente, negocio_id, consentimiento)."""
    gen = _conn_enlace(request, token)
    conn = next(gen)
    try:
        p = _paciente(conn, token)
        _exigir_disponible(request, conn)
        return p, request.state.negocio_id, consentimiento.estado(conn, p)
    finally:
        gen.close()


def _entero(valor: str) -> int | None:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


# ----------------------------------------------------------------- propuestas -> tarjetas

def _tarjeta(pr: dict, token: str) -> dict | None:
    """Una propuesta de una herramienta, lista para pintar: dónde se envía y con qué campos. Lo que no cuadra se descarta."""
    try:
        tipo, par = pr["tipo"], pr.get("parametros") or {}
        resumen = str(pr.get("resumen") or "")[:300]
        base = {"tipo": tipo, "resumen": resumen, "metodo": "post", "campos": [], "alternativa": None}
        if tipo == "agendar":
            inicio = datetime.fromisoformat(par["inicio"])
            s, p_, para = int(par["servicio"]), int(par.get("profesional") or 0), int(par["para"])
            desde = inicio.astimezone(clock.TZ).strftime("%Y-%m-%dT%H:%M") if inicio.tzinfo else inicio.strftime("%Y-%m-%dT%H:%M")
            return {**base, "accion": f"/p/{token}/agendar", "boton": "Confirmar cita",
                    "campos": [("servicio", s), ("profesional", p_), ("inicio", inicio.isoformat()), ("para", para)],
                    "alternativa": f"/p/{token}/agendar?servicio={s}&profesional={p_}&para={para}&desde={desde}"}
        if tipo == "cambiar_fecha":
            cita = int(par["cita_id"])
            inicio = datetime.fromisoformat(par["inicio"])
            return {**base, "accion": f"/p/{token}/cambiar/{cita}", "boton": "Confirmar el cambio",
                    "campos": [("inicio", inicio.isoformat())], "alternativa": f"/p/{token}/cambiar/{cita}"}
        if tipo == "cancelar":  # abre la pantalla que pide el motivo: el asistente no cancela
            return {**base, "metodo": "get", "accion": f"/p/{token}/cancelar/{int(par['cita_id'])}", "boton": "Continuar para cancelar"}
        if tipo == "confirmar":
            return {**base, "accion": f"/p/{token}/confirmar/{int(par['cita_id'])}", "boton": "Confirmar asistencia"}
        if tipo == "contacto":
            return {**base, "accion": f"/p/{token}/contacto", "boton": "Que me llamen"}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return None


def _vista(mensajes: list[dict], token: str, solo_ultima: bool) -> list[dict]:
    """Los mensajes de una conversación para pintar. Al volver a abrirla solo la última respuesta conserva sus botones."""
    ultimo = max((i for i, m in enumerate(mensajes) if m["rol"] == "asistente"), default=None)
    out = []
    for i, m in enumerate(mensajes):
        props = m.get("propuestas") or []
        if solo_ultima and i != ultimo:
            props = []
        out.append({"rol": m["rol"], "texto": m["texto"], "propuestas": [t for t in (_tarjeta(x, token) for x in props) if t]})
    return out


# ----------------------------------------------------------------- páginas

def _pagina(request: Request, token: str, p: dict, fase: str, *, status_code: int = 200, mensajes=None, conversacion_id=None,
            error: str = "", aviso: str = "", consentimiento_estado: dict | None = None):
    return _render(request, "asistente.html", status_code, p=p, token=token, fase=fase, mensajes=mensajes or [],
                   conversacion_id=conversacion_id, error=error, aviso=aviso, consent=consentimiento_estado or {},
                   texto_consentimiento=consentimiento.TEXTO, guiados=GUIADOS)


@router.get("/p/{token}/asistente", response_class=HTMLResponse, include_in_schema=False)
def asistente(request: Request, token: str, c: str = "", aviso: str = "", conn=Depends(_conn_enlace)):
    p = _paciente(conn, token)
    _exigir_disponible(request, conn)
    consent = consentimiento.estado(conn, p)
    if not consent["acepta"]:
        return _pagina(request, token, p, "consentimiento", aviso=aviso, consentimiento_estado=consent)
    actor = Actor.de_paciente(request.state.negocio_id, p["id"])
    conversacion_id, mensajes = _entero(c), []
    if conversacion_id is not None:
        try:
            mensajes = _vista(modelo.leer(actor, conversacion_id)["mensajes"], token, solo_ultima=True)
        except modelo.ConversacionNoExiste:
            conversacion_id = None
    return _pagina(request, token, p, "chat", mensajes=mensajes, conversacion_id=conversacion_id, aviso=aviso,
                   consentimiento_estado=consent)


@router.post("/p/{token}/asistente", response_class=HTMLResponse, include_in_schema=False)
def mensaje(request: Request, token: str, texto: str = Form(""), guiado: str = Form(""), conversacion: str = Form(""),
            cliente=Depends(cliente_del_modelo)):
    p, negocio_id, consent = _resolver(request, token)  # ninguna conexión sigue abierta desde aquí
    if not consent["acepta"]:  # sin consentimiento no hay chat ni llamada al modelo
        raise HTTPException(403, "Primero acepta el uso del asistente.")
    actor = Actor.de_paciente(negocio_id, p["id"])
    conversacion_id = _entero(conversacion)
    pedido = GUIADOS.get(guiado) or texto
    hx = _hx(request)

    def respuesta(status_code=200, *, nuevos=None, error="", id_=conversacion_id, historial=None):
        if hx:
            return _render(request, "_asistente_turno.html", status_code, token=token, mensajes=_vista(nuevos or [], token, False),
                           conversacion_id=id_, error=error)
        return _pagina(request, token, p, "chat", status_code=status_code, conversacion_id=id_, error=error,
                       mensajes=_vista((historial or []) + (nuevos or []), token, True), consentimiento_estado=consent)

    historial = []
    if not hx and conversacion_id is not None:
        try:
            historial = modelo.leer(actor, conversacion_id)["mensajes"]
        except modelo.ConversacionNoExiste:
            conversacion_id = None
    ip = request.client.host if request.client else "?"
    usuario = {"rol": "usuario", "texto": pedido.strip(), "propuestas": []}
    if not limite_asistente.disponible(ip):
        fija = {"rol": "asistente", "texto": respuesta_fija("paciente", "limite"), "propuestas": []}
        return respuesta(_estado_http(request, 429), nuevos=[usuario, fija], historial=historial)
    limite_asistente.registrar(ip)
    try:
        r = modelo.conversar(actor, pedido, conversacion_id, cliente=cliente)
    except modelo.AsistenteApagado:
        raise HTTPException(404, "Not Found") from None
    except modelo.TextoInvalido as e:
        return respuesta(_estado_http(request, 422), error=str(e), historial=historial)
    except modelo.ConversacionNoExiste:
        return respuesta(_estado_http(request, 404), id_=None, historial=[],
                         error="Esa conversación ya no está disponible. Empieza una nueva.")
    nuevos = [usuario, {"rol": "asistente", "texto": r["respuesta"], "propuestas": r["propuestas"]}]
    return respuesta(nuevos=nuevos, id_=r["conversacion_id"], historial=historial)


@router.post("/p/{token}/asistente/consentimiento", response_class=HTMLResponse, include_in_schema=False)
def consentir(request: Request, token: str, accion: str = Form(...), conn=Depends(_conn_enlace)):
    p = _paciente(conn, token)
    _exigir_disponible(request, conn)
    if accion == "aceptar":
        consentimiento.aceptar(conn, p)  # un familiar que comparte sus citas no la da: lo decide su responsable
        return RedirectResponse(f"/p/{token}/asistente", status_code=303)
    if accion == "retirar":
        if consentimiento.retirar(conn, p):
            return RedirectResponse(f"/p/{token}?aviso=" + quote("Listo: el asistente ya no tiene tu autorización."), status_code=303)
        return RedirectResponse(f"/p/{token}/asistente", status_code=303)
    if accion == "rechazar":
        return RedirectResponse(f"/p/{token}", status_code=303)
    raise HTTPException(422, "Acción desconocida")


@router.post("/p/{token}/contacto", response_class=HTMLResponse, include_in_schema=False)
def contacto(request: Request, token: str, conn=Depends(_conn_enlace)):
    """Una solicitud para la bandeja de Contactos. No repite una que la clínica aún no atiende ni pasa de unas pocas al día."""
    p = _paciente(conn, token)
    _exigir_disponible(request, conn)
    ahora = clock.now(conn)
    abiertas = conn.execute("select count(*) n from solicitud_contacto where documento=%s and nota=%s and not gestionada",
                            (p["documento"], NOTA_CONTACTO)).fetchone()["n"]
    del_dia = conn.execute("select count(*) n from solicitud_contacto where documento=%s and nota=%s and momento > %s",
                           (p["documento"], NOTA_CONTACTO, ahora - timedelta(days=1))).fetchone()["n"]
    termino = request.state.termino
    if abiertas or del_dia >= CONTACTOS_POR_DIA:
        aviso = f"Ya le avisamos a {termino}. Te contactará pronto."
    else:
        conn.execute("insert into solicitud_contacto(documento, celular, nota, momento) values (%s,%s,%s,%s)",
                     (p["documento"], p["celular"], NOTA_CONTACTO, ahora))
        aviso = f"Listo: le avisamos a {termino} para que te contacte."
    if _hx(request):
        return _render(request, "_asistente_contacto.html", aviso=aviso)
    return RedirectResponse(f"/p/{token}?aviso=" + quote(aviso), status_code=303)
