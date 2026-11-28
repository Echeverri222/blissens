"""Indicadores: hechos diarios (cierre) y consultas del tablero (PRD §6.8)."""
import json
from collections import Counter
from datetime import date, datetime, timedelta

from . import clock, config, db
from .agenda import _local
from .lifecycle import ALIVE


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
            count(*) filter (where c.estado='cancelada' and not exists (
                select 1 from cancelacion x where x.cita_id=c.id and x.canal='clinica')),
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
            where c.dia=%s and x.canal <> 'clinica' group by c.profesional_id, c.servicio_id, m.etiqueta
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
            from cupo_liberado where profesional_id=%s and (lower(rango) at time zone current_setting('TimeZone'))::date=%s
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


def _cita_filters(filters: dict, alias: str = "c") -> tuple[str, dict]:
    """Filtros de las consultas directas a `cita` (rango de fechas, profesional y servicio)."""
    params = {"desde": filters["desde"], "hasta": filters["hasta"]}
    parts = [f"{alias}.dia between %(desde)s and %(hasta)s"]
    if filters.get("profesional_id"):
        parts.append(f"{alias}.profesional_id = %(pro)s")
        params["pro"] = filters["profesional_id"]
    if filters.get("servicio_id"):
        parts.append(f"{alias}.servicio_id = %(srv)s")
        params["srv"] = filters["servicio_id"]
    return " and ".join(parts), params


def _sin_desenlace_por_dia(conn, filters: dict) -> dict[date, int]:
    """Citas pasadas del rango que siguen programadas, confirmadas o sin confirmar."""
    w, p = _cita_filters(filters)
    rows = conn.execute(
        f"select c.dia, count(*) as n from cita c where {w} and c.estado = any(%(alive)s) and c.rango is not null "
        f"and upper(c.rango) < %(now)s group by c.dia", {**p, "alive": list(ALIVE), "now": clock.now(conn)}).fetchall()
    return {r["dia"]: r["n"] for r in rows}


def _por_depurar(conn, filters: dict) -> int:
    """Citas pasadas que quedaron vivas (típico de la importación: «Confirmado» sin cerrar). Se cuentan aunque no
    tengan hora, y nunca como atendidas."""
    w, p = _cita_filters(filters)
    ahora = clock.now(conn)
    return conn.execute(
        f"select count(*) as n from cita c where {w} and c.estado = any(%(alive)s) "
        f"and ((c.rango is not null and upper(c.rango) < %(now)s) or (c.rango is null and c.dia < %(hoy)s))",
        {**p, "alive": list(ALIVE), "now": ahora, "hoy": ahora.date()}).fetchone()["n"]


def period_before(filters: dict) -> dict:
    """El periodo de igual duración que termina el día anterior a `desde`."""
    dias = (filters["hasta"] - filters["desde"]).days + 1
    hasta = filters["desde"] - timedelta(days=1)
    return {**filters, "desde": hasta - timedelta(days=dias - 1), "hasta": hasta}


def summary(conn, filters: dict, comparar: bool = False) -> dict:
    """Cifras del periodo, las metas vigentes y, con `comparar`, las del periodo anterior."""
    out = _summary(conn, filters, comparar)
    out["metas"] = config.get(conn, "metas_indicadores")
    return out


