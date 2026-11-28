"""Panel de la auxiliar (docs/prd-panel-auxiliar.md): confirmar por teléfono, No confirmadas con las de mañana y resumen del día."""
from datetime import datetime

from estudia import bandejas, clock, confirmations, permisos
from estudia.agenda import rng

from .conftest import NOW, at, book, make_patient, make_pro, outbox, status, svc
from .test_api import API, mundo  # noqa: F401  (fixture)


def poner(conn, cita, estado):
    conn.execute("update cita set estado=%s where id=%s", (estado, cita))
    conn.commit()


def cita(conn, paciente, pro, inicio, estado="programada"):
    """Inserta la cita directo: estas pruebas necesitan horas y estados que el agendamiento no deja crear."""
    return conn.execute(
        "insert into cita(paciente_id, profesional_id, servicio_id, dia, rango, estado, origen) values (%s,%s,%s,%s,%s,%s,'auxiliar') "
        "returning id", (paciente, pro, svc(conn), inicio.date(), rng(inicio, 30), estado)).fetchone()["id"]


def hist(conn, cita):
    return conn.execute("select * from historial_estado where cita_id=%s order by id", (cita,)).fetchall()


# ------------------------------------------------------------------ R1: confirmar por teléfono

def test_phone_confirmation_works_on_future_programada_and_no_confirmada(mundo, conn):
    for estado in ("programada", "no_confirmada"):
        c = book(conn, mundo.p1, mundo.pro1, at(3 if estado == "programada" else 4, "09:00"))
        poner(conn, c, estado)
        antes = conn.execute("select count(*) as n from mensaje").fetchone()["n"]
        d = mundo.aux.get(f"{API}/citas/{c}").json()
        assert "confirmar" in d["acciones"]
        assert mundo.aux.post(f"{API}/citas/{c}/confirmar", json={}).status_code == 200
        assert status(conn, c) == "confirmada"
        h = hist(conn, c)[-1]
        assert (h["estado_anterior"], h["estado_nuevo"], h["actor"], h["detalle"]) == (
            estado, "confirmada", "auxiliar", "Confirmada por teléfono")
        assert h["usuario_id"] is not None
        assert conn.execute("select count(*) as n from mensaje").fetchone()["n"] == antes  # no sale ningún mensaje
        assert "confirmar" not in mundo.aux.get(f"{API}/citas/{c}").json()["acciones"]


def test_phone_confirmation_can_be_reverted(mundo, conn):
    c = book(conn, mundo.p1, mundo.pro1, at(3, "09:00"))
    conn.commit()
    mundo.aux.post(f"{API}/citas/{c}/confirmar", json={})
    h = mundo.aux.get(f"{API}/citas/{c}").json()["historial"][-1]
    assert h["reversible"] is True
    assert mundo.aux.post(f"{API}/historial/{h['id']}/revertir", json={}).status_code == 200
    assert status(conn, c) == "programada"


def test_phone_confirmation_is_refused_when_it_does_not_apply(mundo, conn):
    futura = book(conn, mundo.p1, mundo.pro1, at(3, "09:00"))
    conn.commit()
    assert mundo.esp1.post(f"{API}/citas/{futura}/confirmar", json={}).status_code == 403
    assert "confirmar" not in mundo.esp1.get(f"{API}/citas/{futura}").json()["acciones"]
    assert status(conn, futura) == "programada"

    for hora, estado in zip(("09:00", "10:00", "11:00", "13:00", "14:00"),
                            ("confirmada", "cancelada", "atendida", "no_asistio", "reprogramada")):
        c = book(conn, mundo.p2, mundo.pro2, at(7, hora))
        poner(conn, c, estado)
        assert mundo.aux.post(f"{API}/citas/{c}/confirmar", json={}).status_code == 409, estado
        assert "confirmar" not in mundo.aux.get(f"{API}/citas/{c}").json()["acciones"]
        assert status(conn, c) == estado

    pasada = book(conn, mundo.p1, mundo.pro2, at(1, "09:00"))
    poner(conn, pasada, "no_confirmada")
    clock.freeze(at(1, "09:30"))
    assert "confirmar" not in mundo.aux.get(f"{API}/citas/{pasada}").json()["acciones"]
    r = mundo.aux.post(f"{API}/citas/{pasada}/confirmar", json={})
    assert r.status_code == 409 and r.json()["codigo"] == "transicion_invalida"
    assert status(conn, pasada) == "no_confirmada"
    assert mundo.aux.post(f"{API}/citas/99999/confirmar", json={}).status_code == 404


def test_actions_offer_confirmar_only_to_the_auxiliar_before_the_start():
    aux, esp = {"rol": "auxiliar"}, {"rol": "especialista"}
    inicio = at(1, "09:00")
    assert permisos.acciones_cita(aux, "programada", inicio, NOW) == ["confirmar", "cancelar", "cambiar_fecha"]
    assert permisos.acciones_cita(aux, "no_confirmada", inicio, NOW) == ["confirmar", "cancelar", "cambiar_fecha"]
    assert permisos.acciones_cita(aux, "confirmada", inicio, NOW) == ["cancelar", "cambiar_fecha"]
    assert permisos.acciones_cita(esp, "programada", inicio, NOW) == []
    assert permisos.acciones_cita(aux, "programada", inicio, inicio) == ["desenlace"]


# ------------------------------------------------------------------ R4: No confirmadas incluye las de mañana

