"""R5 del PRD de respuestas de la clínica: el semáforo se calcula al vuelo, la primera regla que cumple gana."""
from datetime import timedelta

from estudia import bandejas, pacientes

from .conftest import NOW, at, book, make_patient, make_pro, svc
from .test_api import API, mundo  # noqa: F401  (fixture)


def pasada(conn, paciente, pro, dias_atras, estado, canal=None):
    """Una cita histórica (terminó hace `dias_atras` días) en el estado dado."""
    fin = NOW - timedelta(days=dias_atras)
    c = conn.execute(
        "insert into cita(paciente_id, profesional_id, servicio_id, dia, rango, estado, origen) "
        "values (%s,%s,%s,%s, tstzrange(%s,%s), %s,'auxiliar') returning id",
        (paciente, pro, svc(conn), fin.date(), fin - timedelta(hours=1), fin, estado)).fetchone()["id"]
    if canal:
        conn.execute("insert into cancelacion(cita_id, canal, antelacion_horas, tardia, momento) values (%s,%s,1,false,%s)",
                     (c, canal, fin))
    return c


def color(conn, p):
    return pacientes.semaforo(conn, [p])[p]


def test_sin_historia_es_verde_y_el_prospecto_no_tiene_color(conn):
    a = make_patient(conn)
    pid, _ = pacientes.atender_solicitud(conn, nombre="Jane", correo="j@example.com", celular=None)
    assert pacientes.semaforo(conn, [a, pid]) == {a: "verde", pid: "prospecto"}
    assert pacientes.semaforo(conn, []) == {}


def test_rojo_si_la_ultima_cita_fue_cancelacion_del_paciente_o_inasistencia_sin_cita_viva(conn):
    pro = make_pro(conn)
    cancela, falta, clinica = make_patient(conn, "Ca"), make_patient(conn, "Fa"), make_patient(conn, "Cl")
    pasada(conn, cancela, pro, 10, "cancelada", canal="whatsapp")
    pasada(conn, falta, pro, 10, "no_asistio")
    pasada(conn, clinica, pro, 10, "cancelada", canal="clinica")
    assert color(conn, cancela) == "rojo" and color(conn, falta) == "rojo"
    assert color(conn, clinica) == "verde"  # la canceló la clínica: no es culpa del paciente


def test_rojo_por_una_cita_pasada_sin_cerrar(conn):
    pro, a = make_pro(conn), make_patient(conn)
    pasada(conn, a, pro, 3, "programada")
    assert color(conn, a) == "rojo"


def test_una_cita_viva_futura_quita_el_rojo_y_la_ultima_atendida_es_verde(conn):
    pro, a, b = make_pro(conn), make_patient(conn, "A"), make_patient(conn, "B")
    pasada(conn, a, pro, 10, "no_asistio")
    book(conn, a, pro, at(3, "10:00"))
    pasada(conn, b, pro, 10, "no_asistio")
    pasada(conn, b, pro, 2, "atendida")  # lo último fue una atención
    assert color(conn, a) == "verde" and color(conn, b) == "verde"


def test_perdido_con_mas_de_60_dias_sin_venir_y_sin_cita_viva(conn):
    pro = make_pro(conn)
    p, nuevo, nunca = make_patient(conn, "P"), make_patient(conn, "N"), make_patient(conn, "U")
    pasada(conn, p, pro, 70, "atendida")
    pasada(conn, nuevo, pro, 50, "atendida")
    pasada(conn, nunca, pro, 80, "no_asistio")  # nunca asistió y faltó hace más de 60 días
    assert (color(conn, p), color(conn, nuevo), color(conn, nunca)) == ("perdido", "verde", "perdido")
    book(conn, p, pro, at(2, "10:00"))
    assert color(conn, p) == "verde"  # con cita viva ya no está perdido


def test_perdido_gana_al_rojo(conn):
    pro, a = make_pro(conn), make_patient(conn)
    pasada(conn, a, pro, 90, "atendida")
    pasada(conn, a, pro, 70, "no_asistio")
    assert color(conn, a) == "perdido"


def test_amarillo_por_tres_cambios_de_fecha_en_12_meses(conn):
    pro, a = make_pro(conn), make_patient(conn)
    for d in (20, 40):
        pasada(conn, a, pro, d, "reprogramada")
    assert color(conn, a) == "verde"
    pasada(conn, a, pro, 100, "reprogramada")
    assert color(conn, a) == "amarillo"
    otra = make_patient(conn, "Vieja")
    for d in (400, 410, 420):
        pasada(conn, otra, pro, d, "reprogramada")
    assert color(conn, otra) == "verde"  # fuera de los 12 meses


def test_amarillo_si_la_cita_de_menos_de_48h_sigue_sin_confirmar(conn):
    pro, a, b = make_pro(conn), make_patient(conn, "A"), make_patient(conn, "B")
    c = book(conn, a, pro, at(1, "10:00"))
    d = book(conn, b, pro, at(4, "10:00"))
    conn.execute("update cita set estado='no_confirmada' where id = any(%s)", ([c, d],))
    assert color(conn, a) == "amarillo" and color(conn, b) == "verde"  # la de b es dentro de 4 días


def test_la_busqueda_filtra_por_color_y_devuelve_el_semaforo(conn):
    pro = make_pro(conn)
    roja, verde = make_patient(conn, "Rosa", "Prueba"), make_patient(conn, "Vera", "Prueba")
    pasada(conn, roja, pro, 5, "no_asistio")
    todos = {r["id"]: r["semaforo"] for r in bandejas.find_patients(conn, "prueba")}
    assert todos == {roja: "rojo", verde: "verde"}
    assert [r["id"] for r in bandejas.find_patients(conn, "prueba", semaforo="rojo")] == [roja]
    assert [r["id"] for r in bandejas.find_patients(conn, "prueba", semaforo="perdido")] == []


def test_el_panel_devuelve_el_color_en_busqueda_y_ficha_y_filtra(mundo, conn):  # noqa: F811
    pro = mundo.pro1
    pasada(conn, mundo.p1, pro, 5, "no_asistio")
    conn.commit()
    nombre = conn.execute("select nombres from paciente where id=%s", (mundo.p1,)).fetchone()["nombres"].split()[0]
    res = mundo.aux.get(f"{API}/pacientes", params={"q": nombre}).json()
    assert {r["id"]: r["semaforo"] for r in res}[mundo.p1] == "rojo"
    ids = [r["id"] for r in mundo.aux.get(f"{API}/pacientes", params={"q": nombre, "semaforo": "rojo"}).json()]
    assert mundo.p1 in ids
    ids = [r["id"] for r in mundo.aux.get(f"{API}/pacientes", params={"q": nombre, "semaforo": "perdido"}).json()]
    assert mundo.p1 not in ids
    assert mundo.aux.get(f"{API}/pacientes/{mundo.p1}").json()["paciente"]["semaforo"] == "rojo"
    assert mundo.aux.get(f"{API}/pacientes", params={"q": nombre, "semaforo": "azul"}).status_code == 422