def _summary(conn, filters: dict, comparar: bool = False) -> dict:
    w, p = _where(filters)
    r = conn.execute(
        f"select coalesce(sum(citas),0) citas, coalesce(sum(atendidas),0) atendidas, coalesce(sum(no_asistio),0) no_asistio, "
        f"coalesce(sum(canceladas),0) canceladas, "
        f"coalesce(sum(con_recordatorio),0) con_rec, coalesce(sum(confirmadas_explicitas),0) conf, "
        f"coalesce(sum(cancelaciones),0) canc, coalesce(sum(cancelaciones_tardias),0) tard, "
        f"coalesce(sum(cancelaciones_recuperadas),0) recup, coalesce(sum(minutos_atendidos),0) min_at "
        f"from hecho_diario where {w}", p).fetchone()
    # La capacidad y los cupos se consolidan por profesional, no por servicio: con un servicio elegido no aplican.
    cap_aplica = not filters.get("servicio_id")
    wp, pp = _where(filters, "hp")
    cap = conn.execute(
        f"select coalesce(sum(minutos_disponibles),0) disp, coalesce(sum(cupos_liberados),0) lib, "
        f"coalesce(sum(cupos_ocupados_oferta),0) oferta, coalesce(sum(cupos_ocupados_agendamiento),0) agend, "
        f"coalesce(sum(cupos_vacios),0) vacios from hecho_diario_profesional hp where {wp}", pp).fetchone()
    min_at = r["min_at"]
    por_depurar = _por_depurar(conn, filters)
    out = {
        "citas": r["citas"], "atendidas": r["atendidas"], "no_asistio": r["no_asistio"],
        # Obsoleto: atendidas ÷ todas las citas. Se conserva por compatibilidad; la cifra vigente es `asistencia`.
        "atencion_efectiva": _ratio(r["atendidas"], r["citas"]),
        "asistencia": _ratio(r["atendidas"], r["atendidas"] + r["no_asistio"] + r["canceladas"]),
        "inasistencia": _ratio(r["no_asistio"], r["atendidas"] + r["no_asistio"]),
        "inasistencia_por_depurar": por_depurar,
        "inasistencia_con_pendientes": _ratio(r["no_asistio"] + por_depurar, r["atendidas"] + r["no_asistio"] + por_depurar),
        "cancelaciones": r["canc"], "cancelaciones_tardias": r["tard"], "cancelaciones_recuperadas": r["recup"],
        "recuperacion": _ratio(r["recup"], r["canc"]),
        "confirmacion": _ratio(r["conf"], r["con_rec"]),
        "sin_desenlace": sum(_sin_desenlace_por_dia(conn, filters).values()),
        "capacidad_aplica": cap_aplica,
        "ocupacion": _ratio(min_at, cap["disp"]) if cap_aplica else None,
        "minutos_disponibles": cap["disp"] if cap_aplica else None, "minutos_atendidos": min_at,
        "cupos_liberados": cap["lib"] if cap_aplica else None,
        "cupos_ocupados_oferta": cap["oferta"] if cap_aplica else None,
        "cupos_ocupados_agendamiento": cap["agend"] if cap_aplica else None,
        "cupos_vacios": cap["vacios"] if cap_aplica else None,
        **_resumen_dinero(lost_appointments(conn, filters)),
    }
    if comparar:
        prev = period_before(filters)
        out["desde_anterior"], out["hasta_anterior"] = prev["desde"], prev["hasta"]
        out["anterior"] = _summary(conn, prev)
    return out


def by_dimension(conn, filters: dict, dim: str) -> list[dict]:
    """Inasistencia y dinero perdido por profesional o servicio."""
    w, p = _where(filters, "h")
    col, join = ("p", "profesional p on p.id=h.profesional_id") if dim == "profesional" else \
                ("s", "servicio s on s.id=h.servicio_id")
    rows = conn.execute(
        f"select {col}.id, {col}.nombre as nombre, sum(h.atendidas) atendidas, sum(h.no_asistio) no_asistio, "
        f"sum(h.citas) citas, sum(h.canceladas) canceladas "
        f"from hecho_diario h join {join} where {w} group by {col}.id, {col}.nombre order by {col}.nombre", p).fetchall()
    perdido: dict[int, int] = {}
    for c in lost_appointments(conn, filters):
        k = c["profesional_id" if dim == "profesional" else "servicio_id"]
        perdido[k] = perdido.get(k, 0) + (c["valor"] or 0)
    return [{"id": r["id"], "nombre": r["nombre"], "atendidas": r["atendidas"], "no_asistio": r["no_asistio"],
             "citas": r["citas"], "canceladas": r["canceladas"],
             "inasistencia": _ratio(r["no_asistio"], r["atendidas"] + r["no_asistio"]),
             "valor_perdido": perdido.get(r["id"], 0)} for r in rows]