def test_no_confirmadas_includes_tomorrows_silent_programadas(conn):
    pro = make_pro(conn)
    pa, pb, pc, pd, pe = (make_patient(conn, n, "Prueba") for n in ("A", "B", "C", "D", "E"))
    hoy_programada = cita(conn, pa, pro, at(0, "15:00"))
    poner(conn, hoy_programada, "programada")
    manana_prog = cita(conn, pb, pro, at(1, "09:00"))
    manana_noconf = cita(conn, pc, pro, at(1, "10:00"))
    poner(conn, manana_noconf, "no_confirmada")
    tarde_manana = cita(conn, pd, pro, at(1, "17:00"))
    pasado = cita(conn, pe, pro, at(2, "09:00"))
    pasado_noconf = cita(conn, pa, pro, at(2, "11:00"))
    poner(conn, pasado_noconf, "no_confirmada")
    empezada = cita(conn, pb, pro, at(0, "09:00"))
    poner(conn, empezada, "no_confirmada")
    clock.freeze(at(0, "09:00"))
    ids = [r["id"] for r in bandejas.no_confirmadas(conn)]
    assert pasado not in ids and empezada not in ids
    # Por día; dentro del día, primero las «sin confirmar» y luego las programadas sin respuesta, cada grupo por hora.
    assert ids == [hoy_programada, manana_noconf, manana_prog, tarde_manana, pasado_noconf]
    r = {x["id"]: x for x in bandejas.no_confirmadas(conn)}
    assert r[manana_noconf]["estado"] == "no_confirmada" and r[manana_prog]["estado"] == "programada"
    assert bandejas.resumen_dia(conn)["sin_confirmar"] == 4  # hasta el fin de mañana: sin la de pasado mañana


def test_no_confirmadas_tomorrow_cutoff_is_midnight_of_tomorrow(conn):
    pro = make_pro(conn)
    p = make_patient(conn)
    ultima = cita(conn, p, pro, at(1, "23:30"))
    primera = cita(conn, p, pro, at(2, "00:00"))
    assert [r["id"] for r in bandejas.no_confirmadas(conn)] == [ultima]
    assert primera not in [r["id"] for r in bandejas.no_confirmadas(conn)]


def test_no_confirmadas_reports_the_reminder_and_skips_opted_out_patients(conn):
    pro = make_pro(conn)
    p, baja = make_patient(conn, "A", "Uno"), make_patient(conn, "B", "Dos", acepta=False)
    con_hora, con_bandera, sin_nada, de_baja = (cita(conn, q, pro, at(1, h)) for q, h in
                                                ((p, "09:00"), (p, "10:00"), (p, "11:00"), (baja, "12:00")))
    conn.execute("update cita set datos_origen=%s::jsonb where id=%s",
                 ('{"recordatorio_enviado": true, "recordatorio_en": "2026-11-15T08:00:00-05:00"}', con_hora))
    conn.execute("update cita set datos_origen=%s::jsonb where id=%s", ('{"recordatorio_enviado": true}', con_bandera))
    r = {x["id"]: x for x in bandejas.no_confirmadas(conn)}
    assert de_baja not in r
    assert r[con_hora]["recordatorio_enviado"] and r[con_hora]["recordatorio_en"].hour == 8
    assert r[con_bandera]["recordatorio_enviado"] and r[con_bandera]["recordatorio_en"] is None
    assert not r[sin_nada]["recordatorio_enviado"] and r[sin_nada]["recordatorio_en"] is None


def test_reminder_task_records_when_it_was_sent(conn):
    pro, p = make_pro(conn), make_patient(conn)
    c = cita(conn, p, pro, at(3, "09:00"))
    clock.freeze(at(1, "09:00"))
    confirmations.run_reminder(conn, c, 48, at(3, "09:00").isoformat(), clock.now(conn))
    assert outbox(conn, p, "recordatorio_48h")
    assert bandejas.no_confirmadas(conn) == []  # fuera de la ventana de mañana: aún no aparece
    fila = conn.execute("select datos_origen from cita where id=%s", (c,)).fetchone()["datos_origen"]
    assert fila["recordatorio_enviado"] is True and datetime.fromisoformat(fila["recordatorio_en"]) == clock.now(conn)
    assert fila["recordatorio_48h"] == at(3, "09:00").isoformat()  # la marca del hogar sigue guardando la hora de inicio


# ------------------------------------------------------------------ R3: resumen del día

def test_summary_counts_and_is_only_for_the_auxiliar(mundo, conn):
    cita(conn, mundo.p1, mundo.pro1, at(0, "09:00"), "confirmada")  # hoy
    cita(conn, mundo.p2, mundo.pro2, at(1, "09:00"))  # mañana, sin respuesta
    cita(conn, mundo.p2, mundo.pro2, at(3, "09:00"))  # fuera de la ventana
    conn.execute("insert into mensaje(paciente_id, direccion, texto, gestionado, momento) values (%s,'entrante','hola',false,%s)",
                 (mundo.p2, NOW))
    conn.commit()
    clock.freeze(at(0, "11:00"))  # la cita de hoy ya terminó
    r = mundo.aux.get(f"{API}/resumen-dia")
    assert r.status_code == 200
    assert r.json() == {"citas_hoy": 1, "sin_confirmar": 1, "mensajes": 1, "por_cerrar": 1}
    assert mundo.esp1.get(f"{API}/resumen-dia").status_code == 403
