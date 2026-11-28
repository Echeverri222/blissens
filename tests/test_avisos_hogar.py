"""Un hogar comparte un celular: sus avisos automáticos salen agrupados, uno por evento (docs/prd-familia.md R9)."""
from datetime import timedelta

from estudia import agenda, clock, confirmations, familia, lifecycle, slots, tasks
from estudia.web.app import _hogar_del_ultimo_mensaje

from .conftest import at, book, make_patient, make_pro, outbox, press, status, svc

CEL = "+573001112233"


def hogar(conn):
    """Carlos (responsable) con Mateo y Sofía, todos con el mismo celular."""
    carlos = make_patient(conn, "Carlos", "Prueba", celular=CEL)
    hijos = []
    for nombre in ("Mateo", "Sofía"):
        h = make_patient(conn, nombre, "Prueba", celular=CEL)
        conn.execute("update paciente set responsable_id=%s, parentesco='hijo' where id=%s", (carlos, h))
        hijos.append(h)
    return carlos, *hijos


def del_hogar(conn, ids, plantilla_like):
    return conn.execute("select * from mensaje where paciente_id = any(%s) and direccion='saliente' "
                        "and estado_entrega='entregado' and plantilla like %s order by id", (list(ids), plantilla_like)).fetchall()


def citas_seguidas(conn, pro, gente, dia=3):
    return [book(conn, p, pro, at(dia, h), notify=False) for p, h in zip(gente, ("09:00", "09:30", "10:00"), strict=False)]


def test_un_solo_recordatorio_de_48h_para_todo_el_hogar_y_un_toque_confirma_todas(conn):
    pro = make_pro(conn)
    gente = hogar(conn)
    citas = citas_seguidas(conn, pro, gente)
    clock.freeze(at(3, "09:00") - timedelta(hours=48) + timedelta(minutes=1))
    tasks.cycle(conn)
    clock.freeze(at(3, "10:00") - timedelta(hours=48) + timedelta(minutes=1))  # vencen las tareas de las otras dos
    tasks.cycle(conn)

    recordatorios = del_hogar(conn, gente, "recordatorio%")
    assert len(recordatorios) == 1
    m = recordatorios[0]
    assert m["paciente_id"] == gente[0] and m["plantilla"] == "recordatorio_48h_hogar"
    assert "Hola Carlos" in m["texto"] and "• Tú:" in m["texto"] and "• Mateo:" in m["texto"] and "• Sofía:" in m["texto"]
    assert [b["title"] for b in m["botones"]] == ["Sí, asistiremos", "Cambiar o cancelar"]

    press(conn, gente[0], m["botones"][0]["id"])
    assert [status(conn, c) for c in citas] == ["confirmada"] * 3
    assert len(outbox(conn, gente[0], "confirmacion_recibida_hogar")) == 1

    # A las 24 h: un solo recordatorio corto, sin botones
    clock.freeze(at(3, "10:00") - timedelta(hours=24) + timedelta(minutes=1))
    tasks.cycle(conn)
    cortos = del_hogar(conn, gente, "recordatorio_24h%")
    assert len(cortos) == 1 and cortos[0]["plantilla"] == "recordatorio_24h_hogar" and not cortos[0]["botones"]
    assert not del_hogar(conn, gente, "segundo_intento%")


def test_a_las_24h_un_solo_segundo_intento_que_marca_las_que_faltan(conn):
    pro = make_pro(conn)
    gente = hogar(conn)
    carlos_cita, mateo_cita, sofia_cita = citas_seguidas(conn, pro, gente)
    clock.freeze(at(3, "09:00") - timedelta(hours=47))
    tasks.cycle(conn)
    lifecycle.transition(conn, carlos_cita, "confirmada", "paciente", "Confirmó por teléfono")
    clock.freeze(at(3, "10:00") - timedelta(hours=23, minutes=59))
    tasks.cycle(conn)

    m = del_hogar(conn, gente, "segundo_intento%")
    assert len(m) == 1 and m[0]["plantilla"] == "segundo_intento_hogar"
    assert not del_hogar(conn, gente, "recordatorio_24h%")
    lineas = m[0]["texto"].splitlines()
    assert any(x.startswith("• Tú:") and "sin confirmar" not in x for x in lineas)
    assert any(x.startswith("• Mateo:") and "(sin confirmar)" in x for x in lineas)
    assert status(conn, mateo_cita) == status(conn, sofia_cita) == "no_confirmada"
    assert m[0]["botones"][0]["id"] == f"confh:si:{mateo_cita}-{sofia_cita}"


