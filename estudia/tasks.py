"""Tareas programadas durables y ciclo idempotente (PRD §6.7)."""
import json
import traceback
from datetime import datetime, timedelta

from . import clock, config, db

HANDLERS: dict = {}


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def schedule(conn, kind: str, run_at: datetime, data: dict | None = None) -> int:
    row = conn.execute(
        "insert into tarea_programada(tipo, ejecutar_en, datos) values (%s,%s,%s) returning id",
        (kind, run_at, json.dumps(data or {})),
    ).fetchone()
    return row["id"]


def _run_one(conn) -> bool:
    """Toma una tarea vencida y la ejecuta. Seguro si corren dos ciclos a la vez (skip locked)."""
    from . import jobs  # noqa: F401  (registra handlers)

    now = clock.now(conn)
    t = conn.execute(
        "select * from tarea_programada where estado='pendiente' and ejecutar_en <= %s "
        "order by ejecutar_en, id limit 1 for update skip locked",
        (now,),
    ).fetchone()
    if t is None:
        return False
    try:
        with conn.transaction():
            HANDLERS[t["tipo"]](conn, t["datos"], now)
        conn.execute("update tarea_programada set estado='hecha', intentos=intentos+1 where id=%s", (t["id"],))
    except Exception:
        err = traceback.format_exc(limit=3)
        n = t["intentos"] + 1
        if n >= config.get(conn, "reintentos_tarea"):
            conn.execute("update tarea_programada set estado='fallida', intentos=%s, error=%s where id=%s",
                         (n, err, t["id"]))
        else:
            conn.execute("update tarea_programada set intentos=%s, error=%s, ejecutar_en=%s where id=%s",
                         (n, err, now + timedelta(seconds=30 * n), t["id"]))
    return True


def cycle(conn=None, max_tasks: int = 500) -> dict:
    """Un ciclo: tareas vencidas, ofertas vencidas, cupos cerrados, detección y cierre diarios."""
    own = conn is None
    if own:
        conn = db.connect()
    try:
        from . import jobs

        ran = 0
        while ran < max_tasks:
            ok = _run_one(conn)
            conn.commit()
            if not ok:
                break
            ran += 1
        now = clock.now(conn)
        summary = {"tareas": ran}
        for name, fn in (("ofertas_vencidas", jobs.expire_offers),
                         ("cupos_cerrados", jobs.close_slots),
                         ("diario", jobs.run_daily)):
            try:
                with conn.transaction():
                    summary[name] = fn(conn, now)
            except Exception:
                summary[name] = "error"
                _record_failure(conn, name, traceback.format_exc(limit=3), now)
            conn.commit()
        return summary
    finally:
        if own:
            conn.close()


def _record_failure(conn, name: str, err: str, now: datetime) -> None:
    conn.execute(
        "insert into tarea_programada(tipo, ejecutar_en, estado, intentos, error) values (%s,%s,'fallida',1,%s)",
        (f"ciclo:{name}", now, err),
    )
