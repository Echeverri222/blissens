"""Usuarios, contraseñas, sesiones y bloqueo por intentos fallidos (PRD #2 §6.4).

Excepción deliberada a la regla del reloj único: sesiones y bloqueos usan la hora REAL, para que adelantar
el reloj en una demo no cierre la sesión de todos.
"""
import argparse
import base64
import getpass
import hashlib
import hmac
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

from . import config, db, permisos, settings

ROLES = ("auxiliar", "especialista")
MIN_CLAVE = 8
MAX_CLAVE = 128
DEMO_CLAVE = "demo-blissens"  # solo para usuarios creados junto con los datos ficticios
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


class CredencialesInvalidas(Exception):
    pass


class InicioBloqueado(Exception):
    def __init__(self, hasta: datetime):
        super().__init__("Demasiados intentos fallidos")
        self.hasta = hasta


class ClaveInvalida(ValueError):
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
    if len(clave) > MAX_CLAVE:
        raise ClaveInvalida(f"La contraseña no puede superar {MAX_CLAVE} caracteres")


#
# `usuario` es de la plataforma (nombre de usuario, contraseña, bloqueo). El rol, el profesional y la capacidad de
# administrar son del ACCESO de ese usuario a un negocio (PRD #4, D9).

class ClaveDeOtroNegocio(Exception):
    """El usuario tiene acceso a otro negocio: su contraseña solo la cambia él o el operador."""


class UltimoAdministrador(Exception):
    """No se puede dejar un negocio sin ningún administrador."""


def _negocio_activo(conn) -> int:
    n = conn.execute("select negocio_activo() n").fetchone()["n"]
    if n is None:
        raise UsuarioInvalido("No hay un negocio activo")
    return n


def _validar_acceso(conn, rol: str, profesional_id: int | None, excepto_acceso: int | None = None) -> None:
    if rol not in ROLES:
        raise UsuarioInvalido("El rol debe ser auxiliar o especialista")
    if (rol == "especialista") != (profesional_id is not None):
        raise UsuarioInvalido("Un especialista debe estar ligado a un profesional y una auxiliar no")
    if profesional_id is None:
        return
    if not conn.execute("select 1 from profesional where id=%s", (profesional_id,)).fetchone():
        raise UsuarioInvalido("No existe ese profesional")
    if conn.execute("select 1 from acceso where profesional_id=%s and id is distinct from %s",
                    (profesional_id, excepto_acceso)).fetchone():
        raise UsuarioInvalido("Ese profesional ya tiene un usuario")


def crear(conn, nombre_usuario: str, nombre: str, clave: str, rol: str, profesional_id: int | None = None,
          administrador: bool = False) -> int:
    """Crea un usuario de la plataforma y su acceso al negocio activo. Devuelve el id del usuario."""
    nombre_usuario = nombre_usuario.strip()
    if rol not in ROLES:
        raise UsuarioInvalido("El rol debe ser auxiliar o especialista")
    if not nombre_usuario or not nombre.strip():
        raise UsuarioInvalido("Faltan el usuario o el nombre visible")
    if (rol == "especialista") != (profesional_id is not None):
        raise UsuarioInvalido("Un especialista debe estar ligado a un profesional y una auxiliar no")
    _validar_acceso(conn, rol, profesional_id)
    if conn.execute("select existe_usuario(%s) e", (nombre_usuario,)).fetchone()["e"]:
        raise UsuarioInvalido("Ya existe un usuario con ese nombre")
    validar_clave(clave)
    uid = conn.execute("select crear_usuario(%s,%s,%s) id", (nombre_usuario, nombre.strip(), hash_clave(clave))).fetchone()["id"]
    conn.execute("insert into acceso(usuario_id, rol, profesional_id, administrador) values (%s,%s,%s,%s)",
                 (uid, rol, profesional_id, administrador))
    return uid


