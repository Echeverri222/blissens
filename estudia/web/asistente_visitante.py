"""El asistente del sitio público (docs/prd-asistente.md, §7b). Solo se registra si hay clave de la API.

Dos capas. La primera NO llama al modelo y existe aunque el asistente esté apagado: un cuadro con cuatro botones cuyas respuestas
salen del texto fijo (`copia.py`) y de los formularios de siempre. Esta capa es el `GET /sitio/asistente/paso/{clave}` (router `pasos`, siempre registrado).
La segunda es el asistente de IA, perfil `visitante`, detrás de «Otra pregunta»:

- `POST /sitio/asistente`: un mensaje (`texto`, `conversacion`, `idioma`). HTMX recibe solo los globos nuevos. 404 si el negocio
  no encendió `asistente_visitantes`, como si no existiera.

El visitante es anónimo: su id es un valor al azar en una cookie firmada (httpOnly, SameSite=Lax) que pone el servidor. El
modelo nunca lo elige y nunca recibe ni pide documento, celular o correo: eso va solo en los formularios de las tarjetas.

El texto del asistente es salida del modelo, o sea no confiable: va por el autoescape de Jinja como texto plano. Nunca se le
aplica `linkify`, `|safe` ni Markdown. Las tarjetas las arma el servidor desde propuestas validadas, nunca desde texto del modelo.

Este módulo importa `web.app` solo dentro de funciones: `crear_app` lo importa a él al construir la aplicación.
"""
import re
import secrets
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import config, links
from ..asistente import Actor
from ..asistente import conversacion as modelo
from ..asistente.instrucciones import respuesta_fija
from . import copia
from .limite import LimiteVentana

router = APIRouter()  # el asistente de IA: solo se registra con la clave de la API
pasos = APIRouter()   # los botones sin modelo: existen siempre, aunque el asistente esté apagado o sin clave

# Segunda línea de defensa: el tope de verdad (por visitante y día, y el presupuesto de tokens) está en la base. Por IP y en memoria.
limite_visitantes = LimiteVentana(maximo=30, segundos=600)

PASOS = ("inicio", "agendar", "afuera", "direccion", "otra")
# Dónde lleva cada opción sin JavaScript (secciones de la landing).
ANCLAS = {"agendar": "agendar", "afuera": "evaluacion", "direccion": "contacto", "otra": "contacto"}


def cliente_del_modelo():
    """Dependencia que entrega el cliente de la API; `None` usa el real. Las pruebas la sustituyen con un cliente falso."""
    return None


def _app():
    from . import app
    return app


@contextmanager
def _conexion_corta(request: Request):
    """El negocio por defecto con una conexión corta que se cierra al salir: ninguna sigue abierta mientras espera al modelo."""
    gen = _app().conn_publica(request)
    conn = next(gen)
    try:
        yield conn
    finally:
        gen.close()


def _idioma(idioma: str) -> str:
    return idioma if idioma in copia.COPIA else "es"


def _disponible(request: Request, conn) -> bool:
    """¿El cuadro de texto del asistente de IA existe? Con la clave de la API y el interruptor del negocio."""
    return bool(getattr(request.app.state, "asistente", False)) and bool(config.get(conn, "asistente_visitantes"))


def _poner_cookie(request: Request, response, visitante: str) -> None:
    response.set_cookie(links.COOKIE_VISITANTE, links.firmar_visitante(visitante), max_age=links.VIGENCIA_VISITANTE_DIAS * 86400,
                        httponly=True, samesite="lax", secure=request.app.state.entorno != "local", path="/")


def _visitante(request: Request) -> tuple[str, bool]:
    """(id, es_nuevo): el de la cookie firmada o, si falta o no sirve, uno nuevo."""
    actual = links.leer_visitante(request.cookies.get(links.COOKIE_VISITANTE))
    return (actual, False) if actual else (links.nuevo_visitante(), True)


def _hx(request: Request) -> bool:
    return bool(request.headers.get("HX-Request"))


# ----------------------------------------------------------------- capa 1: botones sin modelo

@pasos.get("/sitio/asistente/paso/{clave}", response_class=HTMLResponse, include_in_schema=False)
def paso(request: Request, clave: str, idioma: str = "es"):
    """Un paso de los botones: un fragmento que reemplaza el cuerpo del cuadro. Sin HTMX redirige a la sección de la landing."""
    if clave not in PASOS:
        raise HTTPException(404, "Not Found")
    lang = _idioma(idioma)
    t = copia.COPIA[lang]
    if not _hx(request):
        return RedirectResponse(t["home"] + (f"#{ANCLAS[clave]}" if clave in ANCLAS else ""), status_code=303)
    render = _app().render
    if clave == "inicio":
        return render(request, "_asistente_inicio.html", lang=lang)
    if clave != "otra":
        return render(request, "_asistente_paso.html", lang=lang, paso=clave, chat=False)
    with _conexion_corta(request) as conn:  # solo «Otra pregunta» mira si el asistente de IA está disponible
        chat = _disponible(request, conn)
    respuesta = render(request, "_asistente_paso.html", lang=lang, paso=clave, chat=chat)
    if chat:
        visitante, nuevo = _visitante(request)
        if nuevo:
            _poner_cookie(request, respuesta, visitante)
    return respuesta