def test_cambiar_o_cancelar_manda_el_enlace_del_hogar_y_no_cancela_nada(conn):
    pro = make_pro(conn)
    gente = hogar(conn)
    citas = citas_seguidas(conn, pro, gente)
    clock.freeze(at(3, "09:00") - timedelta(hours=47))
    tasks.cycle(conn)
    press(conn, gente[0], del_hogar(conn, gente, "recordatorio%")[0]["botones"][1]["id"])
    assert "/p/" in outbox(conn, gente[0], "cambiar_hogar")[0]["texto"]
    assert [status(conn, c) for c in citas] == ["programada"] * 3


def test_un_boton_no_toca_citas_de_otro_hogar(conn):
    pro = make_pro(conn)
    gente = hogar(conn)
    otro = make_patient(conn, "Otro", celular="+573009999999")
    ajena = book(conn, otro, pro, at(3, "15:00"), notify=False)
    press(conn, gente[0], f"confh:si:{ajena}")
    assert status(conn, ajena) == "programada"
    entrante = conn.execute("select gestionado from mensaje where direccion='entrante' order by id desc limit 1").fetchone()
    assert entrante["gestionado"] is False
    assert not outbox(conn, gente[0], "respuesta_tardia")
    # Defensa en profundidad: invocando directamente sin pasar por messaging.receive
    confirmations.process_household(conn, gente[0], "si", [ajena])
    assert status(conn, ajena) == "programada"
    assert outbox(conn, gente[0], "respuesta_tardia")


def test_solo_la_cita_del_responsable_usa_el_recordatorio_de_siempre(conn):
    pro = make_pro(conn)
    carlos, mateo, _ = hogar(conn)
    book(conn, carlos, pro, at(3, "09:00"), notify=False)
    book(conn, mateo, pro, at(4, "09:00"), notify=False)  # otro día: recordatorio aparte
    clock.freeze(at(3, "09:00") - timedelta(hours=47))
    tasks.cycle(conn)
    assert [m["plantilla"] for m in del_hogar(conn, (carlos, mateo), "recordatorio%")] == ["recordatorio_48h"]


def test_la_cita_de_un_familiar_le_llega_al_responsable_con_su_nombre(conn):
    pro = make_pro(conn)
    carlos, mateo, _ = hogar(conn)
    book(conn, mateo, pro, at(3, "09:00"), notify=False)
    clock.freeze(at(3, "09:00") - timedelta(hours=47))
    tasks.cycle(conn)
    m = del_hogar(conn, (carlos, mateo), "recordatorio%")
    assert len(m) == 1 and m[0]["paciente_id"] == carlos and "• Mateo:" in m[0]["texto"]


def test_las_citas_agendadas_seguidas_salen_en_un_solo_mensaje(conn):
    pro = make_pro(conn)
    gente = hogar(conn)
    for p, h in zip(gente, ("09:00", "09:30", "10:00"), strict=True):
        agenda.book(conn, p, pro, svc(conn), at(3, h), "paciente", "paciente")
        clock.freeze(clock.now(conn) + timedelta(minutes=2))  # entre una y otra, menos que la espera
        tasks.cycle(conn)
    assert not del_hogar(conn, gente, "cita_agendada%")  # todavía agendando: nada sale

    clock.freeze(clock.now(conn) + timedelta(minutes=5))
    tasks.cycle(conn)
    m = del_hogar(conn, gente, "cita_agendada%")
    assert len(m) == 1 and m[0]["plantilla"] == "cita_agendada_hogar" and m[0]["paciente_id"] == gente[0]
    assert m[0]["texto"].count("•") == 3
    assert not conn.execute("select 1 from cita where datos_origen ? 'aviso_pendiente'").fetchone()


def test_un_paciente_sin_familia_recibe_su_aviso_al_instante(conn):
    pro = make_pro(conn)
    solo = make_patient(conn, "Ana", celular="+573005555555")
    book(conn, solo, pro, at(3, "09:00"))
    assert len(outbox(conn, solo, "cita_agendada")) == 1


def test_un_solo_seguimiento_al_dia_por_hogar(conn):
    pro = make_pro(conn)
    gente = hogar(conn)
    citas = citas_seguidas(conn, pro, gente)
    for c in citas:
        agenda.cancel(conn, c, "paciente", "web")
    seguimiento = del_hogar(conn, gente, "%")
    seguimiento = [m for m in seguimiento if m["plantilla"] in ("cancelacion_recibida", "seguimiento_reasignacion")]
    assert len(seguimiento) == 1
    casos = conn.execute("select count(*) n from caso_seguimiento where estado='abierto'").fetchone()["n"]
    assert casos == 3  # los casos siguen abiertos: sus próximos intentos saldrán, de a uno
    # Lo que no salió no cuenta como intento: queda reprogramado para cuando se cumpla la espera.
    assert conn.execute("select count(*) n from intento").fetchone()["n"] == 1
    clock.freeze(clock.now(conn) + timedelta(hours=20, minutes=1))  # 04:01: fuera del horario, sale a las 07:00
    tasks.cycle(conn)
    clock.freeze(clock.now(conn) + timedelta(hours=3))
    tasks.cycle(conn)
    otra_vez = [m for m in del_hogar(conn, gente, "%") if m["plantilla"] == "seguimiento_reasignacion"]
    assert len(otra_vez) == 1  # al día siguiente, el de una sola persona más


