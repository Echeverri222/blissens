"""Herramientas solo del perfil `operador` (sesión local del desarrollador, PRD asistente §8): `esquema` y `consulta_sql`.

Son una puerta abierta a toda la base del negocio activo, por eso solo existen con `ENTORNO=local` y datos ficticios.
Lo que devuelven no pasa por el filtro de datos personales de las demás herramientas: nunca con datos reales.
"""
import re

from pydantic import Field

from .base import LECTURA, Entrada, ErrorHerramienta, herramienta

OPERADOR = ("operador",)
MAX_FILAS_SQL = 200
TIEMPO_SQL = "5s"
# `select set_config('app.negocio_id', ...)` cambiaría el negocio de la conexión y con él lo que RLS deja ver.
PROHIBIDAS = re.compile(r"\b(set_config|pg_sleep_until|dblink\w*|lo_\w+|pg_read_\w+)\b", re.I)


class Esquema(Entrada):
    tabla: str | None = Field(None, max_length=63, description="Una tabla, para ver sus columnas. Sin ella, la lista de tablas.")


@herramienta("esquema", "Las tablas de la base y, dado el nombre de una, sus columnas con su tipo.", Esquema, OPERADOR, LECTURA)
def esquema(conn, actor, a: Esquema) -> dict:
    if a.tabla is None:
        return {"tablas": [r["table_name"] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE' "
            "order by 1")]}
    cols = conn.execute("select column_name, data_type from information_schema.columns where table_schema='public' "
                        "and table_name=%s order by ordinal_position", (a.tabla,)).fetchall()
    if not cols:
        raise ErrorHerramienta("no_existe", "No existe esa tabla.")
    return {"tabla": a.tabla, "columnas": [{"nombre": c["column_name"], "tipo": c["data_type"]} for c in cols]}


class ConsultaSql(Entrada):
    sql: str = Field(min_length=1, max_length=2000, description="Un solo `select` (o `with ... select`), sin punto y coma intermedio.")


def validar_sql(sql: str) -> str:
    """Un solo `select`. La barrera real es la transacción de solo lectura; esto da un mensaje claro y cierra lo evidente."""
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise ErrorHerramienta("datos_invalidos", "Solo se permite una sentencia por llamada.")
    if not re.match(r"(select|with)\b", s, re.I):
        raise ErrorHerramienta("datos_invalidos", "Solo se permite un `select`.")
    if PROHIBIDAS.search(s):
        raise ErrorHerramienta("datos_invalidos", "Esa consulta usa una función que no se permite.")
    return s


@herramienta("consulta_sql", f"Ejecuta un `select` de solo lectura sobre la base del negocio (máximo {MAX_FILAS_SQL} filas, {TIEMPO_SQL} de tiempo).",
             ConsultaSql, OPERADOR, LECTURA)
def consulta_sql(conn, actor, a: ConsultaSql) -> dict:
    s = validar_sql(a.sql)
    # El despachador ya abrió una transacción de solo lectura; el tiempo se limita solo a esta.
    conn.execute(f"set local statement_timeout = '{TIEMPO_SQL}'")
    try:
        with conn.cursor() as cur:
            cur.execute(s)
            filas = cur.fetchmany(MAX_FILAS_SQL + 1)
    except Exception as e:  # el mensaje de la base es lo que el desarrollador necesita para corregir su consulta
        conn.rollback()
        raise ErrorHerramienta("datos_invalidos", f"La consulta falló: {str(e).splitlines()[0]}") from None
    return {"filas": filas[:MAX_FILAS_SQL], "hay_mas": len(filas) > MAX_FILAS_SQL}
