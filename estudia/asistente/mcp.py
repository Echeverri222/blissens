"""Servidor MCP local por stdio (PRD asistente, §8): el catálogo del perfil `operador` para una sesión de Claude Code.

    uv run python -m estudia.asistente.mcp

Solo arranca con `ENTORNO=local`. Todo lo que una herramienta devuelve viaja a Anthropic en la conversación de Claude Code:
úsalo únicamente con los datos ficticios de demostración, nunca después de importar los Excel reales.
"""
import inspect
import sys
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import db, settings
from .actor import Actor
from .base import Herramienta
from .catalogo import herramientas_de
from .despachador import ejecutar


def _funcion(h: Herramienta, actor: Actor, conexion) -> Callable[..., dict]:
    """Una función cuya firma es la entrada de la herramienta, para que el SDK publique el mismo esquema."""
    def fn(**kwargs):
        return ejecutar(actor, h.nombre, kwargs, conexion=conexion)

    params = []
    for nombre, campo in h.modelo_de(actor.perfil).model_fields.items():
        anotacion = Annotated[campo.annotation, *campo.metadata, Field(description=campo.description)]
        params.append(inspect.Parameter(nombre, inspect.Parameter.KEYWORD_ONLY, annotation=anotacion,
                                        default=inspect.Parameter.empty if campo.is_required() else campo.default))
    fn.__signature__ = inspect.Signature(params, return_annotation=dict[str, Any])
    fn.__name__ = h.nombre
    return fn


def crear_servidor(actor: Actor, conexion=None) -> MCPServer:
    """Un servidor con las herramientas del perfil del actor, y solo esas. `conexion`: ver `ejecutar`."""
    servidor = MCPServer("estudia", instructions="Herramientas de solo lectura sobre los datos ficticios de Estud-IA (perfil operador).")
    for h in herramientas_de(actor.perfil):
        servidor.add_tool(_funcion(h, actor, conexion), name=h.nombre, description=h.descripcion)
    return servidor


def main() -> int:
    if settings.ENTORNO != "local":
        print(f"El servidor MCP del asistente solo arranca con ENTORNO=local (ENTORNO={settings.ENTORNO}).", file=sys.stderr)
        return 1
    conn = db.connect(negocio=None)
    try:
        negocio_id = db.negocio_id_de(conn, settings.NEGOCIO_POR_DEFECTO)
    finally:
        conn.close()
    if negocio_id is None:
        print(f"No existe el negocio '{settings.NEGOCIO_POR_DEFECTO}'.", file=sys.stderr)
        return 1
    crear_servidor(Actor.de_operador(negocio_id)).run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
