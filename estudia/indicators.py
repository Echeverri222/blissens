"""Indicadores: hechos diarios (cierre) y consultas del tablero (PRD §6.8)."""
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta

from . import clock, config, db
from .agenda import _local


def _minutes_available(conn, pro_id: int, day: date) -> int:
    total = 0
    d0 = _local(day, datetime.min.time())
    d1 = d0 + timedelta(days=1)
    blocks = [r["rango"] for r in conn.execute(
        "select rango from bloqueo where profesional_id=%s and rango && tstzrange(%s,%s)", (pro_id, d0, d1))]
    for w in conn.execute("select desde, hasta from horario_atencion where profesional_id=%s and dia_semana=%s",
                          (pro_id, day.weekday())).fetchall():
        a, b = _local(day, w["desde"]), _local(day, w["hasta"])
        minutes = (b - a).total_seconds() / 60
        # Unión de bloqueos: el tiempo compartido por dos bloqueos solapados se resta una sola vez.
        spans = sorted((max(a, bl.lower), min(b, bl.upper)) for bl in blocks if min(b, bl.upper) > max(a, bl.lower))
        cur_lo = cur_hi = None
        for lo, hi in spans:
            if cur_hi is None or lo > cur_hi:
                if cur_hi is not None:
                    minutes -= (cur_hi - cur_lo).total_seconds() / 60
                cur_lo, cur_hi = lo, hi
            else:
                cur_hi = max(cur_hi, hi)
        if cur_hi is not None:
            minutes -= (cur_hi - cur_lo).total_seconds() / 60
        total += max(0, minutes)
    return int(total)


def close_day(conn, day: date) -> None:
    """Consolida los conteos del día. Repetir el cierre de una fecha reemplaza sus hechos sin duplicar."""
    conn.execute("delete from hecho_diario where fecha=%s", (day,))
    conn.execute("delete from hecho_diario_profesional where fecha=%s", (day,))
    conn.execute(
        """
        insert into hecho_diario(fecha, profesional_id, servicio_id, citas, atendidas, no_asistio, canceladas,
            reprogramadas, con_recordatorio, confirmadas_explicitas, minutos_atendidos)
        select c.dia, c.profesional_id, c.servicio_id, count(*),
            count(*) filter (where c.estado='atendida'),
            count(*) filter (where c.estado='no_asistio'),
            count(*) filter (where c.estado='cancelada'),
            count(*) filter (where c.estado='reprogramada'),
            count(*) filter (where (c.datos_origen->>'recordatorio_enviado')::boolean),
            count(*) filter (where exists (select 1 from historial_estado h where h.cita_id=c.id
                                           and h.estado_nuevo='confirmada' and h.actor='paciente'
                                           and h.revierte_id is null)),
            coalesce(sum(extract(epoch from upper(c.rango)-lower(c.rango))/60)
                     filter (where c.estado='atendida' and c.rango is not null), 0)::int
        from cita c where c.dia=%s group by c.dia, c.profesional_id, c.servicio_id
        """, (day,))
    for r in conn.execute(
            """
            select c.profesional_id, c.servicio_id, count(*) as n, count(*) filter (where x.tardia) as tardias,
                   count(*) filter (where c.estado='reprogramada') as recuperadas,
                   coalesce(m.etiqueta, 'sin especificar') as motivo
            from cancelacion x join cita c on c.id=x.cita_id
            left join motivo_cancelacion m on m.id=x.motivo_id
            where c.dia=%s group by c.profesional_id, c.servicio_id, m.etiqueta
            """, (day,)).fetchall():
        conn.execute(
            """
            insert into hecho_diario(fecha, profesional_id, servicio_id, cancelaciones, cancelaciones_tardias,
                cancelaciones_recuperadas, motivos)
            values (%(f)s,%(p)s,%(s)s,%(n)s,%(t)s,%(r)s,%(m)s)
            on conflict (fecha, profesional_id, servicio_id) do update set
              cancelaciones = hecho_diario.cancelaciones + excluded.cancelaciones,
              cancelaciones_tardias = hecho_diario.cancelaciones_tardias + excluded.cancelaciones_tardias,
              cancelaciones_recuperadas = hecho_diario.cancelaciones_recuperadas + excluded.cancelaciones_recuperadas,
              motivos = hecho_diario.motivos || excluded.motivos
            """,
            {"f": day, "p": r["profesional_id"], "s": r["servicio_id"], "n": r["n"], "t": r["tardias"],
             "r": r["recuperadas"], "m": json.dumps({r["motivo"]: [r["n"], r["tardias"]]})})
    for p in conn.execute("select id from profesional").fetchall():
        slot = conn.execute(
            """
            select count(*) as lib,
                   count(*) filter (where estado='ocupado' and ocupado_por='oferta') as oferta,
                   count(*) filter (where estado='ocupado' and ocupado_por='agendamiento') as agend,
                   count(*) filter (where estado='vacio') as vacios
            from cupo_liberado where profesional_id=%s and (lower(rango) at time zone 'America/Bogota')::date=%s
              and estado <> 'anulado'
            """, (p["id"], day)).fetchone()
        conn.execute(
            "insert into hecho_diario_profesional(fecha, profesional_id, minutos_disponibles, cupos_liberados, "
            "cupos_ocupados_oferta, cupos_ocupados_agendamiento, cupos_vacios) values (%s,%s,%s,%s,%s,%s,%s)",
            (day, p["id"], _minutes_available(conn, p["id"], day), slot["lib"], slot["oferta"], slot["agend"],
             slot["vacios"]))


