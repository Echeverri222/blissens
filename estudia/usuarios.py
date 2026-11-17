"""Usuarios, contraseñas, sesiones y bloqueo por intentos fallidos (PRD #2 §6.4).

Excepción deliberada a la regla del reloj único: sesiones y bloqueos usan la hora REAL, para que adelantar
el reloj en una demo no cierre la sesión de todos.
"""
import argparse
import base64
import getpass
import hashlib
import hmac
import secrets
import sys
from datetime import datetime, timedelta, timezone

from . import config, db

ROLES = ("auxiliar", "especialista")
MIN_CLAVE = 8
DEMO_CLAVE = "demo-blissens"  # solo para usuarios creados junto con los datos ficticios
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


class CredencialesInvalidas(Exception):
    pass


class InicioBloqueado(Exception):
    def __init__(self, hasta: datetime):
        super().__init__("Demasiados intentos fallidos")
        self.hasta = hasta


class ClaveInvalida(Exception):
    pass


class UsuarioInvalido(Exception):
    pass


def _ahora() -> datetime:
    """Hora real (UTC). Las pruebas lo sustituyen; nada más debe usar otro reloj aquí."""
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------- contraseñas

def hash_clave(clave: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(clave.encode(), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt${n}${r}${p}${}${}".format(base64.b64encode(salt).decode(), base64.b64encode(h).decode(), **_SCRYPT)


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        _, n, r, p, salt, h = guardado.split("$")
        calc = hashlib.scrypt(clave.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


_FALSO = hash_clave("relleno-contra-tiempos")


def validar_clave(clave: str) -> None:
    if len(clave) < MIN_CLAVE:
        raise ClaveInvalida(f"La contraseña debe tener al menos {MIN_CLAVE} caracteres")


# ----------------------------------------------------------------- usuarios

def crear(conn, nombre_usuario: str, nombre: str, clave: str, rol: str, profesional_id: int | None = None) -> int:
    nombre_usuario = nombre_usuario.strip()
    if rol not in ROLES:
        raise UsuarioInvalido("El rol debe ser auxiliar o especialista")
    if not nombre_usuario or not nombre.strip():
        raise UsuarioInvalido("Faltan el usuario o el nombre visible")
    if (rol == "especialista") != (profesional_id is not None):
        raise UsuarioInvalido("Un especialista debe estar ligado a un profesional y una auxiliar no")
    if profesional_id is not None and not conn.execute("select 1 from profesional where id=%s", (profesional_id,)).fetchone():
        raise UsuarioInvalido("No existe ese profesional")
    if conn.execute("select 1 from usuario where lower(nombre_usuario)=lower(%s)", (nombre_usuario,)).fetchone():
        raise UsuarioInvalido("Ya existe un usuario con ese nombre")
    if profesional_id is not None and conn.execute("select 1 from usuario where profesional_id=%s", (profesional_id,)).fetchone():
        raise UsuarioInvalido("Ese profesional ya tiene un usuario")
    validar_clave(clave)
    return conn.execute(
        "insert into usuario(nombre_usuario, nombre, clave_hash, rol, profesional_id) values (%s,%s,%s,%s,%s) returning id",
        (nombre_usuario, nombre.strip(), hash_clave(clave), rol, profesional_id)).fetchone()["id"]


def crear_demo(conn) -> list[dict]:
    """Una auxiliar y un especialista por profesional, con la contraseña de demostración."""
    out = []
    crear(conn, "auxiliar", "Auxiliar de demostración", DEMO_CLAVE, "auxiliar")
    out.append({"usuario": "auxiliar", "rol": "auxiliar", "clave": DEMO_CLAVE})
    for i, p in enumerate(conn.execute("select id, nombre from profesional order by id").fetchall(), start=1):
        crear(conn, f"especialista{i}", p["nombre"], DEMO_CLAVE, "especialista", p["id"])
        out.append({"usuario": f"especialista{i}", "rol": "especialista", "clave": DEMO_CLAVE})
    return out


def listar(conn) -> list[dict]:
    return conn.execute(
        "select u.id, u.nombre_usuario, u.nombre, u.rol, u.activo, u.profesional_id, u.ultimo_acceso, u.bloqueado_hasta "
        "from usuario u order by u.id").fetchall()


def _por_nombre(conn, nombre_usuario: str) -> dict:
    u = conn.execute("select * from usuario where lower(nombre_usuario)=lower(%s)", (nombre_usuario.strip(),)).fetchone()
    if u is None:
        raise UsuarioInvalido("No existe ese usuario")
    return u


def desactivar(conn, nombre_usuario: str) -> None:
    u = _por_nombre(conn, nombre_usuario)
    conn.execute("update usuario set activo=false where id=%s", (u["id"],))
    conn.execute("delete from sesion where usuario_id=%s", (u["id"],))  # pierde el acceso de inmediato


def activar(conn, nombre_usuario: str) -> None:
    u = _por_nombre(conn, nombre_usuario)
    conn.execute("update usuario set activo=true, intentos_fallidos=0, bloqueado_hasta=null where id=%s", (u["id"],))


def restablecer_clave(conn, nombre_usuario: str, clave: str) -> None:
    validar_clave(clave)
    u = _por_nombre(conn, nombre_usuario)
    conn.execute("update usuario set clave_hash=%s, intentos_fallidos=0, bloqueado_hasta=null where id=%s",
                 (hash_clave(clave), u["id"]))
    conn.execute("delete from sesion where usuario_id=%s", (u["id"],))


# ----------------------------------------------------------------- sesión

def _huella(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def iniciar_sesion(conn, nombre_usuario: str, clave: str) -> tuple[str, dict]:
    """Devuelve (token de la cookie, usuario). El mensaje de fallo es el mismo exista o no el usuario."""
    ahora = _ahora()
    u = conn.execute("select * from usuario where lower(nombre_usuario)=lower(%s) for update",
                     (nombre_usuario.strip(),)).fetchone()
    if u is None or not u["activo"]:
        verificar_clave(clave, _FALSO)  # tiempo comparable
        raise CredencialesInvalidas("Usuario o contraseña incorrectos")
    if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora:
        raise InicioBloqueado(u["bloqueado_hasta"])
    if not verificar_clave(clave, u["clave_hash"]):
        fallos = (0 if u["bloqueado_hasta"] else u["intentos_fallidos"]) + 1  # un bloqueo vencido reinicia la cuenta
        if fallos >= config.get(conn, "max_intentos_login"):
            hasta = ahora + timedelta(minutes=config.get(conn, "bloqueo_login_min"))
            conn.execute("update usuario set intentos_fallidos=0, bloqueado_hasta=%s where id=%s", (hasta, u["id"]))
            conn.commit()  # el bloqueo debe persistir aunque la petición termine en error
            raise InicioBloqueado(hasta)
        conn.execute("update usuario set intentos_fallidos=%s, bloqueado_hasta=null where id=%s", (fallos, u["id"]))
        conn.commit()
        raise CredencialesInvalidas("Usuario o contraseña incorrectos")
    token = secrets.token_urlsafe(32)
    conn.execute("update usuario set intentos_fallidos=0, bloqueado_hasta=null, ultimo_acceso=%s where id=%s",
                 (ahora, u["id"]))
    conn.execute("insert into sesion(huella, usuario_id, creada_en, vence_en) values (%s,%s,%s,%s)",
                 (_huella(token), u["id"], ahora, ahora + timedelta(hours=config.get(conn, "sesion_horas"))))
    conn.execute("delete from sesion where vence_en < %s", (ahora,))  # limpieza oportunista
    return token, u


def usuario_de_sesion(conn, token: str | None) -> dict | None:
    """Usuario de una sesión vigente (y la renueva con el uso). None si no existe, venció o el usuario está inactivo."""
    if not token:
        return None
    ahora = _ahora()
    h = _huella(token)
    u = conn.execute(
        "select u.id, u.nombre_usuario, u.nombre, u.rol, u.profesional_id from sesion s join usuario u on u.id=s.usuario_id "
        "where s.huella=%s and s.vence_en > %s and u.activo", (h, ahora)).fetchone()
    if u is None:
        return None
    conn.execute("update sesion set vence_en=%s where huella=%s",
                 (ahora + timedelta(hours=config.get(conn, "sesion_horas")), h))
    return u


def cerrar_sesion(conn, token: str | None) -> None:
    if token:
        conn.execute("delete from sesion where huella=%s", (_huella(token),))


def cambiar_clave(conn, usuario_id: int, actual: str, nueva: str, token_actual: str | None) -> None:
    """Cambia la contraseña propia y cierra las demás sesiones del usuario (la actual se conserva)."""
    u = conn.execute("select * from usuario where id=%s for update", (usuario_id,)).fetchone()
    if not verificar_clave(actual, u["clave_hash"]):
        raise CredencialesInvalidas("La contraseña actual no es correcta")
    validar_clave(nueva)
    conn.execute("update usuario set clave_hash=%s where id=%s", (hash_clave(nueva), usuario_id))
    conn.execute("delete from sesion where usuario_id=%s and huella <> %s", (usuario_id, _huella(token_actual or "")))


# ----------------------------------------------------------------- terminal (`make usuario`)

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="make usuario ARGS=", description="Administración de usuarios")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crear", help="crear un usuario")
    c.add_argument("usuario")
    c.add_argument("--nombre", required=True, help="nombre visible")
    c.add_argument("--rol", required=True, choices=ROLES)
    c.add_argument("--profesional", type=int, help="id del profesional (obligatorio para especialista)")
    c.add_argument("--clave", help="si se omite, se pide por terminal")
    sub.add_parser("listar", help="listar usuarios")
    for name, hlp in (("desactivar", "desactivar y cerrar sus sesiones"), ("activar", "reactivar"),
                      ("clave", "cambiar la contraseña (cierra sus sesiones)")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("usuario")
        if name == "clave":
            p.add_argument("--clave", help="si se omite, se pide por terminal")
    a = ap.parse_args(argv)

    def pedir() -> str:
        if getattr(a, "clave", None):
            return a.clave
        c1, c2 = getpass.getpass("Contraseña: "), getpass.getpass("Repite la contraseña: ")
        if c1 != c2:
            raise SystemExit("Las contraseñas no coinciden")
        return c1

    try:
        with db.connect() as conn:
            if a.cmd == "crear":
                crear(conn, a.usuario, a.nombre, pedir(), a.rol, a.profesional)
                print(f"Usuario '{a.usuario}' creado ({a.rol}).")
            elif a.cmd == "listar":
                for u in listar(conn):
                    print(f"{u['id']:>3}  {u['nombre_usuario']:<18} {u['rol']:<13} profesional={u['profesional_id'] or '-':<4} "
                          f"{'activo' if u['activo'] else 'DESACTIVADO'}  {u['nombre']}")
            elif a.cmd == "desactivar":
                desactivar(conn, a.usuario)
                print(f"Usuario '{a.usuario}' desactivado; sus sesiones se cerraron.")
            elif a.cmd == "activar":
                activar(conn, a.usuario)
                print(f"Usuario '{a.usuario}' activado.")
            elif a.cmd == "clave":
                restablecer_clave(conn, a.usuario, pedir())
                print(f"Contraseña de '{a.usuario}' cambiada; sus sesiones se cerraron.")
    except (UsuarioInvalido, ClaveInvalida) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
