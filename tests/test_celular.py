"""R8 del PRD de respuestas de la clínica: celular válido antes de enviar."""
from datetime import timedelta

import pytest

from estudia import agenda, bandejas, canales, clock, messaging, pacientes, tasks

from .conftest import at, book, make_patient, make_pro
from .test_api import API, mundo  # noqa: F401  (fixture)


@pytest.mark.parametrize("crudo, esperado", [
    ("3001112233", "+573001112233"),
    ("3001112233.0", "+573001112233"),
    ("300 111 2233", "+573001112233"),
    ("573001112233", "+573001112233"),
    ("+57 300 111 2233", "+573001112233"),
    ("+1 305 555 0100", "+13055550100"),
    ("+44 20 7946 0000", "+442079460000"),
    ("+573001", None),            # +57 con largo que no es de celular
    ("+5716012345", None),        # fijo de Colombia
    ("2001112233", None),         # 10 dígitos pero no empieza por 3
    ("12345", None),
    ("405 555 0100", None),       # sin + y no colombiano
    ("+0123456789", None),
    ("+1234567", None),           # 7 dígitos: menos de 8
    ("+1234567890123456", None),  # 16 dígitos
    ("", None), (None, None), ("abc", None),
])
def test_normalizar_celular(crudo, esperado):
    assert pacientes.normalizar_celular(crudo) == esperado


def test_el_alias_de_la_importacion_sigue_funcionando():
    from estudia import data
    assert data.normalize_phone("3001112233") == "+573001112233" and data.normalize_phone("12345") is None


def test_los_digitos_del_resultado_sirven_para_la_deduplicacion_de_prospectos(conn):
    pid, _ = pacientes.atender_solicitud(conn, nombre="Jane", correo=None, celular="+1 305 555 0100")
    otra, _ = pacientes.atender_solicitud(conn, nombre="Jane de nuevo", correo=None, celular="+13055550100")
    assert otra == pid
    col, _ = pacientes.atender_solicitud(conn, nombre="Ana", correo=None, celular="300 111 2233")
    de_nuevo, _ = pacientes.atender_solicitud(conn, nombre="Ana otra vez", correo=None, celular="+57 300 111 2233")
    assert de_nuevo == col  # aunque una lo escriba sin el 57


def test_crear_paciente_con_celular_invalido_dice_celular_no_valido(conn):
    with pytest.raises(pacientes.DatosInvalidos, match="Celular no válido"):
        pacientes.create(conn, "Ana", "Pérez", "123", "12345", True)
    pid = pacientes.create(conn, "Ana", "Pérez", "123", "300 111 2233", True)
    assert conn.execute("select celular, celular_estado from paciente where id=%s", (pid,)).fetchone() == {
        "celular": "+573001112233", "celular_estado": "sin_verificar"}


@pytest.mark.parametrize("estado", ["invalido", "sin_whatsapp"])
def test_no_se_envia_a_un_celular_inutilizable_y_no_cuenta_como_intento(conn, estado):
    pro, a = make_pro(conn), make_patient(conn)
    c = book(conn, a, pro, at(22, "10:00"))
    agenda.cancel(conn, c, "paciente", "enlace")
    caso = conn.execute("select * from caso_seguimiento").fetchone()
    conn.execute("update paciente set celular_estado=%s where id=%s", (estado, a))
    clock.freeze(caso["abierto_en"] + timedelta(days=3, minutes=1))
    tasks.cycle(conn)
    m = conn.execute("select estado_entrega, detalle from mensaje where plantilla='seguimiento_reasignacion'").fetchone()
    assert dict(m) == {"estado_entrega": "omitido", "detalle": "celular"}
    assert conn.execute("select count(*) n from intento").fetchone()["n"] == 0


def test_sin_celular_tampoco_se_envia(conn):
    a = make_patient(conn, celular=None)
    mid = messaging.send(conn, a, "baja_confirmada", direct=True)
    assert conn.execute("select estado_entrega, detalle from mensaje where id=%s", (mid,)).fetchone() == {
        "estado_entrega": "omitido", "detalle": "celular"}


def test_quien_responde_por_whatsapp_queda_con_celular_valido(conn):
    a = make_patient(conn)
    conn.execute("update paciente set celular_estado='sin_whatsapp' where id=%s", (a,))
    messaging.receive(conn, a, text="hola")
    assert conn.execute("select celular_estado from paciente where id=%s", (a,)).fetchone()["celular_estado"] == "valido"


