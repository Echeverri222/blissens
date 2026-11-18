"""Conexiones a PostgreSQL. Las funciones de dominio reciben `conn` y no hacen commit.

El negocio activo (y el usuario) son ajustes de la CONEXIÓN (`app.negocio_id`, `app.usuario_id`) que las políticas de
seguridad por filas (RLS) leen; el código de dominio no menciona `negocio_id` (PRD #4, D2 y D3). Sin negocio activo,
las lecturas devuelven cero filas y las escrituras fallan.
"""
import psycopg
from psycopg.rows import dict_row

from . import settings

TZNAME = "America/Bogota"  # valor por defecto del producto; cada negocio tiene la suya en `negocio.zona_horaria`
POR_DEFECTO = object()
_ids: dict[tuple[str, str], int] = {}


def _abrir(url: str) -> psycopg.Connection:
    conn = psycopg.connect(url, row_factory=dict_row)
    conn.execute("select set_config('timezone', %s, false)", (TZNAME,))
    conn.commit()
    return conn


def connect_admin(url: str | None = None) -> psycopg.Connection:
    """Conexión del dueño del esquema: migraciones y comandos del operador. Se salta RLS; no usar en rutas web."""
    return _abrir(url or settings.DATABASE_URL_ADMIN)


def negocio_id_de(conn, nombre_corto: str) -> int | None:
    r = conn.execute("select id from negocio_de_nombre(%s)", (nombre_corto,)).fetchone()
    conn.rollback()
    return r["id"] if r else None


def fijar(conn, negocio_id: int | None, usuario_id: int | None = None) -> None:
    """Fija negocio y usuario activos y la zona horaria del negocio. Se confirma para sobrevivir a un rollback."""
    conn.execute("select set_config('app.negocio_id', %s, false), set_config('app.usuario_id', %s, false)",
                 ("" if negocio_id is None else str(negocio_id), "" if usuario_id is None else str(usuario_id)))
    zona = TZNAME
    if negocio_id is not None:
        r = conn.execute("select zona_horaria from negocio where id=%s", (negocio_id,)).fetchone()
        zona = r["zona_horaria"] if r else TZNAME
    conn.execute("select set_config('timezone', %s, false)", (zona,))
    conn.commit()


def connect(url: str | None = None, negocio=POR_DEFECTO, usuario_id: int | None = None) -> psycopg.Connection:
    """Conexión del rol de aplicación con su negocio activo.

    `negocio`: nombre corto o id; por defecto, el negocio por defecto; `None` abre la conexión sin negocio (falla cerrado).
    """
    url = url or settings.DATABASE_URL
    conn = _abrir(url)
    if negocio is None:
        return conn
    if negocio is POR_DEFECTO:
        negocio = settings.NEGOCIO_POR_DEFECTO
    if isinstance(negocio, str):
        clave = (url, negocio)
        if clave not in _ids:
            nid = negocio_id_de(conn, negocio)
            if nid is None:
                conn.close()
                raise LookupError(f"No existe el negocio '{negocio}'")
            _ids[clave] = nid
        negocio = _ids[clave]
    fijar(conn, negocio, usuario_id)
    return conn


def sin_contexto(url: str | None = None) -> psycopg.Connection:
    return connect(url, negocio=None)


def request_conn():
    """Conexión por petición web, sin negocio: el negocio sale de la sesión o de la ruta y se fija después."""
    conn = connect(negocio=None)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
