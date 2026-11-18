"""Horario y bloqueos de un profesional (PRD #2 §6.6)."""
from datetime import date, datetime, timedelta

from psycopg.types.range import Range

from . import clock
from .agenda import _local
from .lifecycle import ALIVE


class BlockInvalid(Exception):
    """Fechas del bloqueo inválidas (fin no posterior al inicio, o fin en el pasado)."""


class BlockConflict(Exception):
    """El rango se cruza con citas vivas: recepción debe moverlas antes."""

    def __init__(self, citas: list[dict]):
        super().__init__("El rango se cruza con citas vivas")
        self.citas = citas


class BlockPast(Exception):
    """Un bloqueo que ya terminó forma parte de la ocupación consolidada y no se elimina."""


class BlockNotFound(Exception):
    pass


def schedule(conn, professional_id: int) -> list[dict]:
    return conn.execute(
        "select dia_semana, desde, hasta from horario_atencion where profesional_id=%s order by dia_semana, desde",
        (professional_id,)).fetchall()


def list_blocks(conn, professional_id: int | None, desde: date, hasta: date) -> list[dict]:
    d0 = _local(desde, datetime.min.time())
    d1 = _local(hasta, datetime.min.time()) + timedelta(days=1)
    return conn.execute(
        "select b.id, b.profesional_id, b.rango, b.motivo, b.creado_por, b.creado_en, u.nombre as creado_por_nombre "
        "from bloqueo b left join usuario u on u.id=b.creado_por where b.rango && tstzrange(%s,%s) "
        "and (%s::bigint is null or b.profesional_id=%s) order by lower(b.rango), b.id",
        (d0, d1, professional_id, professional_id)).fetchall()


def get_block(conn, block_id: int) -> dict | None:
    return conn.execute(
        "select b.id, b.profesional_id, b.rango, b.motivo, b.creado_por, b.creado_en, u.nombre as creado_por_nombre "
        "from bloqueo b left join usuario u on u.id=b.creado_por where b.id=%s", (block_id,)).fetchone()


def conflicting_appointments(conn, professional_id: int, rango: Range) -> list[dict]:
    return conn.execute(
        "select c.id, c.estado, c.rango, c.profesional_id, s.nombre as servicio, p.id as paciente_id, "
        "p.nombres || ' ' || p.apellidos as paciente from cita c join servicio s on s.id=c.servicio_id "
        "join paciente p on p.id=c.paciente_id where c.profesional_id=%s and c.estado = any(%s) and c.rango && %s "
        "order by lower(c.rango)", (professional_id, list(ALIVE), rango)).fetchall()


def create_block(conn, professional_id: int, start: datetime, end: datetime, reason: str,
                 user_id: int | None = None) -> int:
    """Crea un bloqueo. Nunca cancela citas: si hay citas vivas en el rango, se rechaza y se listan."""
    now = clock.now(conn)
    if end <= start:
        raise BlockInvalid("El fin del bloqueo debe ser posterior al inicio")
    if end <= now:
        raise BlockInvalid("El bloqueo debe terminar en el futuro")
    rango = Range(start, end, "[)")
    # Serializa bloqueos y agendamientos concurrentes sobre el mismo profesional.
    conn.execute("select id from profesional where id=%s for update", (professional_id,))
    conflicts = conflicting_appointments(conn, professional_id, rango)
    if conflicts:
        raise BlockConflict(conflicts)
    # Los cupos abiertos que se crucen dejan de existir, con sus ofertas pendientes.
    conn.execute(
        "update oferta_adelanto o set estado='anulada', respondida_en=%s from cupo_liberado c "
        "where o.cupo_id=c.id and o.estado='pendiente' and c.profesional_id=%s and c.rango && %s "
        "and c.estado in ('abierto','en_oferta')", (now, professional_id, rango))
    conn.execute(
        "update cupo_liberado set estado='anulado' where profesional_id=%s and rango && %s "
        "and estado in ('abierto','en_oferta')", (professional_id, rango))
    return conn.execute(
        "insert into bloqueo(profesional_id, rango, motivo, creado_por, creado_en) values (%s,%s,%s,%s,%s) returning id",
        (professional_id, rango, reason, user_id, now)).fetchone()["id"]


def delete_block(conn, block_id: int) -> None:
    b = conn.execute("select * from bloqueo where id=%s for update", (block_id,)).fetchone()
    if b is None:
        raise BlockNotFound("No existe ese bloqueo")
    if b["rango"].upper <= clock.now(conn):
        raise BlockPast("Un bloqueo que ya terminó no se puede eliminar")
    conn.execute("delete from bloqueo where id=%s", (block_id,))