def dar_acceso(conn, nombre_usuario: str, rol: str, profesional_id: int | None = None, administrador: bool = False) -> int:
    """Da (o reactiva y actualiza) el acceso de un usuario YA existente al negocio activo."""
    _validar_acceso(conn, rol, profesional_id)
    u = conn.execute("select * from ingreso_usuario(%s)", (nombre_usuario.strip(),)).fetchone()
    if u is None:
        raise UsuarioInvalido("No existe ese usuario")
    existente = conn.execute("select id from acceso where usuario_id=%s", (u["id"],)).fetchone()
    if existente:
        _validar_acceso(conn, rol, profesional_id, existente["id"])
        conn.execute("update acceso set rol=%s, profesional_id=%s, administrador=%s, activo=true where id=%s",
                     (rol, profesional_id, administrador, existente["id"]))
        return existente["id"]
    return conn.execute("insert into acceso(usuario_id, rol, profesional_id, administrador) values (%s,%s,%s,%s) returning id",
                        (u["id"], rol, profesional_id, administrador)).fetchone()["id"]


def crear_demo(conn) -> list[dict]:
    """Una auxiliar (que administra) y un especialista por profesional, con la contraseña de demostración."""
    out = []

    def alta(usuario, nombre, rol, profesional=None, administrador=False):
        if conn.execute("select existe_usuario(%s) e", (usuario,)).fetchone()["e"]:  # recarga de la semilla
            dar_acceso(conn, usuario, rol, profesional, administrador)
        else:
            crear(conn, usuario, nombre, DEMO_CLAVE, rol, profesional, administrador)

    alta("auxiliar", "Auxiliar de demostración", "auxiliar", administrador=True)
    out.append({"usuario": "auxiliar", "rol": "auxiliar", "clave": DEMO_CLAVE})
    for i, p in enumerate(conn.execute("select id, nombre from profesional order by id").fetchall(), start=1):
        alta(f"especialista{i}", p["nombre"], "especialista", p["id"])
        out.append({"usuario": f"especialista{i}", "rol": "especialista", "clave": DEMO_CLAVE})
    return out


def listar(conn) -> list[dict]:
    return conn.execute(
        "select a.id as acceso_id, u.id, u.nombre_usuario, u.nombre, a.rol, a.activo, a.administrador, a.profesional_id, "
        "u.ultimo_acceso, u.bloqueado_hasta from acceso a join usuario u on u.id=a.usuario_id order by a.id").fetchall()


def _acceso_por_nombre(conn, nombre_usuario: str) -> dict:
    a = conn.execute(
        "select a.*, u.nombre_usuario from acceso a join usuario u on u.id=a.usuario_id "
        "where lower(u.nombre_usuario)=lower(%s)", (nombre_usuario.strip(),)).fetchone()
    if a is None:
        raise UsuarioInvalido("No existe ese usuario")
    return a


def _administradores_restantes(conn, excepto_acceso: int) -> int:
    return conn.execute("select count(*) n from acceso where administrador and activo and id<>%s",
                        (excepto_acceso,)).fetchone()["n"]


def desactivar(conn, nombre_usuario: str) -> None:
    """Quita el acceso al negocio activo: pierde ese acceso de inmediato; su usuario y sus otros accesos no se tocan."""
    a = _acceso_por_nombre(conn, nombre_usuario)
    if a["administrador"] and a["activo"] and _administradores_restantes(conn, a["id"]) == 0:
        raise UltimoAdministrador("No se puede desactivar al último administrador")
    conn.execute("update acceso set activo=false where id=%s", (a["id"],))


def activar(conn, nombre_usuario: str) -> None:
    a = _acceso_por_nombre(conn, nombre_usuario)
    conn.execute("update acceso set activo=true where id=%s", (a["id"],))
    conn.execute("update usuario set intentos_fallidos=0, bloqueado_hasta=null where id=%s", (a["usuario_id"],))


def restablecer_clave(conn, nombre_usuario: str, clave: str, temporal: bool = False) -> None:
    validar_clave(clave)
    a = _acceso_por_nombre(conn, nombre_usuario)
    if conn.execute("select otros_accesos(%s, %s) n", (a["usuario_id"], a["negocio_id"])).fetchone()["n"]:
        raise ClaveDeOtroNegocio("Esa persona tiene acceso a otro negocio: la cambia ella misma o el operador")
    conn.execute("update usuario set clave_hash=%s, intentos_fallidos=0, bloqueado_hasta=null, debe_cambiar_clave=%s "
                 "where id=%s", (hash_clave(clave), temporal, a["usuario_id"]))
    _cerrar_sesiones_de(conn, a["usuario_id"])


