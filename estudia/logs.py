"""Registro estructurado: una línea JSON por petición con negocio, petición, usuario, ruta, resultado y duración.

NUNCA se escriben nombres, documentos, celulares ni textos de mensajes: de la ruta solo va la PLANTILLA
(`/pacientes/{paciente_id}`), no la dirección real, que puede llevar identificadores o enlaces firmados.
"""
import json
import time
import uuid

from fastapi import FastAPI, Request


def configurar() -> None:
    """Nada que configurar: cada evento es una línea JSON en la salida estándar (Render la recoge tal cual)."""


def evento(**campos) -> None:
    print(json.dumps(campos, ensure_ascii=False, default=str), flush=True)


def instalar(app: FastAPI) -> None:
    configurar()

    @app.middleware("http")
    async def registrar(request: Request, call_next):
        inicio = time.perf_counter()
        peticion = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.negocio_id = None
        request.state.usuario_id = None
        estado = 500
        try:
            r = await call_next(request)
            estado = r.status_code
            r.headers["x-request-id"] = peticion
            return r
        finally:
            ruta = getattr(request.scope.get("route"), "path", None) or "(sin ruta)"
            evento(evento="peticion", peticion=peticion, negocio=request.state.negocio_id, usuario=request.state.usuario_id,
                   metodo=request.method, ruta=ruta, estado=estado, ms=round((time.perf_counter() - inicio) * 1000, 1))