def trend(conn, filters: dict) -> list[dict]:
    w, p = _where(filters)
    rows = conn.execute(
        f"select fecha, sum(citas) citas, sum(atendidas) atendidas, sum(no_asistio) no_asistio from hecho_diario "
        f"where {w} group by fecha order by fecha", p).fetchall()
    pend = _sin_desenlace_por_dia(conn, filters)
    return [{"fecha": r["fecha"], "citas": r["citas"], "atendidas": r["atendidas"], "no_asistio": r["no_asistio"],
             "sin_desenlace": pend.get(r["fecha"], 0),
             "inasistencia": _ratio(r["no_asistio"], r["atendidas"] + r["no_asistio"])} for r in rows]


def weekly_trend(conn, filters: dict) -> list[dict]:
    """Tendencia agrupada por semana (lunes) con la inasistencia recalculada sobre la suma semanal."""
    out: dict[date, dict] = {}
    for r in trend(conn, filters):
        monday = r["fecha"] - timedelta(days=r["fecha"].weekday())
        w = out.setdefault(monday, {"fecha": monday, "citas": 0, "atendidas": 0, "no_asistio": 0, "sin_desenlace": 0})
        for k in ("citas", "atendidas", "no_asistio", "sin_desenlace"):
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
    params = {"desde": filters["desde"], "hasta": filters["hasta"]}
    extra = ""
    if filters.get("profesional_id"):
        extra += " and c.profesional_id = %(pro)s"
        params["pro"] = filters["profesional_id"]
    if filters.get("servicio_id"):
        extra += " and c.servicio_id = %(srv)s"
        params["srv"] = filters["servicio_id"]
    r = conn.execute(
        f"""
        select avg(gap)::float as dias from (
          select c.dia - lag(c.dia) over (partition by c.paciente_id order by c.dia) as gap, c.dia
          from cita c where c.estado='atendida' {extra}) g
        where gap is not null and dia between %(desde)s and %(hasta)s
        """, params).fetchone()
    return r["dias"]


# ----- Dinero perdido (PRD fase 2, R2) -----

DIAS_REAGENDA_PERDIDA = 30  # una cancelación tardía se da por recuperada si el paciente agenda ese servicio en este plazo


def lost_appointments(conn, filters: dict) -> list[dict]:
    """Citas del rango que costaron dinero: inasistencias y cancelaciones tardías que no se reagendaron.

    Cada fila trae el `valor` del servicio (None si no se ha configurado) y `motivo`: 'inasistencia' o 'tardia'."""
    w, p = _cita_filters(filters)
    return conn.execute(
        f"""
        select c.id, c.profesional_id, c.servicio_id, s.valor::bigint as valor,
               case when c.estado='no_asistio' then 'inasistencia' else 'tardia' end as motivo
        from cita c join servicio s on s.id=c.servicio_id left join cancelacion x on x.cita_id=c.id
        where {w} and (c.estado='no_asistio' or (c.estado='cancelada' and x.tardia and not exists (
            select 1 from cita n where n.paciente_id=c.paciente_id and n.servicio_id=c.servicio_id
            and n.creada_en > x.momento and n.creada_en <= x.momento + make_interval(days => %(dias)s))))
        """, {**p, "dias": DIAS_REAGENDA_PERDIDA}).fetchall()


def _resumen_dinero(citas: list[dict]) -> dict:
    por = {m: sum(c["valor"] or 0 for c in citas if c["motivo"] == m) for m in ("inasistencia", "tardia")}
    return {"valor_perdido": sum(por.values()), "valor_perdido_inasistencia": por["inasistencia"],
            "valor_perdido_tardias": por["tardia"], "citas_sin_valor": sum(1 for c in citas if c["valor"] is None)}


# ----- Metas (R3) -----

# indicador -> (límite, si es dinero). `min`: más es mejor; `max`: menos es mejor.
METAS = {"inasistencia": ("max", False), "asistencia": ("min", False), "confirmacion": ("min", False),
         "dinero_perdido": ("max", True)}


# ----- Pendientes del equipo (R5) -----

HORAS_VENCIDO = {"cierre_citas": 48, "mensajes": 48, "seguimientos": 7 * 24}
REGISTRO_PENDIENTES_DESDE = date(2026, 11, 25)  # desde esta fecha se registra quién resuelve (migración 014)
SIN_REGISTRAR = "Sin registrar"