def close_all(conn) -> dict:
    """Cierre de todo el historial hasta hoy (idempotente). Es lo que ejecutan `make cierre` y la API."""
    first = conn.execute("select min(dia) as d from cita").fetchone()["d"]
    today = clock.now(conn).date()
    n = close_range(conn, first, today) if first else 0
    if first:
        config.set_(conn, "ultimo_diario", today.isoformat())
    return {"dias": n, "desde": first, "hasta": today if first else None}


def close_range(conn, desde: date, hasta: date) -> int:
    n = 0
    d = desde
    while d <= hasta:
        close_day(conn, d)
        d += timedelta(days=1)
        n += 1
    return n


# ----- Consultas del tablero -----

def _where(filters: dict, alias: str = "") -> tuple[str, dict]:
    a = f"{alias}." if alias else ""
    parts, params = [f"{a}fecha between %(desde)s and %(hasta)s"], {"desde": filters["desde"], "hasta": filters["hasta"]}
    if filters.get("profesional_id"):
        parts.append(f"{a}profesional_id = %(pro)s")
        params["pro"] = filters["profesional_id"]
    if filters.get("servicio_id") and alias != "hp":
        parts.append(f"{a}servicio_id = %(srv)s")
        params["srv"] = filters["servicio_id"]
    return " and ".join(parts), params


def _ratio(n, d):
    return (n / d) if d else None


def summary(conn, filters: dict) -> dict:
    w, p = _where(filters)
    r = conn.execute(
        f"select coalesce(sum(citas),0) citas, coalesce(sum(atendidas),0) atendidas, coalesce(sum(no_asistio),0) no_asistio, "
        f"coalesce(sum(con_recordatorio),0) con_rec, coalesce(sum(confirmadas_explicitas),0) conf, "
        f"coalesce(sum(cancelaciones),0) canc, coalesce(sum(cancelaciones_tardias),0) tard, "
        f"coalesce(sum(cancelaciones_recuperadas),0) recup, coalesce(sum(minutos_atendidos),0) min_at "
        f"from hecho_diario where {w}", p).fetchone()
    wp, pp = _where(filters, "hp")
    cap = conn.execute(
        f"select coalesce(sum(minutos_disponibles),0) disp, coalesce(sum(cupos_liberados),0) lib, "
        f"coalesce(sum(cupos_ocupados_oferta),0) oferta, coalesce(sum(cupos_ocupados_agendamiento),0) agend, "
        f"coalesce(sum(cupos_vacios),0) vacios from hecho_diario_profesional hp where {wp}", pp).fetchone()
    min_at = r["min_at"]
    if filters.get("servicio_id") is None:
        pass
    return {
        "citas": r["citas"], "atendidas": r["atendidas"], "no_asistio": r["no_asistio"],
        "atencion_efectiva": _ratio(r["atendidas"], r["citas"]),
        "inasistencia": _ratio(r["no_asistio"], r["atendidas"] + r["no_asistio"]),
        "cancelaciones": r["canc"], "cancelaciones_tardias": r["tard"], "cancelaciones_recuperadas": r["recup"],
        "recuperacion": _ratio(r["recup"], r["canc"]),
        "confirmacion": _ratio(r["conf"], r["con_rec"]),
        "ocupacion": _ratio(min_at, cap["disp"]),
        "minutos_disponibles": cap["disp"], "minutos_atendidos": min_at,
        "cupos_liberados": cap["lib"], "cupos_ocupados_oferta": cap["oferta"],
        "cupos_ocupados_agendamiento": cap["agend"], "cupos_vacios": cap["vacios"],
    }


