"""Migrador propio sobre SQL plano (PRD #4, D6).

Cada migración es `migrations/NNN_nombre.sql`; su reversa, `NNN_nombre.down.sql`. Una migración cuya primera línea es
`-- sin-transaccion` corre fuera de transacción (por ejemplo, índices sin bloquear). Una cuya primera línea es
`-- irreversible` no tiene reversa y exige copia verificada antes de aplicarse.

Subcomandos: estado · subir · bajar [n] · verificar. Se guarda la huella de cada archivo aplicado: si cambió, falla.
"""
import hashlib
import re
import sys

from . import db, settings

MIGRATIONS = settings.ROOT / "migrations"
CLAVE_BLOQUEO = 7_340_201  # bloqueo consultivo: dos migradores no corren a la vez
ESPERA_BLOQUEOS_MS = 5000   # una migración no deja esperando a la agenda: si no consigue el bloqueo, falla y se reintenta


class MigracionModificada(Exception):
    pass


class SinReversa(Exception):
    pass


def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def archivos() -> list:
    return sorted(f for f in MIGRATIONS.glob("*.sql") if not f.name.endswith(".down.sql"))


def _reversa(f):
    return f.with_name(f.name[:-4] + ".down.sql")


def _marca(texto: str) -> str:
    primera = texto.lstrip().splitlines()[0] if texto.strip() else ""
    m = re.match(r"--\s*(sin-transaccion|irreversible)\b", primera)
    return m.group(1) if m else ""


def _preparar(conn) -> dict[str, str | None]:
    conn.execute("create table if not exists migracion (nombre text primary key, aplicada_en timestamptz default now())")
    conn.execute("alter table migracion add column if not exists huella text")
    conn.commit()
    return {r["nombre"]: r["huella"] for r in conn.execute("select nombre, huella from migracion")}


def _comprobar_huellas(conn, hechas: dict[str, str | None]) -> None:
    for f in archivos():
        if f.name not in hechas:
            continue
        h = _huella(f.read_text())
        if hechas[f.name] is None:  # base anterior al migrador nuevo: se adopta la huella actual
            conn.execute("update migracion set huella=%s where nombre=%s", (h, f.name))
            conn.commit()
        elif hechas[f.name] != h:
            raise MigracionModificada(f"La migración {f.name} ya estaba aplicada y su contenido cambió")


def _conectar(url):
    conn = db.connect_admin(url)
    conn.autocommit = False
    return conn


def _bloquear(conn) -> None:
    conn.execute("select pg_advisory_lock(%s)", (CLAVE_BLOQUEO,))
    conn.commit()


def _ejecutar(conn, texto: str, sin_tx: bool) -> None:
    if sin_tx:
        conn.autocommit = True
        try:
            conn.execute(texto)
        finally:
            conn.autocommit = False
    else:
        conn.execute(f"set local lock_timeout = {ESPERA_BLOQUEOS_MS}")
        conn.execute(texto)


def _clave_rol_app(conn) -> None:
    """En local el rol de aplicación recibe su contraseña de desarrollo; en otros entornos la fija el operador."""
    if settings.CLAVE_ROL_APP and conn.execute("select 1 from pg_roles where rolname='estudia_app'").fetchone():
        clave = conn.execute("select quote_literal(%s) q", (settings.CLAVE_ROL_APP,)).fetchone()["q"]
        conn.execute(f"alter role estudia_app password {clave}")
        conn.commit()


def run(url: str | None = None, hasta: str | None = None) -> list[str]:
    """Aplica las pendientes (en orden, una transacción por migración). Devuelve los nombres aplicados."""
    aplicadas = []
    conn = _conectar(url)
    try:
        _bloquear(conn)
        hechas = _preparar(conn)
        _comprobar_huellas(conn, hechas)
        for f in archivos():
            if f.name in hechas:
                continue
            texto = f.read_text()
            _ejecutar(conn, texto, _marca(texto) == "sin-transaccion")
            conn.execute("insert into migracion(nombre, huella) values (%s,%s)", (f.name, _huella(texto)))
            conn.commit()
            aplicadas.append(f.name)
            if hasta and f.name.startswith(hasta):
                break
        _clave_rol_app(conn)
    finally:
        conn.close()
    return aplicadas


