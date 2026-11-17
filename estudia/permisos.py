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