def _percentil(vals: list[float], q: float) -> float | None:
    """Percentil con interpolación lineal (como `percentile_cont`)."""
    if not vals:
        return None
    v = sorted(vals)
    k = (len(v) - 1) * q
    i = int(k)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (k - i)


def _resumen_tiempos(horas: list[float], abiertos: list[float], kind: str) -> dict:
    return {"resueltos": len(horas), "mediana_horas": _percentil(horas, 0.5), "p90_horas": _percentil(horas, 0.9),
            "abiertos_hoy": len(abiertos), "vencidos": sum(1 for h in abiertos if h > HORAS_VENCIDO[kind])}


def pending_followthrough(conn, filters: dict) -> dict:
    """¿El equipo cierra sus pendientes? Tiempos de resolución de desenlaces, mensajes y seguimientos hechos a mano.

    El periodo se mide por el día en que se resolvió. Los abiertos son los de hoy: no dependen del rango."""
    now, tz = clock.now(conn), "current_setting('TimeZone')"
    p = {"desde": filters["desde"], "hasta": filters["hasta"], "now": now}
    cita_f, caso_f = "", ""
    for k, col in (("profesional_id", "pro"), ("servicio_id", "srv")):
        if filters.get(k):
            p[col] = filters[k]
            cita_f += f" and c.{k} = %({col})s"
            caso_f += f" and cc.{k} = %({col})s"
    horas = lambda a, b: f"(extract(epoch from ({a} - {b}))/3600)::float"  # noqa: E731
    en_rango = lambda x: f"({x} at time zone {tz})::date between %(desde)s and %(hasta)s"  # noqa: E731

    resueltos: dict[str, list[tuple[float, int | None, str | None]]] = {k: [] for k in HORAS_VENCIDO}
    # Primer desenlace de cada cita registrado por una persona y no revertido.
    for r in conn.execute(
            f"""
            select greatest(0, {horas('h.momento', 'upper(c.rango)')}) as h, h.usuario_id, u.nombre
            from historial_estado h join cita c on c.id=h.cita_id left join usuario u on u.id=h.usuario_id
            where h.estado_nuevo in ('atendida','no_asistio') and h.actor in ('auxiliar','especialista')
              and h.revierte_id is null and c.rango is not null and {en_rango('h.momento')}
              and not exists (select 1 from historial_estado r where r.revierte_id=h.id)
              and not exists (select 1 from historial_estado a where a.cita_id=h.cita_id and a.estado_nuevo in ('atendida','no_asistio')
                              and a.actor in ('auxiliar','especialista') and a.revierte_id is null
                              and not exists (select 1 from historial_estado r2 where r2.revierte_id=a.id)
                              and (a.momento, a.id) < (h.momento, h.id)){cita_f}
            """, p):
        resueltos["cierre_citas"].append((r["h"], r["usuario_id"], r["nombre"]))
    # Los mensajes no tienen profesional ni servicio: esos filtros no aplican.
    for r in conn.execute(
            f"""
            select greatest(0, {horas('m.gestionado_en', 'm.momento')}) as h, m.gestionado_por as usuario_id, u.nombre
            from mensaje m left join usuario u on u.id=m.gestionado_por
            where m.direccion='entrante' and m.gestionado_en is not null and {en_rango('m.gestionado_en')}
            """, p):
        resueltos["mensajes"].append((r["h"], r["usuario_id"], r["nombre"]))
    # Cerrados a mano: la auxiliar registró que aceptó o rechazó. Los cerrados antes de la migración 014 no traen usuario.
    for r in conn.execute(
            f"""
            select greatest(0, {horas('cs.cerrado_en', 'cs.abierto_en')}) as h, cs.cerrado_por as usuario_id, u.nombre
            from caso_seguimiento cs left join cita cc on cc.id=cs.cita_id left join usuario u on u.id=cs.cerrado_por
            where cs.estado in ('reprogramado','rechazado') and cs.cerrado_en is not null and {en_rango('cs.cerrado_en')}
              and exists (select 1 from intento i where i.caso_id=cs.id and i.canal='manual' and i.resultado in ('acepto','rechazo')){caso_f}
            """, p):
        resueltos["seguimientos"].append((r["h"], r["usuario_id"], r["nombre"]))

    abiertos = {
        "cierre_citas": [r["h"] for r in conn.execute(
            f"select {horas('%(now)s', 'upper(c.rango)')} as h from cita c where c.estado = any(%(alive)s) "
            f"and c.rango is not null and upper(c.rango) < %(now)s{cita_f}", {**p, "alive": list(ALIVE)})],
        "mensajes": [r["h"] for r in conn.execute(
            f"select {horas('%(now)s', 'm.momento')} as h from mensaje m where m.direccion='entrante' and not m.gestionado", p)],
        "seguimientos": [r["h"] for r in conn.execute(
            f"select {horas('%(now)s', 'cs.abierto_en')} as h from caso_seguimiento cs left join cita cc on cc.id=cs.cita_id "
            f"where (cs.estado='abierto' or (cs.estado='agotado' and cs.escalado)){caso_f}", p)],
    }
    out = {k: _resumen_tiempos([h for h, _, _ in resueltos[k]], abiertos[k], k) for k in HORAS_VENCIDO}
    personas: dict[int | None, dict] = {}
    for filas in resueltos.values():
        for h, uid, nombre in filas:
            d = personas.setdefault(uid, {"usuario_id": uid, "usuario": nombre, "horas": []})
            d["horas"].append(h)
    out["por_usuario"] = sorted(
        ({"usuario_id": d["usuario_id"], "usuario": d["usuario"], "resueltos": len(d["horas"]),
          "mediana_horas": _percentil(d["horas"], 0.5)} for d in personas.values()),
        key=lambda d: (d["usuario_id"] is None, -d["resueltos"]))
    out["registro_desde"] = REGISTRO_PENDIENTES_DESDE
    return out


