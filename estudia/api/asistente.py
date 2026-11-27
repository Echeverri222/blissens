"""Rutas del asistente del equipo (docs/prd-asistente.md, §6). Solo existen si hay clave de la API (`web.app.crear_app`).

`POST /mensajes` no retiene ninguna conexión mientras espera al modelo (D2): autentica con `usuario_sin_conexion` y el bucle
abre conexiones cortas por su cuenta.
"""
from fastapi import APIRouter, Depends

from ..asistente import Actor, conversacion
from . import schemas as sc
from .comun import PREFIJO, ApiError, solo_json, usuario_sin_conexion

router = APIRouter(prefix=f"{PREFIJO}/asistente", tags=["Asistente"], dependencies=[Depends(solo_json)], responses={
    401: {"model": sc.Error, "description": "Sin sesión o sesión vencida"},
    403: {"model": sc.Error, "description": "Asistente apagado para este negocio, o el rol no lo usa"},
    404: {"model": sc.Error, "description": "La conversación no existe o no es de este usuario"},
    422: {"model": sc.Error, "description": "Datos inválidos"},
})


def cliente_del_modelo():
    """Dependencia que entrega el cliente de la API; `None` usa el real. Las pruebas la sustituyen con un cliente falso."""
    return None


def _actor(u: dict) -> Actor:
    try:
        return Actor.de_usuario(u)
    except ValueError:
        raise ApiError(403, "sin_permiso", "Tu rol no usa el asistente.") from None


@router.get("/estado", summary="¿Puede este usuario usar el asistente?", response_model=sc.AsistenteEstadoOut,
            description="`disponible` es falso si el negocio no lo encendió para el equipo. El panel oculta el acceso en ese caso.")
def estado(u=Depends(usuario_sin_conexion)):
    return conversacion.estado(_actor(u))


@router.post("/mensajes", summary="Enviar un mensaje al asistente", response_model=sc.AsistenteRespuestaOut,
             description="Hasta 1 000 caracteres. Sin `conversacion_id` abre una conversación. Un tope, un fallo del modelo o un "
                         "mensaje que tarda más de 45 s responden 200 con un texto fijo y sin `propuestas`. Las `propuestas` no "
                         "se ejecutan: el panel las confirma con los endpoints que ya existen.")
def enviar(datos: sc.AsistenteMensajeIn, u=Depends(usuario_sin_conexion), cliente=Depends(cliente_del_modelo)):
    actor = _actor(u)
    try:
        return conversacion.conversar(actor, datos.texto, datos.conversacion_id, cliente=cliente)
    except conversacion.AsistenteApagado:
        raise ApiError(403, "asistente_apagado", "El asistente no está activado para este negocio.") from None
    except conversacion.ConversacionNoExiste:
        raise ApiError(404, "no_existe", "No existe esa conversación.") from None
    except conversacion.TextoInvalido as e:
        raise ApiError(422, "datos_invalidos", str(e)) from None


@router.get("/conversaciones/{conversacion_id}", summary="Una conversación propia, para mostrarla de nuevo",
            response_model=sc.AsistenteConversacionOut,
            description="Solo las del propio usuario y negocio; cualquier otra es 404, como una que no existe.")
def conversacion_propia(conversacion_id: int, u=Depends(usuario_sin_conexion)):
    try:
        return conversacion.leer(_actor(u), conversacion_id)
    except conversacion.ConversacionNoExiste:
        raise ApiError(404, "no_existe", "No existe esa conversación.") from None
