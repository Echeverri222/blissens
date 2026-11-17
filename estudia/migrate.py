"""Aplica migraciones versionadas de /migrations."""
import sys

from . import db, settings

MIGRATIONS = settings.ROOT / "migrations"


def run(url: str | None = None) -> list[str]:
    applied = []
    with db.connect(url) as conn:
        conn.execute("create table if not exists migracion (nombre text primary key, aplicada_en timestamptz default now())")
        done = {r["nombre"] for r in conn.execute("select nombre from migracion")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            conn.execute(f.read_text())
            conn.execute("insert into migracion(nombre) values (%s)", (f.name,))
            applied.append(f.name)
    return applied


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else None
    ap = run(url)
    print("Migraciones aplicadas:", ", ".join(ap) if ap else "ninguna (al día)")