# ----- Del cancelar al volver a agendar (R6) -----

DIAS_REAGENDAMIENTO = 60


def rebooking(conn, filters: dict) -> dict:
    """Cancelaciones del rango y cuánto tardó el paciente en agendar de nuevo (mismo profesional o mismo servicio)."""
    w, p = _cita_filters(filters)
    tz = "current_setting('TimeZone')"
    rows = conn.execute(
        f"""
        select (r.creada_en at time zone {tz})::date - (x.momento at time zone {tz})::date as dias
        from cancelacion x join cita c on c.id=x.cita_id
        left join lateral (
            select n.creada_en from cita n where n.paciente_id=c.paciente_id and n.creada_en > x.momento
            and n.creada_en <= x.momento + make_interval(days => %(max)s)
            and (n.profesional_id=c.profesional_id or n.servicio_id=c.servicio_id) order by n.creada_en limit 1) r on true
        where {w.replace('c.dia', f"(x.momento at time zone {tz})::date")}
        """, {**p, "max": DIAS_REAGENDAMIENTO}).fetchall()
    dias = [r["dias"] for r in rows if r["dias"] is not None]
    buckets = {"mismo_dia": 0, "1_3": 0, "4_14": 0, "15_60": 0, "no_reagendo": len(rows) - len(dias)}
    for d in dias:
        buckets["mismo_dia" if d == 0 else "1_3" if d <= 3 else "4_14" if d <= 14 else "15_60"] += 1
    return {"mediana_dias": _percentil([float(d) for d in dias], 0.5), "total": len(rows), "buckets": buckets}


# ----- Consultas sobre citas (detalle detrás de las cifras) -----

def repeat_no_shows(conn, filters: dict, minimo: int = 2) -> list[dict]:
    """Pacientes con al menos `minimo` inasistencias en el rango, y si ya tienen una cita futura."""
    w, p = _cita_filters(filters)
    return conn.execute(
        f"""
        select p.id as paciente_id, p.nombres || ' ' || p.apellidos as paciente, p.celular, count(*) as faltas,
               max(c.dia) as ultima_falta,
               exists (select 1 from cita f where f.paciente_id=p.id and f.estado = any(%(alive)s)
                       and f.rango is not null and lower(f.rango) > %(now)s) as tiene_cita_futura
        from cita c join paciente p on p.id=c.paciente_id
        where {w} and c.estado='no_asistio'
        group by p.id having count(*) >= %(minimo)s order by count(*) desc, max(c.dia) desc, p.id
        """, {**p, "alive": list(ALIVE), "now": clock.now(conn), "minimo": minimo}).fetchall()