def test_si_el_canal_dice_que_no_es_whatsapp_se_marca_y_el_mensaje_queda_fallido(conn, monkeypatch):
    class Rechaza(canales.Adaptador):
        tipo, medio = "prueba", "mensajeria"

        def enviar(self, conn, mensaje, paciente):
            raise canales.SinWhatsApp()

    conn.execute("insert into canal_negocio(negocio_id, tipo, id_externo, secreto_ref) values (1,'prueba','x','S')")
    monkeypatch.setattr(canales, "adaptador", lambda t: Rechaza() if t == "prueba" else None)
    a = make_patient(conn)
    mid = messaging.send(conn, a, "baja_confirmada", direct=True)
    assert conn.execute("select estado_entrega, detalle from mensaje where id=%s", (mid,)).fetchone() == {
        "estado_entrega": "fallido", "detalle": "celular"}
    assert conn.execute("select celular_estado from paciente where id=%s", (a,)).fetchone()["celular_estado"] == "sin_whatsapp"


def test_bandeja_celulares_por_revisar_con_fallback_al_responsable(conn):
    pro = make_pro(conn)
    papa = make_patient(conn, "Carlos", "Prueba", celular="+573005550000")
    hijo = make_patient(conn, "Mateo", "Prueba", celular=None)
    conn.execute("update paciente set responsable_id=%s, parentesco='hijo' where id=%s", (papa, hijo))
    sola = make_patient(conn, "Sola", "Sin Celular", celular="+573006660000")
    conn.execute("update paciente set celular_estado='invalido' where id=%s", (sola,))
    sin_cita = make_patient(conn, "Sin", "Cita", celular=None)  # sin cita ni caso: no sale
    no_contactar = make_patient(conn, "Cobro", "Jurídico", celular=None)
    pacientes.no_contactar(conn, no_contactar, "cobro", None, None)
    book(conn, hijo, pro, at(3, "10:00"), notify=False)
    book(conn, sola, pro, at(3, "11:00"), notify=False)
    book(conn, no_contactar, pro, at(3, "14:00"), notify=False)
    filas = {r["paciente_id"]: r for r in bandejas.celulares_por_revisar(conn)}
    assert set(filas) == {hijo, sola} and sin_cita not in filas
    assert filas[hijo]["motivo"] == "sin_celular" and filas[hijo]["responsable"] == "Carlos Prueba"
    assert filas[hijo]["parentesco"] == "hijo" and filas[hijo]["responsable_celular"] == "+573005550000"
    assert filas[sola]["motivo"] == "invalido" and filas[sola]["responsable_id"] is None


def test_el_responsable_con_celular_inutilizable_no_se_ofrece(conn):
    pro = make_pro(conn)
    papa = make_patient(conn, "Carlos", celular="+573005550000")
    conn.execute("update paciente set celular_estado='sin_whatsapp' where id=%s", (papa,))
    hijo = make_patient(conn, "Mateo", celular=None)
    conn.execute("update paciente set responsable_id=%s, parentesco='hijo' where id=%s", (papa, hijo))
    book(conn, hijo, pro, at(3, "10:00"), notify=False)
    assert [r["responsable_id"] for r in bandejas.celulares_por_revisar(conn) if r["paciente_id"] == hijo] == [None]


def test_el_panel_corrige_el_celular_o_lo_marca_como_valido(mundo, conn):  # noqa: F811
    conn.execute("update paciente set celular=null, celular_estado='invalido' where id=%s", (mundo.p1,))
    conn.commit()
    r = mundo.aux.put(f"{API}/pacientes/{mundo.p1}/celular", json={"celular": "123"})
    assert r.status_code == 422 and r.json()["mensaje"] == "Celular no válido"
    r = mundo.aux.put(f"{API}/pacientes/{mundo.p1}/celular", json={"celular": "301 222 3344"})
    assert r.status_code == 200 and r.json() == {"id": mundo.p1, "celular": "+573012223344", "celular_estado": "sin_verificar"}
    conn.execute("update paciente set celular_estado='sin_whatsapp' where id=%s", (mundo.p1,))
    conn.commit()
    r = mundo.aux.post(f"{API}/pacientes/{mundo.p1}/celular/en-chat", json={})
    assert r.status_code == 200 and r.json()["celular_estado"] == "valido"
    assert mundo.aux.put(f"{API}/pacientes/999999/celular", json={"celular": "3012223344"}).status_code == 404
    assert mundo.aux.get(f"{API}/bandejas/celulares-por-revisar").json() == []
    assert mundo.aux.get(f"{API}/bandejas").json()["celulares_por_revisar"] == 0
    assert mundo.aux.get(f"{API}/pacientes/{mundo.p1}").json()["paciente"]["celular_estado"] == "valido"
