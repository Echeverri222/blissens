"""Permisos: una sola función decide si un usuario puede actuar sobre un profesional o una cita (PRD #2 §6.5).

Las rutas no repiten esta lógica. Un especialista que pide algo de otro profesional recibe NoExiste (404),
igual que si no existiera, para no revelar nada.
"""


class SinPermiso(Exception):
    """El rol no puede hacer esta operación (403)."""


class NoExiste(Exception):
    """No existe, o pertenece a otro profesional (404)."""


def es_auxiliar(usuario: dict) -> bool:
    return usuario["rol"] == "auxiliar"


def exigir_auxiliar(usuario: dict) -> None:
    if not es_auxiliar(usuario):
        raise SinPermiso("Esta operación es solo para recepción")


def exigir_administrador(usuario: dict) -> None:
    if not usuario.get("administrador"):
        raise SinPermiso("Esta operación es solo para quien administra el negocio")


def puede_actuar_sobre_profesional(usuario: dict, profesional_id: int) -> bool:
    return es_auxiliar(usuario) or usuario["profesional_id"] == profesional_id


def exigir_profesional(usuario: dict, profesional_id: int) -> None:
    if not puede_actuar_sobre_profesional(usuario, profesional_id):
        raise NoExiste("No existe")


def alcance_profesional(usuario: dict, pedido: int | None) -> int | None:
    """Profesional cuyo contenido se devuelve: el especialista siempre recibe el suyo (el filtro se ignora)."""
    return pedido if es_auxiliar(usuario) else usuario["profesional_id"]


def cita_visible(conn, usuario: dict, cita_id: int) -> dict:
    c = conn.execute("select * from cita where id=%s", (cita_id,)).fetchone()
    if c is None or not puede_actuar_sobre_profesional(usuario, c["profesional_id"]):
        raise NoExiste("No existe esa cita")
    return c


# ----------------------------------------------------------------- acciones permitidas (PRD #3 §6.3)

VIVAS = ("programada", "confirmada", "no_confirmada")
REVERSIBLES = ("cancelada", "reprogramada", "no_asistio", "atendida", "confirmada")
DESENLACES = ("atendida", "no_asistio")


def acciones_cita(usuario: dict, estado: str, inicio, ahora) -> list[str]:
    """Qué puede hacer este usuario con la cita, según su rol, su estado y el reloj del sistema."""
    if estado not in VIVAS:
        return []
    acciones = []
    if inicio is None or ahora >= inicio:
        acciones.append("desenlace")
    if es_auxiliar(usuario) and inicio is not None and ahora < inicio:
        if estado in ("programada", "no_confirmada"):
            acciones.append("confirmar")
        acciones += ["cancelar", "cambiar_fecha"]
    return acciones


def puede_revertir(usuario: dict, movimiento: dict, estado_actual: str) -> bool:
    """Un movimiento es reversible si es el último de su cita y el rol puede deshacerlo.

    El resto de condiciones (rango libre, no bloqueado) las valida `agenda.revert` al ejecutar.
    """
    if movimiento["estado_anterior"] is None or movimiento["revertido"] or movimiento["revierte_id"] is not None:
        return False
    if movimiento["estado_nuevo"] != estado_actual or estado_actual not in REVERSIBLES:
        return False
    return es_auxiliar(usuario) or estado_actual in DESENLACES