def bajar(url: str | None = None, cuantas: int = 1) -> list[str]:
    """Deshace las últimas `cuantas` migraciones aplicadas, de la más reciente a la más antigua."""
    revertidas = []
    conn = _conectar(url)
    try:
        _bloquear(conn)
        hechas = _preparar(conn)
        _comprobar_huellas(conn, hechas)
        por_nombre = {f.name: f for f in archivos()}
        for nombre in sorted(hechas, reverse=True)[:cuantas]:
            f = por_nombre[nombre]
            rev = _reversa(f)
            if _marca(f.read_text()) == "irreversible" or not rev.exists():
                raise SinReversa(f"La migración {nombre} no tiene reversa")
            conn.execute(f"set local lock_timeout = {ESPERA_BLOQUEOS_MS}")
            conn.execute(rev.read_text())
            conn.execute("delete from migracion where nombre=%s", (nombre,))
            conn.commit()
            revertidas.append(nombre)
    finally:
        conn.close()
    return revertidas


def estado(url: str | None = None) -> list[tuple[str, str]]:
    conn = _conectar(url)
    try:
        hechas = _preparar(conn)
        out = []
        for f in archivos():
            if f.name not in hechas:
                out.append((f.name, "pendiente"))
            elif hechas[f.name] not in (None, _huella(f.read_text())):
                out.append((f.name, "MODIFICADA"))
            else:
                out.append((f.name, "aplicada"))
        return out
    finally:
        conn.close()


def verificar(url: str | None = None) -> list[str]:
    """Comprobaciones previas/posteriores; devuelve la lista de problemas (vacía si todo está bien)."""
    problemas = []
    conn = _conectar(url)
    try:
        v = conn.execute("show server_version_num").fetchone()["server_version_num"]
        if int(v) < 160000:
            problemas.append(f"Se requiere PostgreSQL 16 o superior (versión {v})")
        if not conn.execute("select 1 from pg_extension where extname='btree_gist'").fetchone():
            problemas.append("Falta la extensión btree_gist")
        hechas = _preparar(conn)
        for f in archivos():
            if f.name in hechas and hechas[f.name] not in (None, _huella(f.read_text())):
                problemas.append(f"La migración {f.name} cambió después de aplicarse")
        for t in conn.execute("select table_name from information_schema.columns "
                              "where table_schema='public' and column_name='negocio_id' and table_name <> 'sesion'").fetchall():
            n = conn.execute(f'select count(*) n from "{t["table_name"]}" where negocio_id is null').fetchone()["n"]
            if n:
                problemas.append(f"{t['table_name']}: {n} filas sin negocio")
    finally:
        conn.close()
    return problemas


def main(argv: list[str] | None = None) -> None:
    a = list(sys.argv[1:] if argv is None else argv)
    url = None
    cmd = a.pop(0) if a else "subir"
    if cmd == "subir":
        ap = run(url)
        print("Migraciones aplicadas:", ", ".join(ap) if ap else "ninguna (al día)")
    elif cmd == "bajar":
        r = bajar(url, int(a[0]) if a else 1)
        print("Migraciones revertidas:", ", ".join(r) if r else "ninguna")
    elif cmd == "estado":
        for nombre, est in estado(url):
            print(f"{est:<10} {nombre}")
    elif cmd == "verificar":
        p = verificar(url)
        print("\n".join(p) if p else "Verificaciones en verde")
        sys.exit(1 if p else 0)
    elif cmd.startswith("postgresql"):  # compatibilidad: `python -m estudia.migrate <url>`
        print("Migraciones aplicadas:", ", ".join(run(cmd)) or "ninguna (al día)")
    else:
        raise SystemExit(f"Subcomando desconocido: {cmd} (estado, subir, bajar, verificar)")


if __name__ == "__main__":
    main()
