"""Comprobaciones de arranque según el entorno (PRD #4, §6.4). Fuera de `local`, ante la duda, no arranca."""
from . import db, settings


def problemas(entorno: str | None = None) -> list[str]:
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
    if "sslmode=" not in settings.DATABASE_URL or "sslmode=disable" in settings.DATABASE_URL:
        out.append("DATABASE_URL debe exigir TLS (sslmode=require)")
    conn = db.connect(negocio=None)
    try:
        r = conn.execute("select rolsuper or rolbypassrls as priv from pg_roles where rolname=current_user").fetchone()
        if r and r["priv"]:
            out.append("El rol de la base es privilegiado (superusuario o salta RLS)")
        if conn.execute("select 1 from pg_tables where schemaname='public' and tableowner=current_user limit 1").fetchone():
            out.append("El rol de la base es dueño de las tablas")
    finally:
        conn.close()
    return out


def exigir(entorno: str | None = None) -> None:
    p = problemas(entorno)
    if p:
        raise SystemExit("La aplicación no arranca en este entorno:\n - " + "\n - ".join(p))