def missed_appointments(conn, filters: dict, limite: int = 500) -> list[dict]:
    """Citas del rango que no asistió o canceló tarde, con si el paciente ya volvió a agendar ese servicio."""
    w, p = _cita_filters(filters)
    return conn.execute(
        f"""
        select c.id as cita_id, c.dia, lower(c.rango) as inicio, c.estado, p.id as paciente_id,
               p.nombres || ' ' || p.apellidos as paciente, pr.nombre as profesional, s.nombre as servicio,
               m.etiqueta as motivo, x.tardia as cancelacion_tardia,
               (c.estado = 'reprogramada' or exists (
                   select 1 from cita n where n.paciente_id=c.paciente_id and n.servicio_id=c.servicio_id and n.id > c.id
                   and n.estado not in ('cancelada','no_asistio','reprogramada'))) as reagendada
        from cita c join paciente p on p.id=c.paciente_id join profesional pr on pr.id=c.profesional_id
        join servicio s on s.id=c.servicio_id
        left join cancelacion x on x.cita_id=c.id left join motivo_cancelacion m on m.id=x.motivo_id
        where {w} and (c.estado='no_asistio' or (c.estado='cancelada' and x.tardia))
        order by c.dia desc, c.id desc limit %(limite)s
        """, {**p, "limite": limite}).fetchall()


def reminders(conn, filters: dict) -> dict:
    """¿Sirven los recordatorios? Inasistencia con y sin recordatorio, y el embudo del periodo."""
    w, p = _cita_filters(filters)
    grupos = {True: {"n": 0, "no_asistio": 0}, False: {"n": 0, "no_asistio": 0}}
    for r in conn.execute(
            f"select coalesce((c.datos_origen->>'recordatorio_enviado')::boolean, false) as rec, "
            f"count(*) as n, count(*) filter (where c.estado='no_asistio') as faltas "
            f"from cita c where {w} and c.estado in ('atendida','no_asistio') group by 1", p):
        grupos[r["rec"]] = {"n": r["n"], "no_asistio": r["faltas"]}
    wh, ph = _where(filters)
    e = conn.execute(
        f"select coalesce(sum(citas),0) citas, coalesce(sum(con_recordatorio),0) rec, "
        f"coalesce(sum(confirmadas_explicitas),0) conf, coalesce(sum(atendidas),0) atendidas "
        f"from hecho_diario where {wh}", ph).fetchone()
    fila = lambda g: {**g, "inasistencia": _ratio(g["no_asistio"], g["n"])}  # noqa: E731
    return {"con_recordatorio": fila(grupos[True]), "sin_recordatorio": fila(grupos[False]),
            "embudo": {"citas": e["citas"], "con_recordatorio": e["rec"], "confirmadas": e["conf"], "atendidas": e["atendidas"]}}


def weekday_hour(conn, filters: dict) -> list[dict]:
    """Atendidas y no asistió por día de la semana (0 = lunes) y hora local de inicio."""
    w, p = _cita_filters(filters)
    rows = conn.execute(
        f"""
        select (extract(isodow from lower(c.rango) at time zone current_setting('TimeZone'))::int - 1) as dia_semana,
               extract(hour from lower(c.rango) at time zone current_setting('TimeZone'))::int as hora,
               count(*) filter (where c.estado='atendida') as atendidas,
               count(*) filter (where c.estado='no_asistio') as no_asistio
        from cita c where {w} and c.rango is not null and c.estado in ('atendida','no_asistio')
        group by 1, 2 order by 1, 2
        """, p).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    # `make cierre`: consolida todo el historial hasta hoy (idempotente).
    with db.connect() as conn:
        r = close_all(conn)
        if r["desde"]:
            print(f"Cierre ejecutado: {r['dias']} días consolidados ({r['desde']} a {r['hasta']}).")
        else:
            print("No hay citas que consolidar.")
