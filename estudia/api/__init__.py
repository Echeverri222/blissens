"""API JSON v1: sesión con roles, agenda del especialista y la operación de la auxiliar."""
from fastapi import APIRouter

from . import gestion, operacion, schemas
from .comun import PREFIJO, registrar_errores

router = APIRouter(prefix=PREFIJO, responses={
    401: {"model": schemas.Error, "description": "Sin sesión o sesión vencida"},
    403: {"model": schemas.Error, "description": "El rol no tiene permiso"},
    404: {"model": schemas.Error, "description": "No existe, o es de otro profesional"},
    409: {"model": schemas.Error, "description": "Conflicto con el estado actual"},
    422: {"model": schemas.Error, "description": "Datos inválidos"},
    429: {"model": schemas.Error, "description": "Inicio de sesión bloqueado por intentos fallidos"},
})
router.include_router(operacion.router)
router.include_router(gestion.router)

__all__ = ["router", "registrar_errores"]
