"""Planes de tratamiento: «plan entregado», abonos y seguimiento sin cobrar (docs/prd-respuestas-clinica.md, R14).
El valor del plan es solo del panel: nunca sale en un mensaje ni en lo que ve el paciente."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from . import clock, followup, pacientes
from .lifecycle import ALIVE

DIAS_SIN_SIGUIENTE_PASO = 7
DIAS_CONVERSION = 15


class PlanInvalido(Exception):
    pass


def _momento(conn, dia: date | None) -> datetime:
    """La fecha que eligió la recepción (hoy por defecto) como momento del día en la zona del negocio."""
    ahora = clock.now(conn)
    if dia is None or dia == ahora.date():
        return ahora
    return datetime.combine(dia, time(12, 0), tzinfo=ahora.tzinfo)


def _tratamiento(conn, paciente_id: int, tratamiento_id: int) -> dict | None:
    return conn.execute("select t.*, p.etapa from tratamiento t join paciente p on p.id=t.paciente_id "
                        "where t.id=%s and t.paciente_id=%s", (tratamiento_id, paciente_id)).fetchone()


def tratamientos_de(conn, paciente_id: int) -> list[dict]:
    """Los tratamientos de la ficha con su plan y el siguiente paso (cita viva futura con ese profesional)."""
    return conn.execute(
        "select t.id, t.tipo, t.estado, t.sesiones_previstas, t.generado_en, t.plan_entregado_en, t.valor_plan, "
        "t.ultimo_abono_en, pr.nombre as profesional, "
        "(select min(lower(c.rango)) from cita c where c.paciente_id=t.paciente_id and c.profesional_id=t.profesional_id "
        " and c.estado = any(%s) and c.rango is not null and lower(c.rango) > %s) as proxima_cita "
        "from tratamiento t join profesional pr on pr.id=t.profesional_id where t.paciente_id=%s "
        "order by t.generado_en desc, t.id desc", (list(ALIVE), clock.now(conn), paciente_id)).fetchall()


def plan_entregado(conn, paciente_id: int, tratamiento_id: int, dia: date | None = None,
                   valor: int | Decimal | None = None) -> dict | None:
    """Registra la entrega del plan (fecha por defecto hoy, valor opcional) y abre su caso de acompañamiento. None si el
    tratamiento no es de ese paciente. Un prospecto no tiene tratamientos: PlanInvalido."""
    t = _tratamiento(conn, paciente_id, tratamiento_id)
    if t is None:
        return None
    if t["etapa"] == "prospecto":
        raise PlanInvalido("Un prospecto no tiene plan de tratamiento")
    if valor is not None and valor < 0:
        raise PlanInvalido("El valor del plan no puede ser negativo")
    momento = _momento(conn, dia)
    conn.execute("update tratamiento set plan_entregado_en=%s, valor_plan=%s where id=%s", (momento, valor, tratamiento_id))
    # Un plan entregado de nuevo reemplaza al caso abierto anterior: la cadencia cuenta desde la nueva entrega.
    conn.execute("update caso_seguimiento set estado='anulado', cerrado_en=%s where tratamiento_id=%s and tipo='plan' "
                 "and estado='abierto'", (clock.now(conn), tratamiento_id))
    caso = followup.open_case(conn, "plan", paciente_id, tratamiento_id=tratamiento_id)
    return {"tratamiento_id": tratamiento_id, "plan_entregado_en": momento, "valor_plan": valor, "caso_id": caso}


def registrar_abono(conn, paciente_id: int, tratamiento_id: int, dia: date | None = None) -> dict | None:
    """Registra un abono (solo la fecha: sin monto). Con un plan que aún tiene sesiones, si no hay caso `plan` abierto se
    abre uno. None si el tratamiento no es de ese paciente."""
    t = _tratamiento(conn, paciente_id, tratamiento_id)
    if t is None:
        return None
    if t["etapa"] == "prospecto":
        raise PlanInvalido("Un prospecto no tiene plan de tratamiento")
    momento = _momento(conn, dia)
    conn.execute("update tratamiento set ultimo_abono_en=%s where id=%s", (momento, tratamiento_id))
    caso = None
    if t["plan_entregado_en"] and t["estado"] == "activo":
        hechas = conn.execute("select count(*) as n from cita where tratamiento_id=%s and estado='atendida'",
                              (tratamiento_id,)).fetchone()["n"]
        if t["sesiones_previstas"] is None or hechas < t["sesiones_previstas"]:
            caso = followup.open_case(conn, "plan", paciente_id, tratamiento_id=tratamiento_id)
    return {"tratamiento_id": tratamiento_id, "ultimo_abono_en": momento, "caso_id": caso}


def sin_siguiente_paso(conn) -> list[dict]:
    """Planes entregados hace más de 7 días, sin cita posterior con ese profesional ni abono desde entonces. Primero los
    pacientes de alto valor, después el `valor_plan` más alto. No salen «No contactar» ni prospectos."""
    ahora = clock.now(conn)
    return conn.execute(
        f"select t.id as tratamiento_id, p.id as paciente_id, p.nombres || ' ' || p.apellidos as paciente, p.celular, "
        f"p.internacional, p.deportista, pr.nombre as profesional, t.plan_entregado_en, t.valor_plan, "
        f"(%(hoy)s::date - (t.plan_entregado_en at time zone %(tz)s)::date) as dias_desde_entrega "
        f"from tratamiento t join paciente p on p.id=t.paciente_id join profesional pr on pr.id=t.profesional_id "
        f"where t.plan_entregado_en is not null and t.plan_entregado_en < %(corte)s and t.estado = 'activo' "
        f"and {pacientes.SQL_CONTACTABLE} and p.etapa = 'paciente' "
        f"and (t.ultimo_abono_en is null or t.ultimo_abono_en < t.plan_entregado_en) "
        f"and not exists (select 1 from cita c where c.paciente_id=t.paciente_id and c.profesional_id=t.profesional_id "
        f"  and c.estado not in ('cancelada','reprogramada') and c.rango is not null "
        f"  and lower(c.rango) > t.plan_entregado_en) "
        f"order by (p.internacional or p.deportista) desc, t.valor_plan desc nulls last, t.plan_entregado_en",
        {"hoy": ahora.date(), "tz": str(clock.TZ), "corte": ahora - timedelta(days=DIAS_SIN_SIGUIENTE_PASO)}).fetchall()


def resumen_periodo(conn, desde: date, hasta: date) -> dict:
    """Indicador «Planes»: entregados en el periodo, % con cita o abono en los 15 días siguientes y suma de `valor_plan` de
    los que no tienen siguiente paso (solo si hay valores)."""
    ini = datetime.combine(desde, time.min, tzinfo=clock.TZ)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=clock.TZ)
    filas = conn.execute(
        "select t.valor_plan, "
        "((t.ultimo_abono_en is not null and t.ultimo_abono_en >= t.plan_entregado_en and "
        "  t.ultimo_abono_en <= t.plan_entregado_en + make_interval(days => %(d)s)) "
        " or exists (select 1 from cita c where c.paciente_id=t.paciente_id and c.profesional_id=t.profesional_id "
        "  and c.estado not in ('cancelada','reprogramada') and c.rango is not null "
        "  and lower(c.rango) > t.plan_entregado_en and lower(c.rango) <= t.plan_entregado_en + make_interval(days => %(d)s))) "
        " as con_siguiente_paso "
        "from tratamiento t join paciente p on p.id=t.paciente_id "
        "where t.plan_entregado_en >= %(ini)s and t.plan_entregado_en < %(fin)s and p.etapa = 'paciente'",
        {"d": DIAS_CONVERSION, "ini": ini, "fin": fin}).fetchall()
    entregados = len(filas)
    con = sum(1 for f in filas if f["con_siguiente_paso"])
    valores = [f["valor_plan"] for f in filas if not f["con_siguiente_paso"] and f["valor_plan"] is not None]
    return {"entregados": entregados, "con_siguiente_paso": con,
            "conversion_pct": round(100 * con / entregados, 1) if entregados else None,
            "valor_sin_siguiente_paso": int(sum(valores)) if valores else None}
