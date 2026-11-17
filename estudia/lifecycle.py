"""Ciclo de vida: máquina de estados e historial de cada cita (RD-02)."""
from . import clock

ALIVE = ("programada", "confirmada", "no_confirmada")

TRANSITIONS = {
    "programada": {"confirmada", "no_confirmada", "cancelada", "reprogramada", "atendida", "no_asistio"},
    "confirmada": {"cancelada", "reprogramada", "atendida", "no_asistio"},
    "no_confirmada": {"confirmada", "cancelada", "reprogramada", "atendida", "no_asistio"},
    "cancelada": {"reprogramada"},
    "reprogramada": set(),
    "atendida": set(),
    "no_asistio": set(),
}

ACTORS = ("paciente", "auxiliar", "sistema")


class InvalidTransition(Exception):
    pass


def transition(conn, cita_id: int, nuevo: str, actor: str, detalle: str = "",
               revierte_id: int | None = None, force: bool = False) -> int:
    """Valida y registra quién/qué/cuándo. `force` solo lo usan las reversiones."""
    assert actor in ACTORS
    row = conn.execute("select estado from cita where id=%s for update", (cita_id,)).fetchone()
    if row is None:
        raise InvalidTransition(f"La cita {cita_id} no existe")
    actual = row["estado"]
    if not force and nuevo not in TRANSITIONS[actual]:
        raise InvalidTransition(f"No se puede pasar de {actual} a {nuevo}")
    conn.execute("update cita set estado=%s where id=%s", (nuevo, cita_id))
    h = conn.execute(
        "insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, detalle, momento, revierte_id) "
        "values (%s,%s,%s,%s,%s,%s,%s) returning id",
        (cita_id, actual, nuevo, actor, detalle, clock.now(conn), revierte_id),
    ).fetchone()
    return h["id"]


def record_birth(conn, cita_id: int, estado: str, actor: str, detalle: str = "") -> None:
    conn.execute(
        "insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, detalle, momento) "
        "values (%s,null,%s,%s,%s,%s)",
        (cita_id, estado, actor, detalle, clock.now(conn)),
    )
