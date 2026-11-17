import itertools
import os
from datetime import datetime, timedelta

# Las pruebas usan una base separada; se fija antes de importar el paquete.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://estudia:estudia@localhost:5433/estudia_test")

import pytest  # noqa: E402

from estudia import agenda, catalog, clock, config, data, db, messaging, migrate  # noqa: E402

URL = os.environ["DATABASE_URL"]
NOW = datetime(2026, 11, 16, 8, 0, tzinfo=clock.TZ)  # lunes 8:00


@pytest.fixture(scope="session", autouse=True)
def _schema():
    migrate.run(URL)


@pytest.fixture
def conn():
    c = db.connect(URL)
    data.wipe(c)
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


def make_patient(conn, nombres="Ana", apellidos="Pérez", doc=None, acepta=True, celular="+573001112233"):
    doc = doc or str(next(_doc))
    return conn.execute(
        "insert into paciente(nombres, apellidos, documento, celular, acepta_mensajes, consentimiento_en) "
        "values (%s,%s,%s,%s,%s,%s) returning id", (nombres, apellidos, doc, celular, acepta, NOW)).fetchone()["id"]


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