def clave_temporal() -> str:
    """Contraseña temporal legible; quien la recibe debe cambiarla al primer ingreso."""
    alfabeto = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alfabeto) for _ in range(4)) for _ in range(3))


def nombre_de_acceso(conn, acceso_id: int) -> str:
    r = conn.execute("select u.nombre_usuario from acceso a join usuario u on u.id=a.usuario_id where a.id=%s",
                     (acceso_id,)).fetchone()
    if r is None:
        raise permisos.NoExiste("No existe ese usuario en este negocio")
    return r["nombre_usuario"]


def actualizar_acceso(conn, acceso_id: int, rol: str, profesional_id: int | None, administrador: bool) -> None:
    a = conn.execute("select * from acceso where id=%s", (acceso_id,)).fetchone()
    if a is None:
        raise permisos.NoExiste("No existe ese usuario en este negocio")
    _validar_acceso(conn, rol, profesional_id, acceso_id)
    if a["administrador"] and a["activo"] and not administrador and _administradores_restantes(conn, acceso_id) == 0:
        raise UltimoAdministrador("No se puede quitar el rol al último administrador")
    conn.execute("update acceso set rol=%s, profesional_id=%s, administrador=%s where id=%s",
                 (rol, profesional_id, administrador, acceso_id))


def marcar_clave_temporal(conn, usuario_id: int) -> None:
    conn.execute("update usuario set debe_cambiar_clave=true where id=%s", (usuario_id,))


def _cerrar_sesiones_de(conn, usuario_id: int, excepto_huella: str = "") -> None:
    """Las sesiones son del usuario: se borran con su contexto, no con el del administrador."""
    activo = conn.execute("select usuario_activo() u").fetchone()["u"]
    negocio = conn.execute("select negocio_activo() n").fetchone()["n"]
    db.fijar(conn, negocio, usuario_id)
    conn.execute("delete from sesion where usuario_id=%s and huella <> %s", (usuario_id, excepto_huella))
    db.fijar(conn, negocio, activo)


# ----------------------------------------------------------------- sesión

