"""Respuestas que llevan a la acción sin gastar tokens: los nombres de pacientes se vuelven enlaces a la ficha con los datos que
el asistente ya leyó, y las bandejas viajan compactas (lo que se reenvía en cada vuelta es lo que más se paga)."""
from datetime import datetime

from estudia.asistente.conversacion import enlaces
from estudia.asistente.herramientas import MAX_FILAS_BANDEJA, _compacta

LEIDO = [
    {"bandeja": "seguimientos", "filas": [{"id": 59, "paciente_id": 11, "paciente": "William Pérez García", "escalado": True}]},
    {"bandeja": "en_riesgo", "filas": [{"paciente_id": 12, "nombres": "Cecilia", "apellidos": "Arias Gutiérrez"}]},
    {"bandeja": "contactos", "filas": [{"id": 3, "nota": "Llamar", "paciente": {"id": 13, "nombre": "Ana Pérez"}}]},
    {"pacientes": [{"id": 14, "nombre": "Ana Pérez Gómez"}]},
]


def test_los_nombres_que_menciona_la_respuesta_llevan_a_la_ficha():
    texto = "Llama a William Pérez García (escalado) y a Cecilia Arias Gutiérrez. Ana Pérez Gómez pidió contacto."
    assert enlaces("auxiliar", texto, LEIDO) == [
        {"texto": "Cecilia Arias Gutiérrez", "ruta": "/pacientes/12"},
        {"texto": "William Pérez García", "ruta": "/pacientes/11"},
        {"texto": "Ana Pérez Gómez", "ruta": "/pacientes/14"},
        {"texto": "Ana Pérez", "ruta": "/pacientes/13"},  # el panel prefiere el más largo, que va antes
    ]


def test_sin_mencion_no_hay_enlace_y_el_paciente_no_recibe_enlaces():
    assert enlaces("auxiliar", "No hay pendientes.", LEIDO) == []
    assert enlaces("paciente", "William Pérez García", LEIDO) == []


def test_una_fila_de_bandeja_viaja_sin_vacios_ni_falsos_y_con_la_hora_al_minuto():
    f = {"id": 1, "paciente_id": 2, "caso_id": None, "internacional": False, "deportista": True, "intentos": 0,
         "abierto_en": datetime(2026, 10, 28, 21, 4, 49, 47970)}
    assert _compacta(f) == {"id": 1, "paciente_id": 2, "deportista": True, "intentos": 0, "abierto_en": "2026-10-28T21:04"}
    assert MAX_FILAS_BANDEJA <= 20
