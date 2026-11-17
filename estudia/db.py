"""Conexiones a PostgreSQL. Las funciones de dominio reciben `conn` y no hacen commit."""
import psycopg
from psycopg.rows import dict_row

from . import settings

TZNAME = "America/Bogota"


def connect(url: str | None = None) -> psycopg.Connection:
    conn = psycopg.connect(url or settings.DATABASE_URL, row_factory=dict_row)
    conn.execute(f"set timezone to '{TZNAME}'")
    conn.commit()
    return conn


def request_conn():
    """Conexión por petición web: confirma al terminar bien, deshace si algo falla."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