# ----------------------------------------------------------------- capa 2: el asistente de IA

def _tarjeta(pr: dict, lang: str) -> dict | None:
    """Una propuesta de una herramienta, lista para pintar. Lo que no cuadra se descarta."""
    t = copia.COPIA[lang]
    try:
        tipo, par = pr["tipo"], pr.get("parametros") or {}
        uid = "c" + secrets.token_hex(3)  # ids propios: el formulario puede aparecer varias veces en la conversación
        if tipo == "registro":
            pre = {"servicio": int(par.get("servicio") or 0), "profesional": int(par.get("profesional") or 0),
                   "desde": str(par.get("desde") or "")}
            if pre["desde"] and not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d", pre["desde"]):
                return None
            return {"tipo": tipo, "uid": uid, "titulo": t["agendar"]["paso1"], "pre": {k: v for k, v in pre.items() if v}}
        if tipo == "solicitud" and par.get("interes") in copia.INTERESES:
            interes = par["interes"]
            titulo = {"evaluacion_virtual": t["evaluacion"]["form_titulo"], "experiencia": t["experiencias"]["form_titulo"],
                      "contacto": t["contacto"]["titulo"]}[interes]
            return {"tipo": tipo, "uid": uid, "titulo": titulo, "interes": interes}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return None


@router.post("/sitio/asistente", response_class=HTMLResponse, include_in_schema=False)
def mensaje(request: Request, texto: str = Form(""), conversacion: str = Form(""), idioma: str = Form("es"), web: str = Form(""),
            cliente=Depends(cliente_del_modelo)):
    _app().mismo_origen(request)
    lang = _idioma(idioma)
    with _conexion_corta(request) as conn:  # se cierra antes de llamar al modelo (D2)
        if not _disponible(request, conn):
            raise HTTPException(404, "Not Found")
        negocio_id = request.state.negocio_id
    visitante, nuevo = _visitante(request)
    actor = Actor.de_visitante(negocio_id, visitante)
    mostrado = modelo.omitir_datos_personales(texto.strip())  # lo que se ve y lo que va al modelo: sin datos personales
    pedido = {"rol": "usuario", "texto": mostrado, "propuestas": []}
    conversacion_id = int(conversacion) if re.fullmatch(r"[1-9][0-9]{0,17}", conversacion) else None

    def respuesta(status_code=200, *, nuevos=None, error="", id_=conversacion_id):
        r = _app().render(request, "_asistente_visitante_turno.html", status_code if not _hx(request) else 200, lang=lang,
                          mensajes=nuevos or [], conversacion_id=id_, error_texto=error)
        if nuevo:
            _poner_cookie(request, r, visitante)
        return r

    def fija(motivo: str, codigo: int):
        return respuesta(codigo, nuevos=[pedido, {"rol": "asistente", "texto": respuesta_fija("visitante", motivo, lang),
                                                  "propuestas": []}])

    if web:  # campo trampa para robots: respuesta de apariencia normal, sin modelo ni base
        return fija("fallo", 200)
    ip = _app()._ip_cliente(request)
    if not limite_visitantes.disponible(ip):
        return fija("limite", 429)
    limite_visitantes.registrar(ip)
    try:
        r = modelo.conversar(actor, texto, conversacion_id, cliente=cliente, idioma=lang)
    except modelo.AsistenteApagado:
        raise HTTPException(404, "Not Found") from None
    except modelo.TextoInvalido:
        maximo = modelo.AJUSTES["visitante"].largo_mensaje
        return respuesta(422, error=copia.COPIA[lang]["asistente"]["err_texto"].format(max=maximo))
    except modelo.ConversacionNoExiste:  # un id que no es de este visitante se comporta como uno que no existe
        return respuesta(404, id_=None, nuevos=[pedido, {"rol": "asistente", "texto": respuesta_fija("visitante", "fallo", lang),
                                                         "propuestas": []}])
    tarjetas = [x for x in (_tarjeta(p, lang) for p in r["propuestas"]) if x]
    nuevos = [pedido, {"rol": "asistente", "texto": r["respuesta"], "propuestas": tarjetas}]
    return respuesta(nuevos=nuevos, id_=r["conversacion_id"])