def _huella(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _accesos_vigentes(conn, usuario_id: int) -> list[dict]:
    return conn.execute(
        "select a.id as acceso_id, a.negocio_id, a.rol, a.profesional_id, a.administrador, n.nombre_corto, n.nombre, "
        "n.zona_horaria from acceso a join negocio n on n.id=a.negocio_id "
        "where a.usuario_id=%s and a.activo and n.activo order by n.id", (usuario_id,)).fetchall()


def _con_acceso(u: dict, a: dict | None) -> dict:
    """El usuario tal como lo ve el resto del sistema: sus datos y el rol del acceso activo."""
    base = {"id": u["id"], "nombre_usuario": u["nombre_usuario"], "nombre": u["nombre"],
            "debe_cambiar_clave": u["debe_cambiar_clave"], "negocio_id": None, "rol": None, "profesional_id": None,
            "administrador": False}
    if a:
        base.update(negocio_id=a["negocio_id"], rol=a["rol"], profesional_id=a["profesional_id"],
                    administrador=a["administrador"])
    return base


def iniciar_sesion(conn, nombre_usuario: str, clave: str) -> tuple[str, dict]:
    """Devuelve (token de la cookie, usuario). El mensaje de fallo es el mismo exista o no el usuario.

    Con un solo acceso vigente la sesión nace con ese negocio activo; con varios, sin negocio (hay que elegir).
    """
    ahora = _ahora()
    u = conn.execute("select * from ingreso_usuario(%s)", (nombre_usuario.strip(),)).fetchone()
    if u is None or not u["activo"]:
        verificar_clave(clave, _FALSO)  # tiempo comparable
        raise CredencialesInvalidas("Usuario o contraseña incorrectos")
    db.fijar(conn, None, u["id"])
    u = conn.execute("select * from usuario where id=%s for update", (u["id"],)).fetchone()
    if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora:
        verificar_clave(clave, _FALSO)
        raise InicioBloqueado(u["bloqueado_hasta"])
    if not verificar_clave(clave, u["clave_hash"]):
        fallos = (0 if u["bloqueado_hasta"] else u["intentos_fallidos"]) + 1  # un bloqueo vencido reinicia la cuenta
        if fallos >= config.plataforma("max_intentos_login"):
            hasta = ahora + timedelta(minutes=config.plataforma("bloqueo_login_min"))
            conn.execute("update usuario set intentos_fallidos=0, bloqueado_hasta=%s where id=%s", (hasta, u["id"]))
            conn.commit()  # el bloqueo debe persistir aunque la petición termine en error
            raise InicioBloqueado(hasta)
        conn.execute("update usuario set intentos_fallidos=%s, bloqueado_hasta=null where id=%s", (fallos, u["id"]))
        conn.commit()
        raise CredencialesInvalidas("Usuario o contraseña incorrectos")
    accesos = _accesos_vigentes(conn, u["id"])
    if not accesos:
        raise CredencialesInvalidas("Usuario o contraseña incorrectos")
    activo = accesos[0] if len(accesos) == 1 else None
    token = secrets.token_urlsafe(32)
    conn.execute("update usuario set intentos_fallidos=0, bloqueado_hasta=null, ultimo_acceso=%s where id=%s",
                 (ahora, u["id"]))
    conn.execute("insert into sesion(huella, usuario_id, creada_en, vence_en, negocio_id) values (%s,%s,%s,%s,%s)",
                 (_huella(token), u["id"], ahora, ahora + timedelta(hours=config.plataforma("sesion_horas")),
                  activo["negocio_id"] if activo else None))
    conn.execute("delete from sesion where vence_en < %s", (ahora,))  # limpieza oportunista (de este usuario)
    db.fijar(conn, activo["negocio_id"] if activo else None, u["id"])
    return token, _con_acceso(u, activo)


def usuario_de_sesion(conn, token: str | None, extender: bool = True) -> dict | None:
    """Usuario de una sesión vigente (y la renueva con el uso si `extender` es True), con el negocio activo fijado.

    None si no existe, venció (por inactividad o por tope absoluto `sesion_max_horas`), el usuario está inactivo o perdió el acceso.
    """
    if not token:
        return None
    ahora = _ahora()
    h = _huella(token)
    s = conn.execute("select * from sesion_de_huella(%s,%s)", (h, ahora)).fetchone()
    if s is None:
        return None
    db.fijar(conn, s["negocio_id"], s["usuario_id"])
    ses = conn.execute("select creada_en from sesion where huella=%s", (h,)).fetchone()
    max_h = config.plataforma("sesion_max_horas")
    if ses is None or ses["creada_en"] + timedelta(hours=max_h) <= ahora:
        conn.execute("delete from sesion where huella=%s", (h,))
        db.fijar(conn, None, None)
        return None
    u = conn.execute("select * from usuario where id=%s", (s["usuario_id"],)).fetchone()
    a = None
    if s["negocio_id"] is not None:
        a = next((x for x in _accesos_vigentes(conn, u["id"]) if x["negocio_id"] == s["negocio_id"]), None)
        if a is None:  # perdió el acceso (o el negocio se desactivó): la sesión ya no sirve
            conn.execute("delete from sesion where huella=%s", (h,))
            db.fijar(conn, None, None)
            return None
    if extender:
        tope = ses["creada_en"] + timedelta(hours=max_h)
        nuevo_vence = min(ahora + timedelta(hours=config.plataforma("sesion_horas")), tope)
        conn.execute("update sesion set vence_en=%s where huella=%s", (nuevo_vence, h))
    return _con_acceso(u, a)


def elegir_negocio(conn, token: str, usuario_id: int, negocio_id: int) -> dict:
    """Cambia el negocio activo de la sesión. Exige un acceso vigente; si no, el negocio se trata como desconocido."""
    a = next((x for x in _accesos_vigentes(conn, usuario_id) if x["negocio_id"] == negocio_id), None)
    if a is None:
        raise NegocioDesconocido("No tienes acceso a ese negocio")
    conn.execute("update sesion set negocio_id=%s where huella=%s", (negocio_id, _huella(token)))
    db.fijar(conn, negocio_id, usuario_id)
    u = conn.execute("select * from usuario where id=%s", (usuario_id,)).fetchone()
    return _con_acceso(u, a)


class NegocioDesconocido(Exception):
    pass


def cerrar_sesion(conn, token: str | None) -> None:
    if token:
        conn.execute("delete from sesion where huella=%s", (_huella(token),))


def cambiar_clave(conn, usuario_id: int, actual: str, nueva: str, token_actual: str | None) -> None:
    """Cambia la contraseña propia y cierra las demás sesiones del usuario (la actual se conserva)."""
    u = conn.execute("select * from usuario where id=%s for update", (usuario_id,)).fetchone()
    if not verificar_clave(actual, u["clave_hash"]):
        raise CredencialesInvalidas("La contraseña actual no es correcta")
    validar_clave(nueva)
    if nueva == actual:
        raise ClaveInvalida("La nueva contraseña debe ser distinta a la actual")
    if settings.ENTORNO == "produccion" and nueva == DEMO_CLAVE:
        raise ClaveInvalida("No se puede usar la contraseña de demostración en producción")
    conn.execute("update usuario set clave_hash=%s, debe_cambiar_clave=false where id=%s", (hash_clave(nueva), usuario_id))
    conn.execute("delete from sesion where usuario_id=%s and huella <> %s", (usuario_id, _huella(token_actual or "")))


# ----------------------------------------------------------------- terminal (`make usuario`)

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="make usuario ARGS=", description="Administración de usuarios y accesos (operador)")
    ap.add_argument("--negocio", default=os.environ.get("NEGOCIO") or settings.NEGOCIO_POR_DEFECTO,
                    help="nombre corto del negocio (por defecto, NEGOCIO o el negocio por defecto)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crear", help="crear un usuario con acceso al negocio")
    c.add_argument("usuario")
    c.add_argument("--nombre", required=True, help="nombre visible")
    c.add_argument("--rol", required=True, choices=ROLES)
    c.add_argument("--profesional", type=int, help="id del profesional (obligatorio para especialista)")
    c.add_argument("--administrador", action="store_true")
    c.add_argument("--clave", help="si se omite, se pide por terminal")
    ac = sub.add_parser("acceso", help="dar (o actualizar) el acceso de un usuario existente al negocio")
    ac.add_argument("usuario")
    ac.add_argument("--rol", required=True, choices=ROLES)
    ac.add_argument("--profesional", type=int)
    ac.add_argument("--administrador", action="store_true")
    sub.add_parser("listar", help="listar los accesos del negocio")
    for name, hlp in (("desactivar", "quitar el acceso al negocio"), ("quitar-acceso", "igual que desactivar"),
                      ("activar", "reactivar el acceso"), ("clave", "cambiar la contraseña (cierra sus sesiones)")):
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
        with db.connect_admin() as conn:  # el operador trabaja con el rol de administración
            nid = db.negocio_id_de(conn, a.negocio)
            if nid is None:
                raise SystemExit(f"No existe el negocio '{a.negocio}'")
            db.fijar(conn, nid)
            if a.cmd == "crear":
                crear(conn, a.usuario, a.nombre, pedir(), a.rol, a.profesional, a.administrador)
                print(f"Usuario '{a.usuario}' creado ({a.rol}) en '{a.negocio}'.")
            elif a.cmd == "acceso":
                dar_acceso(conn, a.usuario, a.rol, a.profesional, a.administrador)
                print(f"Acceso de '{a.usuario}' a '{a.negocio}' guardado ({a.rol}).")
            elif a.cmd == "listar":
                for u in listar(conn):
                    print(f"{u['id']:>3}  {u['nombre_usuario']:<18} {u['rol']:<13} profesional={u['profesional_id'] or '-':<4} "
                          f"{'admin ' if u['administrador'] else '      '}{'activo' if u['activo'] else 'SIN ACCESO'}  {u['nombre']}")
            elif a.cmd in ("desactivar", "quitar-acceso"):
                desactivar(conn, a.usuario)
                print(f"'{a.usuario}' ya no tiene acceso a '{a.negocio}'.")
            elif a.cmd == "activar":
                activar(conn, a.usuario)
                print(f"Acceso de '{a.usuario}' reactivado.")
            elif a.cmd == "clave":
                restablecer_clave(conn, a.usuario, pedir())
                print(f"Contraseña de '{a.usuario}' cambiada; sus sesiones se cerraron.")
            conn.commit()
    except (UsuarioInvalido, ClaveInvalida, UltimoAdministrador, ClaveDeOtroNegocio) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
