import itertools
import os
from datetime import datetime, timedelta

# Las pruebas usan una base separada; se fija antes de importar el paquete. La suite corre con el ROL DE APLICACIÓN
# (sujeto a RLS); el rol de administración solo migra y vacía la base entre pruebas.
os.environ["ENTORNO"] = "local"
# Ninguna prueba llama a la API de Claude: aunque `.env` traiga la clave, aquí queda vacía (las pruebas del asistente la fingen
# en `settings` y usan un cliente falso).
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ASISTENTE_PROVEEDOR"] = "anthropic"
os.environ["ASISTENTE_MODELO"] = "claude-opus-5-5"  # las pruebas no dependen del modelo que cada quien tenga en .env
os.environ["ASISTENTE_MODELO_PACIENTE"] = ""
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://estudia_app:estudia_app@127.0.0.1:5433/estudia_test")
os.environ["DATABASE_URL_ADMIN"] = os.environ.get(
    "TEST_DATABASE_URL_ADMIN", "postgresql://estudia:estudia@127.0.0.1:5433/estudia_test")

import pytest  # noqa: E402

from estudia import agenda, catalog, clock, db, messaging, migrate  # noqa: E402

URL = os.environ["DATABASE_URL"]
ADMIN = os.environ["DATABASE_URL_ADMIN"]
NOW = datetime(2026, 11, 16, 8, 0, tzinfo=clock.TZ)  # lunes 8:00


@pytest.fixture(scope="session", autouse=True)
def _schema():
    migrate.run(ADMIN)


def vaciar():
    """Deja la base vacía (solo el negocio Blissens, tal como lo crea la migración)."""
    a = db.connect_admin(ADMIN)
    tablas = [r["table_name"] for r in a.execute(
        "select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE' "
        "and table_name not in ('negocio','migracion')")]
    a.execute("truncate " + ", ".join(tablas) + " restart identity cascade")
    a.execute("delete from negocio where id <> 1")
    a.execute("update negocio set nombre='Blissens Odontología', zona_horaria='America/Bogota', activo=true where id=1")
    a.commit()
    a.close()


@pytest.fixture
def conn():
    vaciar()
    c = db.connect(URL)
    catalog.load(c)
    c.commit()
    clock.freeze(NOW)
    yield c
    c.rollback()
    c.close()
    clock.freeze(None)


@pytest.fixture
def conn2():
    c = db.connect(URL)
    yield c
    c.rollback()
    c.close()


def at(day_offset: int, hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    d = (NOW + timedelta(days=day_offset)).replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    return d


def make_pro(conn, name="Dra. Prueba"):
    pid = conn.execute("insert into profesional(nombre, especialidad) values (%s,'General') returning id",
                       (name,)).fetchone()["id"]
    catalog.default_hours(conn, pid)
    return pid


_doc = itertools.count(1000)


def make_patient(conn, nombres="Ana", apellidos="Pérez", doc=None, acepta=True, celular="+573001112233",
                 correo=None, acepta_correo=False):
    doc = doc or str(next(_doc))
    return conn.execute(
        "insert into paciente(nombres, apellidos, documento, celular, acepta_mensajes, consentimiento_en, correo, "
        "acepta_correo, consentimiento_correo_en) values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
        (nombres, apellidos, doc, celular, acepta, NOW, correo, acepta_correo, NOW if acepta_correo else None)).fetchone()["id"]


def svc(conn, name="Valoración o revisión"):
    return conn.execute("select * from servicio where nombre=%s", (name,)).fetchone()["id"]


def book(conn, patient, pro, start, service="Valoración o revisión", **kw):
    return agenda.book(conn, patient, pro, svc(conn, service), start, "auxiliar", "auxiliar", **kw)


def status(conn, cita_id):
    return conn.execute("select estado from cita where id=%s", (cita_id,)).fetchone()["estado"]


def outbox(conn, patient, key=None):
    q = "select * from mensaje where paciente_id=%s and direccion='saliente' and estado_entrega='entregado'"
    args = [patient]
    if key:
        q += " and plantilla=%s"
        args.append(key)
    return conn.execute(q + " order by id", args).fetchall()


def press(conn, patient, button_id):
    messaging.receive(conn, patient, button_id=button_id)


def button(conn, patient, key, index=0):
    return outbox(conn, patient, key)[-1]["botones"][index]["id"]
