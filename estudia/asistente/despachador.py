"""El despachador: la única manera de ejecutar una herramienta (PRD asistente, D1 y D2).

Comprueba el perfil, valida la entrada, abre UNA conexión por llamada con el negocio del actor, corre el manejador en una
transacción de solo lectura, deja el registro de acceso, confirma, cierra y recorta la salida. Los errores vuelven como datos
que el modelo puede leer: `{"error": {"codigo": ..., "mensaje": ...}}`.
"""
import logging
from collections.abc import Callable

import psycopg
from pydantic import ValidationError

from .. import agenda, db, familia, horario, lifecycle, permisos, privacidad
from .actor import Actor
from .base import CATALOGO, ErrorHerramienta
from .catalogo import herramientas_de  # noqa: F401  (importa las herramientas y llena el catálogo)
from .salida import SENSIBLES, SENSIBLES_PACIENTE, jsonable, recortar, sanear

log = logging.getLogger("estudia.asistente")

# Error de dominio -> código estable
CODIGOS = {
    permisos.SinPermiso: "sin_permiso",
    permisos.NoExiste: "no_existe",
    familia.NoEsDeLaFamilia: "no_existe",
    horario.BlockNotFound: "no_existe",
    agenda.SlotTaken: "espacio_ocupado",
    lifecycle.InvalidTransition: "accion_no_permitida",
    agenda.OutcomeTooEarly: "accion_no_permitida",
    horario.BlockConflict: "accion_no_permitida",
    horario.BlockInvalid: "datos_invalidos",
}


def _error(codigo: str, mensaje: str) -> dict:
    return {"error": {"codigo": codigo, "mensaje": mensaje}}


def _campos_invalidos(e: ValidationError) -> str:
    # Solo los nombres de los campos y el tipo de fallo: nunca el valor recibido.
    campos = sorted({".".join(str(p) for p in err["loc"]) or "entrada" for err in e.errors()})
    return f"Revisa los datos enviados ({', '.join(campos)})."


def _abrir(actor: Actor, conexion) -> psycopg.Connection:
    if callable(conexion):
        return conexion(actor)
    return db.connect(conexion, negocio=actor.negocio_id, usuario_id=actor.usuario_id)


def ejecutar(actor: Actor, nombre: str, args: dict | None = None, *, conexion: str | Callable[[Actor], psycopg.Connection] | None = None) -> dict:
    """Ejecuta una herramienta en nombre del actor. `conexion`: URL de la base o función `actor -> conexión` (pruebas)."""
    h = CATALOGO.get(nombre)
    if h is None:
        return _error("no_existe", f"No existe la herramienta {nombre}.")
    if actor.perfil not in h.perfiles:
        return _error("sin_permiso", f"La herramienta {nombre} no está disponible para este perfil.")
    try:
        entrada = h.modelo_de(actor.perfil).model_validate(args or {})
    except ValidationError as e:
        return _error("datos_invalidos", _campos_invalidos(e))

    conn = _abrir(actor, conexion)
    try:
        conn.read_only = True  # un manejador no puede escribir aunque lo intentara (P2)
        try:
            salida = h.manejador(conn, actor, entrada)
        except ErrorHerramienta as e:
            conn.rollback()
            return _error(e.codigo, e.mensaje)
        except tuple(CODIGOS) as e:
            conn.rollback()
            return _error(next(c for t, c in CODIGOS.items() if isinstance(e, t)), str(e) or "No se pudo completar la operación.")
        conn.commit()
        conn.read_only = False
        if h.auditoria:
            # Los argumentos no se guardan, solo qué herramienta, para quién y sobre qué.
            privacidad.registrar(conn, actor.usuario_id, h.auditoria,
                                 actor.paciente_id if actor.perfil == "paciente" else getattr(entrada, "paciente_id", None),
                                 getattr(entrada, "cita_id", None), f"herramienta {nombre}")
            conn.commit()
    except Exception:
        log.exception("Falló la herramienta %s (perfil %s)", nombre, actor.perfil)
        return _error("error_interno", "No se pudo completar la consulta.")
    finally:
        conn.close()
    if actor.perfil != "operador":
        salida = sanear(jsonable(salida), SENSIBLES_PACIENTE if actor.perfil == "paciente" else SENSIBLES)
    else:
        salida = jsonable(salida)
    return recortar(salida)
