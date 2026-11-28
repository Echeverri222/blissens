"""Familia (docs/prd-familia.md): un paciente responsable gestiona las citas de sus familiares desde su propio enlace.

Un solo nivel: un familiar no tiene familiares y un responsable no es familiar de nadie. El familiar hereda el celular del
responsable, así los mensajes del hogar llegan a un solo teléfono.
"""
from datetime import date, timedelta

import psycopg

from . import clock, config

PARENTESCOS = {"hijo": "Hijo o hija", "pareja": "Pareja", "padre": "Madre o padre", "otro": "Otro familiar"}
MAXIMO = 10
MAYORIA_DE_EDAD = 18


class DatosInvalidos(Exception):
    pass


class NoSePuede(Exception):
    """El enlace no se puede crear sin revelar datos de otra persona: la clínica contacta al responsable."""


class NoEsDeLaFamilia(Exception):
    pass


VENTANA_DEDUPLICACION = timedelta(hours=24)


def solicitar_contacto(conn, documento: str, celular: str, nota: str) -> bool:
    """Deja una solicitud de contacto para la clínica, salvo que ya haya una abierta y reciente con el mismo documento,
    celular y nota (evita que repetir el formulario llene la bandeja, sin tapar la de otro celular). True si la creó."""
    ahora = clock.now(conn)
    if conn.execute("select 1 from solicitud_contacto where documento=%s and celular=%s and nota=%s and not gestionada "
                    "and momento > %s limit 1", (documento, celular, nota, ahora - VENTANA_DEDUPLICACION)).fetchone():
        return False
    conn.execute("insert into solicitud_contacto(documento, celular, nota, momento) values (%s,%s,%s,%s)",
                 (documento, celular, nota, ahora))
    return True


def edad(nacimiento: date | None, hoy: date) -> int | None:
    if nacimiento is None:
        return None
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def es_menor(nacimiento: date | None, hoy: date) -> bool:
    e = edad(nacimiento, hoy)
    return e is not None and e < MAYORIA_DE_EDAD


def familiares(conn, responsable_id: int) -> list[dict]:
    hoy = clock.now(conn).astimezone(clock.TZ).date()
    filas = conn.execute("select * from paciente where responsable_id=%s order by creado_en, id", (responsable_id,)).fetchall()
    return [{**f, "menor": es_menor(f["fecha_nacimiento"], hoy), "parentesco_texto": PARENTESCOS.get(f["parentesco"], "")}
            for f in filas]


def responsable_de(conn, paciente: dict) -> dict | None:
    if not paciente.get("responsable_id"):
        return None
    return conn.execute("select * from paciente where id=%s", (paciente["responsable_id"],)).fetchone()


def ids_del_hogar(conn, paciente: dict) -> list[int]:
    """El paciente y, si es responsable, sus familiares: de quiénes puede ver y tocar citas desde su enlace."""
    return [paciente["id"]] + [r["id"] for r in conn.execute(
        "select id from paciente where responsable_id=%s", (paciente["id"],)).fetchall()]


def hogar(conn, paciente_id: int) -> tuple[dict, list[int]]:
    """El hogar de un paciente: (responsable, ids de todos sus miembros). Comparten un celular, así que los avisos
    automáticos del hogar salen agrupados y dirigidos al responsable. Un paciente sin familia es un hogar de uno."""
    p = conn.execute("select * from paciente where id=%s", (paciente_id,)).fetchone()
    raiz = responsable_de(conn, p) or p
    return raiz, ids_del_hogar(conn, raiz)


def primer_nombre(p: dict | str | None) -> str:
    nombres = (p.get("nombres") if isinstance(p, dict) else p) or ""
    partes = nombres.split()
    return partes[0].title() if partes else ""


def sujeto(conn, paciente: dict, para: int | None) -> dict:
    """Para quién actúa el enlace: el propio paciente o uno de sus familiares. Cualquier otro id es NoEsDeLaFamilia."""
    if not para or para == paciente["id"]:
        return paciente
    f = conn.execute("select * from paciente where id=%s and responsable_id=%s", (para, paciente["id"])).fetchone()
    if f is None:
        raise NoEsDeLaFamilia()
    return f