def test_una_sola_oferta_de_adelanto_pendiente_por_hogar(conn):
    pro = make_pro(conn)
    carlos, mateo, _ = hogar(conn)
    otro = make_patient(conn, "Otro", celular="+573009999999")
    book(conn, carlos, pro, at(3, "10:00"), notify=False)
    book(conn, mateo, pro, at(4, "10:00"), notify=False)
    book(conn, otro, pro, at(2, "10:00"), notify=False)
    slots.register_slot(conn, pro, agenda.rng(at(0, "14:00"), 30), None, "cancelacion")
    slots.register_slot(conn, pro, agenda.rng(at(0, "15:00"), 30), None, "cancelacion")
    hogar_ofertas = del_hogar(conn, (carlos, mateo), "oferta_adelanto")
    assert len(hogar_ofertas) == 1 and hogar_ofertas[0]["paciente_id"] == mateo  # la cita más lejana, primero
    assert len(outbox(conn, otro, "oferta_adelanto")) == 1


def test_a_las_24h_solo_pasan_a_no_confirmada_las_que_llegaron_a_su_hora(conn):
    pro = make_pro(conn)
    carlos, mateo, sofia = hogar(conn)
    clock.freeze(at(2, "07:30"))  # menos de 48 h: no hay recordatorio de 48 h
    temprano = book(conn, mateo, pro, at(3, "08:00"), notify=False)
    tarde = book(conn, sofia, pro, at(3, "16:00"), notify=False)
    clock.freeze(at(3, "08:00") - timedelta(hours=23, minutes=59))
    tasks.cycle(conn)
    assert status(conn, temprano) == "no_confirmada" and status(conn, tarde) == "programada"
    assert len(del_hogar(conn, (carlos, mateo, sofia), "segundo_intento%")) == 1
    clock.freeze(at(3, "16:00") - timedelta(hours=23, minutes=59))
    tasks.cycle(conn)
    assert status(conn, tarde) == "no_confirmada"
    assert len(del_hogar(conn, (carlos, mateo, sofia), "segundo_intento%")) == 1  # sin otro mensaje


def test_quien_deja_el_hogar_durante_la_espera_recibe_su_propio_aviso(conn):
    pro = make_pro(conn)
    carlos, mateo, _ = hogar(conn)
    cita = agenda.book(conn, mateo, pro, svc(conn), at(3, "09:00"), "paciente", "paciente")
    conn.execute("update paciente set fecha_nacimiento='1990-01-01' where id=%s", (mateo,))
    familia.dejar_de_compartir(conn, conn.execute("select * from paciente where id=%s", (mateo,)).fetchone())
    clock.freeze(clock.now(conn) + timedelta(minutes=6))
    tasks.cycle(conn)
    assert len(outbox(conn, mateo, "cita_agendada")) == 1
    assert not conn.execute("select 1 from cita where id=%s and datos_origen ? 'aviso_pendiente'", (cita,)).fetchone()


def test_la_respuesta_a_un_mensaje_de_un_familiar_queda_en_el_familiar(conn):
    pro = make_pro(conn)
    carlos, mateo, _ = hogar(conn)
    cita = book(conn, mateo, pro, at(3, "09:00"), notify=False)
    agenda.cancel(conn, cita, "paciente", "web")
    boton = outbox(conn, mateo, "cancelacion_recibida")[0]["botones"][0]["id"]
    press(conn, carlos, boton)  # llega desde el celular del hogar, que el webhook resuelve al responsable
    entrante = conn.execute("select * from mensaje where direccion='entrante' order by id desc limit 1").fetchone()
    assert entrante["paciente_id"] == mateo and entrante["texto"] == "Ahora no"
    assert outbox(conn, mateo, "cancelacion_recibida")[0]["respuesta"] == boton


def test_un_celular_que_quedo_en_dos_hogares_se_resuelve_por_el_ultimo_mensaje(conn):
    pro = make_pro(conn)
    carlos, mateo, _ = hogar(conn)
    conn.execute("update paciente set responsable_id=null where id=%s", (mateo,))  # dejó de compartir, mismo número
    assert _hogar_del_ultimo_mensaje(conn, CEL) is None
    book(conn, mateo, pro, at(3, "09:00"))
    assert _hogar_del_ultimo_mensaje(conn, CEL) == mateo
    from estudia import messaging
    messaging.send(conn, carlos, "seguimiento_pausado", {})
    assert _hogar_del_ultimo_mensaje(conn, CEL) == carlos
