"""Comprobaciones de arranque según el entorno (PRD #4, §6.4). Fuera de `local`, ante la duda, no arranca."""
from urllib.parse import parse_qs, urlparse

from . import db, settings, usuarios

_SSLMODES_FUERTES = {"require", "verify-ca", "verify-full"}


def _sslmode_fuerte(url: str) -> bool:
    modos = [m.strip().lower() for m in parse_qs(urlparse(url).query).get("sslmode", [])]
    return len(modos) == 1 and modos[0] in _SSLMODES_FUERTES


def usuarios_con_clave_demo(conn) -> list[str]:
    """Devuelve los nombres de usuarios activos con acceso activo que aún usan la contraseña de demostración."""
    prev_neg = conn.execute("select negocio_activo() n").fetchone()["n"]
    prev_usr = conn.execute("select usuario_activo() u").fetchone()["u"]
    negocios = [r["id"] for r in conn.execute("select id from negocios_activos()").fetchall()]
    encontrados: dict[int, str] = {}
    try:
        for nid in negocios:
            db.fijar(conn, nid)
            filas = conn.execute(
                "select distinct u.id, u.nombre_usuario, u.clave_hash "
                "from usuario u join acceso a on a.usuario_id = u.id "
                "where u.activo and a.activo"
            ).fetchall()
            for r in filas:
                if r["id"] not in encontrados and usuarios.verificar_clave(usuarios.DEMO_CLAVE, r["clave_hash"]):
                    encontrados[r["id"]] = r["nombre_usuario"]
    finally:
        db.fijar(conn, prev_neg, prev_usr)
    return sorted(encontrados.values())


def problemas(entorno: str | None = None, conn=None) -> list[str]:
    entorno = entorno or settings.ENTORNO
    if entorno not in settings.ENTORNOS:
        return [f"ENTORNO desconocido: {entorno} (local, demo o produccion)"]
    if entorno == "local":
        return []
    out = []
    if settings.SECRET_KEY == settings.SECRET_KEY_POR_DEFECTO:
        out.append("SECRET_KEY tiene el valor por defecto")
    if not settings.BASE_URL.startswith("https"):
        out.append("BASE_URL debe empezar por https")
    if not _sslmode_fuerte(settings.DATABASE_URL):
        out.append("DATABASE_URL debe exigir TLS fuerte (sslmode=require, verify-ca o verify-full)")
    propia = conn is None
    if propia:
        conn = db.connect(negocio=None)
    try:
        r = conn.execute("select rolsuper or rolbypassrls as priv from pg_roles where rolname=current_user").fetchone()
        if r and r["priv"]:
            out.append("El rol de la base es privilegiado (superusuario o salta RLS)")
        if conn.execute("select 1 from pg_tables where schemaname='public' and tableowner=current_user limit 1").fetchone():
            out.append("El rol de la base es dueño de las tablas")
        if entorno == "produccion":
            demo = usuarios_con_clave_demo(conn)
            if demo:
                out.append("Hay usuarios activos con la contraseña de demostración: " + ", ".join(demo))
    finally:
        if propia:
            conn.close()
    return out


def exigir(entorno: str | None = None) -> None:
    p = problemas(entorno)
    if p:
        raise SystemExit("La aplicación no arranca en este entorno:\n - " + "\n - ".join(p))