def agregar(conn, responsable: dict, documento: str, nombres: str, apellidos: str, nacimiento: str, parentesco: str,
            consentimiento: bool) -> tuple[int, bool]:
    """Agrega un familiar nuevo o enlaza a un paciente existente. Devuelve (id, ya_estaba)."""
    if responsable.get("responsable_id"):
        r = responsable_de(conn, responsable)
        raise DatosInvalidos(f"Tu familia la gestiona {primer_nombre(r) if r else 'otra persona'}. "
                             "Pídele que agregue a esta persona.")
    documento = "".join(ch for ch in documento if ch.isdigit())
    nombres, apellidos = nombres.strip(), apellidos.strip()
    if not documento or not nombres:
        raise DatosInvalidos("Escribe el documento y los nombres de la persona.")
    if parentesco not in PARENTESCOS:
        raise DatosInvalidos("Elija el parentesco.")
    hoy = clock.now(conn).astimezone(clock.TZ).date()
    try:
        fecha = date.fromisoformat(nacimiento)
    except (TypeError, ValueError):
        raise DatosInvalidos("Escribe la fecha de nacimiento.") from None
    if fecha > hoy or fecha.year < hoy.year - 120:
        raise DatosInvalidos("Revisa la fecha de nacimiento.")
    if not consentimiento:
        raise DatosInvalidos("Para agregarla necesitamos su autorización para tratar sus datos.")
    if documento == responsable["documento"]:
        raise DatosInvalidos("Ese es su propio documento.")

    existente = conn.execute("select * from paciente where documento=%s", (documento,)).fetchone()
    if existente:
        if existente["responsable_id"] == responsable["id"]:
            return existente["id"], True
        tiene_familia = conn.execute("select 1 from paciente where responsable_id=%s limit 1", (existente["id"],)).fetchone()
        if existente["celular"] != responsable["celular"] or existente["responsable_id"] or tiene_familia:
            solicitar_contacto(conn, documento, responsable["celular"],
                               f"Un paciente (documento {responsable['documento']}) quiso agregar a este documento a su familia")
            raise NoSePuede()
    if len(familiares(conn, responsable["id"])) >= MAXIMO:
        raise DatosInvalidos(f"Puedes gestionar hasta {MAXIMO} familiares desde un enlace.")

    now = clock.now(conn)
    if existente:
        # `consentimiento_por` queda vacío a propósito: esta persona se registró y dio su propio consentimiento.
        conn.execute("update paciente set responsable_id=%s, parentesco=%s, fecha_nacimiento=coalesce(fecha_nacimiento, %s) "
                     "where id=%s", (responsable["id"], parentesco, fecha, existente["id"]))
        return existente["id"], False
    try:
        with conn.transaction():
            pid = conn.execute(
                "insert into paciente(nombres, apellidos, documento, celular, fecha_nacimiento, responsable_id, parentesco, "
                "consentimiento_en, consentimiento_version, consentimiento_por, creado_en) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                (nombres, apellidos, documento, responsable["celular"], fecha, responsable["id"], parentesco, now,
                 config.get(conn, "consentimiento_version"), responsable["id"], now)).fetchone()["id"]
    except psycopg.errors.UniqueViolation:  # doble envío del formulario: el otro ya lo creó
        otro = conn.execute("select id, responsable_id from paciente where documento=%s", (documento,)).fetchone()
        if otro and otro["responsable_id"] == responsable["id"]:
            return otro["id"], True
        raise
    return pid, False


def dejar_de_compartir(conn, familiar: dict) -> None:
    """Un familiar mayor de edad deja de ser gestionado por su responsable."""
    hoy = clock.now(conn).astimezone(clock.TZ).date()
    if es_menor(familiar["fecha_nacimiento"], hoy):
        raise DatosInvalidos("Las citas de un menor de edad las gestiona su representante.")
    conn.execute("update paciente set responsable_id=null, parentesco=null where id=%s", (familiar["id"],))


def resumen(conn, paciente_id: int) -> dict:
    """La familia de un paciente para la ficha del panel."""
    hoy = clock.now(conn).astimezone(clock.TZ).date()
    p = conn.execute("select * from paciente where id=%s", (paciente_id,)).fetchone()
    r = responsable_de(conn, p) if p else None

    def nombre(x):
        return f"{x['nombres']} {x['apellidos']}".strip()
    return {
        "responsable": {"id": r["id"], "nombre": nombre(r), "parentesco": p["parentesco"]} if r else None,
        "familiares": [{"id": f["id"], "nombre": nombre(f), "parentesco": f["parentesco"], "menor": f["menor"]}
                       for f in familiares(conn, paciente_id)] if p else [],
        "menor": es_menor(p["fecha_nacimiento"], hoy) if p else False,
    }
