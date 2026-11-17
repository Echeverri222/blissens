"""Alta y gestión de negocios (la hace el operador, con el rol de administración)."""
import argparse
import json
import re
import sys

from . import catalog, config, db, usuarios


class NegocioInvalido(Exception):
    pass


def crear(admin, nombre_corto: str, nombre: str, zona_horaria: str = "America/Bogota", direccion: str | None = None) -> int:
    """Crea el negocio con los motivos y plantillas del producto. `admin` es una conexión del rol de administración."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", nombre_corto):
        raise NegocioInvalido("El nombre corto solo admite minúsculas, números y guiones")
    if admin.execute("select 1 from negocio where nombre_corto=%s", (nombre_corto,)).fetchone():
        raise NegocioInvalido("Ya existe un negocio con ese nombre corto")
    try:
        admin.execute("select now() at time zone %s", (zona_horaria,))
    except Exception as e:
        admin.rollback()
        raise NegocioInvalido("Zona horaria desconocida") from e
    nid = admin.execute("insert into negocio(nombre_corto, nombre, zona_horaria) values (%s,%s,%s) returning id",
                        (nombre_corto, nombre, zona_horaria)).fetchone()["id"]
    db.fijar(admin, nid)
    catalog.load(admin)
    config.set_(admin, "direccion", direccion or f"{nombre}, dirección por definir")
    return nid


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="make negocio ARGS=")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crear")
    c.add_argument("nombre_corto")
    c.add_argument("--nombre", required=True)
    c.add_argument("--zona-horaria", default="America/Bogota")
    c.add_argument("--direccion")
    c.add_argument("--admin", required=True, help="usuario que administrará (se crea con --clave si no existe)")
    c.add_argument("--clave")
    sub.add_parser("listar")
    for n in ("activar", "desactivar"):
        sub.add_parser(n).add_argument("nombre_corto")
    k = sub.add_parser("config")
    k.add_argument("nombre_corto")
    k.add_argument("clave")
    k.add_argument("valor", help="JSON (por ejemplo 48, \"07:00\" o [48,24])")
    a = ap.parse_args(argv)
    with db.connect_admin() as admin:
        try:
            if a.cmd == "crear":
                nid = crear(admin, a.nombre_corto, a.nombre, a.zona_horaria, a.direccion)
                if admin.execute("select existe_usuario(%s) e", (a.admin,)).fetchone()["e"]:
                    usuarios.dar_acceso(admin, a.admin, "auxiliar", None, True)
                else:
                    if not a.clave:
                        raise SystemExit("El usuario no existe: indica --clave para crearlo")
                    usuarios.crear(admin, a.admin, a.admin, a.clave, "auxiliar", None, True)
                admin.commit()
                print(f"Negocio '{a.nombre_corto}' creado (id {nid}); administra '{a.admin}'. Agenda: /n/{a.nombre_corto}/agendar")
            elif a.cmd == "listar":
                for n in admin.execute("select * from negocio order by id"):
                    print(f"{n['id']:>3} {n['nombre_corto']:<16} {n['zona_horaria']:<20} {'activo' if n['activo'] else 'INACTIVO'}  {n['nombre']}")
            elif a.cmd in ("activar", "desactivar"):
                if not admin.execute("update negocio set activo=%s where nombre_corto=%s returning id",
                                     (a.cmd == "activar", a.nombre_corto)).fetchone():
                    raise SystemExit("No existe ese negocio")
                admin.commit()
                print(f"Negocio '{a.nombre_corto}' {a.cmd}do.")
            elif a.cmd == "config":
                n = admin.execute("select id from negocio where nombre_corto=%s", (a.nombre_corto,)).fetchone()
                if not n:
                    raise SystemExit("No existe ese negocio")
                if a.clave not in config.DEFAULTS:
                    raise SystemExit(f"Clave desconocida: {a.clave}")
                db.fijar(admin, n["id"])
                config.set_(admin, a.clave, json.loads(a.valor))
                admin.commit()
                print(f"{a.nombre_corto}: {a.clave} = {a.valor}")
        except (NegocioInvalido, usuarios.UsuarioInvalido) as e:
            admin.rollback()
            sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