def by_dimension(conn, filters: dict, dim: str) -> list[dict]:
    """Inasistencia por profesional o servicio."""
    w, p = _where(filters, "h")
    col, join = ("p.nombre", "profesional p on p.id=h.profesional_id") if dim == "profesional" else \
                ("s.nombre", "servicio s on s.id=h.servicio_id")
    rows = conn.execute(
        f"select {col} as nombre, sum(h.atendidas) atendidas, sum(h.no_asistio) no_asistio, sum(h.citas) citas "
        f"from hecho_diario h join {join} where {w} group by {col} order by {col}", p).fetchall()
    return [{"nombre": r["nombre"], "atendidas": r["atendidas"], "no_asistio": r["no_asistio"], "citas": r["citas"],
             "inasistencia": _ratio(r["no_asistio"], r["atendidas"] + r["no_asistio"])} for r in rows]


def trend(conn, filters: dict) -> list[dict]:
    w, p = _where(filters)
    rows = conn.execute(
        f"select fecha, sum(citas) citas, sum(atendidas) atendidas, sum(no_asistio) no_asistio from hecho_diario "
        f"where {w} group by fecha order by fecha", p).fetchall()
    return [{"fecha": r["fecha"], "citas": r["citas"], "atendidas": r["atendidas"], "no_asistio": r["no_asistio"],
             "inasistencia": _ratio(r["no_asistio"], r["atendidas"] + r["no_asistio"])} for r in rows]


def weekly_trend(conn, filters: dict) -> list[dict]:
    """Tendencia agrupada por semana (lunes) con la inasistencia recalculada sobre la suma semanal."""
    out: dict[date, dict] = {}
    for r in trend(conn, filters):
        monday = r["fecha"] - timedelta(days=r["fecha"].weekday())
        w = out.setdefault(monday, {"fecha": monday, "citas": 0, "atendidas": 0, "no_asistio": 0})
        for k in ("citas", "atendidas", "no_asistio"):
            w[k] += r[k]
    return [{**w, "inasistencia": _ratio(w["no_asistio"], w["atendidas"] + w["no_asistio"])} for w in out.values()]


def reasons(conn, filters: dict) -> list[dict]:
    w, p = _where(filters)
    total: Counter = Counter()
    late: Counter = Counter()
    for r in conn.execute(f"select motivos from hecho_diario where {w}", p):
        for k, (n, t) in r["motivos"].items():
            total[k] += n
            late[k] += t
    return [{"motivo": k, "cancelaciones": n, "tardias": late[k]} for k, n in total.most_common()]


def time_between(conn, filters: dict) -> list[dict]:
    """Días promedio entre citas atendidas consecutivas, por servicio."""
    params = {"desde": filters["desde"], "hasta": filters["hasta"]}
    extra = ""
    if filters.get("profesional_id"):
        extra += " and c.profesional_id = %(pro)s"
        params["pro"] = filters["profesional_id"]
    if filters.get("servicio_id"):
        extra += " and c.servicio_id = %(srv)s"
        params["srv"] = filters["servicio_id"]
    rows = conn.execute(
        f"""
        select s.nombre as servicio, avg(gap)::float as dias, count(*) as n from (
          select c.servicio_id, c.dia - lag(c.dia) over (partition by c.paciente_id, c.servicio_id order by c.dia) as gap, c.dia
          from cita c where c.estado='atendida' {extra}
        ) g join servicio s on s.id=g.servicio_id
        where gap is not null and dia between %(desde)s and %(hasta)s group by s.nombre order by s.nombre
        """, params).fetchall()
    return [{"servicio": r["servicio"], "dias": r["dias"], "pares": r["n"]} for r in rows]


def time_between_patient(conn, filters: dict) -> float | None:
    r = conn.execute(
        """
        select avg(gap)::float as dias from (
          select c.dia - lag(c.dia) over (partition by c.paciente_id order by c.dia) as gap, c.dia
          from cita c where c.estado='atendida') g
        where gap is not null and dia between %(desde)s and %(hasta)s
        """, {"desde": filters["desde"], "hasta": filters["hasta"]}).fetchone()
    return r["dias"]


if __name__ == "__main__":
    # `make cierre`: consolida todo el historial hasta hoy (idempotente).
    with db.connect() as conn:
        r = close_all(conn)
        if r["desde"]:
            print(f"Cierre ejecutado: {r['dias']} días consolidados ({r['desde']} a {r['hasta']}).")
        else:
            print("No hay citas que consolidar.")
