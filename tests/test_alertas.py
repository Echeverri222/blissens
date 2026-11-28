"""Sistema en palabras: cada tarea que falló dice qué no salió, a qué paciente, por qué y qué hacer."""
import json
from datetime import timedelta

from estudia import alertas

from .conftest import NOW, at, book, make_patient, make_pro

TRAZA = ('Traceback (most recent call last):\n  File "estudia/tasks.py", line 40, in _run_one\n'
         '    HANDLERS[t["tipo"]](conn, t["datos"], now)\nKeyError: \'acepta_correo\'\n')


def fallida(conn, tipo, datos, error=TRAZA, cuando=NOW):
    return conn.execute("insert into tarea_programada(tipo, ejecutar_en, datos, estado, intentos, error) "
                        "values (%s,%s,%s,'fallida',3,%s) returning id", (tipo, cuando, json.dumps(datos), error)).fetchone()["id"]


def test_un_recordatorio_que_fallo_dice_a_quien_llamar_y_por_que(conn):
    pro, ana = make_pro(conn), make_patient(conn, "Ana", "Pérez")
    cita = book(conn, ana, pro, at(1, "09:00"))
    fallida(conn, "recordatorio", {"cita_id": cita, "horas": 24, "inicio": at(1, "09:00").isoformat()})
    [a] = alertas.fallidas(conn)
    assert a["titulo"] == "No salió el recordatorio de una cita" and a["titulo_varias"] == "recordatorios de cita no salieron"
    assert a["paciente"] == "Ana Pérez" and a["paciente_id"] == ana and a["cita_id"] == cita
    assert a["cita_inicio"] == at(1, "09:00")
    assert a["causa"] == alertas.INTERNA and "Llama al paciente" in a["que_hacer"]
    assert "KeyError" in a["error"]  # el detalle técnico sigue ahí para quien administra


def test_mensajes_y_seguimientos_tambien_encuentran_al_paciente(conn):
    pro, luis = make_pro(conn), make_patient(conn, "Luis", "Mora")
    cita = book(conn, luis, pro, at(2, "10:00"))
    caso = conn.execute("insert into caso_seguimiento(tipo, paciente_id, cita_id, abierto_en) values ('inasistencia',%s,%s,%s) "
                        "returning id", (luis, cita, NOW)).fetchone()["id"]
    msj = conn.execute("insert into mensaje(paciente_id, direccion, plantilla, texto, tipo, botones, momento) "
                       "values (%s,'saliente','x','hola','texto','[]',%s) returning id", (luis, NOW)).fetchone()["id"]
    fallida(conn, "intento_seguimiento", {"caso_id": caso, "numero": 2}, cuando=NOW - timedelta(minutes=1))
    fallida(conn, "entregar_mensaje", {"mensaje_id": msj}, error="ConnectionError: el proveedor no respondió",
            cuando=NOW - timedelta(minutes=2))
    seguimiento, whatsapp = alertas.fallidas(conn)
    assert seguimiento["paciente_id"] == luis and seguimiento["cita_id"] == cita
    assert whatsapp["paciente"] == "Luis Mora" and whatsapp["cita_id"] is None and whatsapp["causa"] == alertas.CANAL


def test_causa_en_palabras():
    assert alertas.causa(None) == "No quedó registrado por qué."
    assert alertas.causa("sin saldo") == "sin saldo"  # un motivo ya escrito para personas se deja
    assert alertas.causa("Traceback ...\nRuntimeError: algo raro") == alertas.INTERNA
    assert alertas.causa("Traceback ...\nhttpx.ReadTimeout: timed out") == alertas.CANAL


def test_tipo_desconocido_o_sin_paciente_no_rompe(conn):
    fallida(conn, "tarea_nueva", {})
    [a] = alertas.fallidas(conn)
    assert a["titulo"] == "Una tarea automática falló" and a["paciente"] is None


def test_tareas_atrasadas_avisan_que_el_envio_esta_detenido(conn):
    conn.execute("insert into tarea_programada(tipo, ejecutar_en, datos) values ('recordatorio', %s, '{}')",
                 (NOW - timedelta(minutes=5),))
    assert alertas.atrasadas(conn) == 0  # recién vencida: el ciclo aún no pasa
    conn.execute("insert into tarea_programada(tipo, ejecutar_en, datos) values ('recordatorio', %s, '{}')",
                 (NOW - timedelta(hours=1),))
    assert alertas.atrasadas(conn) == 1
