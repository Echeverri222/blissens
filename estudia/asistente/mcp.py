"""Servidor MCP local por stdio (PRD asistente, §8): el catálogo de un perfil para una sesión de Claude Code.

    uv run python -m estudia.asistente.mcp                                   # operador: lectura + esquema y consulta_sql
    uv run python -m estudia.asistente.mcp --perfil auxiliar [--usuario X]   # lo que ve la recepción en el asistente
    uv run python -m estudia.asistente.mcp --perfil paciente [--paciente F146]  # lo que ve un paciente desde su enlace

Con `auxiliar` o `paciente` el servidor expone exactamente las herramientas y el alcance de ese perfil (las propuestas no
escriben: devuelven la tarjeta que la persona confirmaría) y entrega como instrucciones el mismo texto de sistema que usa el
asistente, con el bloque de contexto. Sirve para iterar herramientas, instrucciones y golden cases sin gastar en el modelo
del asistente; la elección de herramientas y la velocidad reales solo se ven en la interfaz.

Solo arranca con `ENTORNO=local`. Todo lo que una herramienta devuelve viaja a Anthropic en la conversación de Claude Code:
úsalo únicamente con los datos ficticios de demostración, nunca después de importar los Excel reales.
"""
import argparse
import inspect
import sys
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import clock, db, settings
from .actor import Actor
from .base import Herramienta
from .catalogo import herramientas_de
from .conversacion import _contexto, precarga
from .despachador import ejecutar
from .instrucciones import INSTRUCCIONES

PERFILES_MCP = ("operador", "auxiliar", "paciente")


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


def crear_servidor(actor: Actor, conexion=None, instrucciones: str | None = None) -> MCPServer:
    """Un servidor con las herramientas del perfil del actor, y solo esas. `conexion`: ver `ejecutar`."""
    servidor = MCPServer("estudia", instructions=instrucciones
                         or "Herramientas de solo lectura sobre los datos ficticios de Estud-IA (perfil operador).")
    for h in herramientas_de(actor.perfil):
        servidor.add_tool(_funcion(h, actor, conexion), name=h.nombre, description=h.descripcion)
    return servidor


class SinActor(Exception):
    pass


def _usuario(conn, nombre_usuario: str | None) -> dict:
    """El usuario auxiliar con su acceso al negocio activo, como lo vería una sesión del panel."""
    filtro, params = ("and lower(u.nombre_usuario)=lower(%s)", (nombre_usuario,)) if nombre_usuario else ("", ())
    u = conn.execute(
        "select u.id, u.nombre_usuario, u.nombre, u.debe_cambiar_clave, a.negocio_id, a.rol, a.profesional_id, a.administrador "
        f"from acceso a join usuario u on u.id=a.usuario_id where a.activo and u.activo and a.rol='auxiliar' {filtro} "
        "order by a.id limit 1", params).fetchone()
    if u is None:
        raise SinActor(f"No hay un usuario auxiliar activo{f' llamado {nombre_usuario!r}' if nombre_usuario else ''}.")
    return dict(u)


def _paciente(conn, paciente: str | None) -> int:
    """El paciente por `external_id` o id; sin él, el de la próxima cita (siempre hay algo que preguntar)."""
    if paciente:
        r = conn.execute("select id from paciente where external_id=%s or id::text=%s order by id limit 1",
                         (paciente, paciente)).fetchone()
    else:
        r = conn.execute("select paciente_id as id from cita where lower(rango) > %s "
                         "and estado in ('programada','confirmada','no_confirmada') order by lower(rango) limit 1",
                         (clock.now(conn),)).fetchone()
    if r is None:
        raise SinActor(f"No existe el paciente {paciente!r}." if paciente else "No hay citas próximas para elegir un paciente.")
    return r["id"]


def actor_de(conn, negocio_id: int, perfil: str, usuario: str | None = None, paciente: str | None = None) -> Actor:
    if perfil == "auxiliar":
        return Actor.de_usuario(_usuario(conn, usuario))
    if perfil == "paciente":
        return Actor.de_paciente(negocio_id, _paciente(conn, paciente))
    return Actor.de_operador(negocio_id)


def instrucciones_de(conn, actor: Actor) -> str | None:
    """Para auxiliar y paciente: el texto de sistema del asistente y su bloque de contexto (fijado al arrancar)."""
    if actor.perfil not in INSTRUCCIONES:
        return None
    return (f"{INSTRUCCIONES[actor.perfil]}\n\n{_contexto(conn, actor)}\n\nLas herramientas proponer_* no escriben nada: "
            "devuelven la tarjeta que la persona confirmaría con un botón.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m estudia.asistente.mcp")
    ap.add_argument("--perfil", choices=PERFILES_MCP, default="operador")
    ap.add_argument("--usuario", help="auxiliar: nombre de usuario (por defecto, el primer auxiliar activo)")
    ap.add_argument("--paciente", help="paciente: external_id o id (por defecto, el de la próxima cita)")
    ap.add_argument("--contexto", action="store_true",
                    help="imprime el bloque <contexto> con el que abre cada pregunta y sale (para el subagente)")
    a = ap.parse_args(argv)
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
    conn = db.connect()
    try:
        actor = actor_de(conn, negocio_id, a.perfil, a.usuario, a.paciente)
        if a.contexto:  # lo mismo que abre cada mensaje en el asistente: <contexto> y <precargado>
            print(_contexto(conn, actor))
            print(precarga(actor, clock.now(conn).date()))
            return 0
        instrucciones = instrucciones_de(conn, actor)
    except SinActor as e:
        print(str(e), file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"MCP estudia: perfil {actor.perfil}"
          + (f", paciente {actor.paciente_id}" if actor.paciente_id else "")
          + (f", usuario {actor.usuario['nombre_usuario']}" if actor.usuario else ""), file=sys.stderr)
    crear_servidor(actor, instrucciones=instrucciones).run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
