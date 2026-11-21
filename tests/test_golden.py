"""Golden cases: escenarios declarados en YAML cuyo resultado se compara con un snapshot aprobado.

Cada caso `tests/golden/<tema>/<caso>.yaml` describe datos ficticios y pasos; el resultado esperado vive al lado, en
`<caso>.golden.yaml`. Para regenerar los snapshots tras un cambio intencional: `make golden-update` y revisar el diff.
"""
import os
import re
from pathlib import Path

import pytest
import yaml

from estudia import agenda, clock, config, tasks

from .conftest import NOW, at, book, button, make_patient, make_pro, press, svc

RAIZ = Path(__file__).parent / "golden"
CASOS = sorted(p for p in RAIZ.rglob("*.yaml") if not p.name.endswith(".golden.yaml"))
ACTUALIZAR = os.environ.get("GOLDEN_UPDATE") == "1"


def _delta(momento) -> str:
    """Instante relativo a NOW ('+2d 1h 5m'): estable aunque cambie la fecha de referencia."""
    s = int((momento - NOW).total_seconds())
    signo, s = ("-" if s < 0 else "+"), abs(s)
    d, resto = divmod(s, 86400)
    h, resto = divmod(resto, 3600)
    return f"{signo}{d}d {h}h {resto // 60}m"


def _offset(texto: str):
    """'-47h59m' -> timedelta."""
    from datetime import timedelta
    m = re.fullmatch(r"([+-])(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?", texto)
    if not m:
        raise ValueError(f"Desplazamiento inválido: {texto}")
    d, h, mi = (int(x or 0) for x in m.groups()[1:])
    delta = timedelta(days=d, hours=h, minutes=mi)
    return -delta if m.group(1) == "-" else delta


def _ejecutar(conn, caso: dict) -> dict:
    dado = caso["dado"]
    for clave, valor in (caso.get("config") or {}).items():
        config.set_(conn, clave, valor)
    pro = make_pro(conn, **dado.get("profesional", {}))
    pac = make_patient(conn, **dado["paciente"])
    ini = dado["cita"]["inicio"]
    inicio = at(ini["dia"], ini["hora"])
    cita = book(conn, pac, pro, inicio, **({"service": dado["cita"]["servicio"]} if "servicio" in dado["cita"] else {}))
    fotos = []
    for paso in caso["pasos"]:
        (accion, arg), = paso.items()
        if accion == "avanzar":
            clock.freeze(inicio + _offset(arg["respecto_a_cita"]) if "respecto_a_cita" in arg else at(arg["dia"], arg["hora"]))
        elif accion == "foto":  # estado intermedio: mensajes y tareas en este punto del escenario
            fotos.append({"paso": arg, **_snapshot(conn)})
        elif accion == "ciclo":
            tasks.cycle(conn)
        elif accion == "presiona":
            press(conn, pac, button(conn, pac, arg["mensaje"], arg.get("boton", 0)))
        elif accion == "cancela":  # cancelación por el enlace del paciente
            agenda.cancel(conn, cita, "paciente", "enlace")
        elif accion == "reprograma":
            agenda.reschedule(conn, cita, at(arg["dia"], arg["hora"]), "auxiliar", "auxiliar")
        elif accion == "baja_correo":  # el enlace de baja de un correo
            from estudia import correo
            correo.dar_de_baja(conn, pac)
        elif accion == "escribe":
            from estudia import messaging
            messaging.receive(conn, pac, text=arg)
        else:
            raise ValueError(f"Paso desconocido: {accion}")
    return {"fotos": fotos, **_snapshot(conn)} if fotos else _snapshot(conn)


def _sin_tokens(texto: str) -> str:
    texto = re.sub(r"/p/[^/\s]+", "/p/<token>", texto)
    return re.sub(r"/correo/baja/[^/\s]+", "/correo/baja/<token>", texto)


def _ejecutar_asignacion(conn, caso: dict) -> dict:
    """Escenarios de «cualquier especialista»: quién queda asignado y qué espacios se ofrecen."""
    dado = caso["dado"]
    pros = {n: make_pro(conn, n) for n in dado["profesionales"]}
    pac = make_patient(conn, **dado["paciente"])
    otro = make_patient(conn, nombres="Otra", apellidos="Persona")
    resultados = []
    for paso in caso["pasos"]:
        (accion, arg), = paso.items()
        if accion == "ocupa":  # otra persona ya tiene ese espacio con un especialista concreto
            book(conn, otro, pros[arg["profesional"]], at(arg["dia"], arg["hora"]))
        elif accion == "agenda":
            quien = None if arg["profesional"] == "cualquiera" else pros[arg["profesional"]]
            try:
                cid = book(conn, pac, quien, at(arg["dia"], arg["hora"]))
                asignado = conn.execute("select p.nombre from cita c join profesional p on p.id=c.profesional_id "
                                        "where c.id=%s", (cid,)).fetchone()["nombre"]
                resultados.append({"agenda": f"{arg['profesional']} -> {asignado}"})
            except agenda.SlotTaken:
                resultados.append({"agenda": f"{arg['profesional']} -> sin espacio"})
        elif accion == "espacios":
            from estudia.agenda import any_slots, day_slots
            servicio, dia = svc(conn, "Valoración o revisión"), at(arg["dia"], "08:00").date()
            horas = (sorted({h for p in pros.values() for h in day_slots(conn, p, servicio, dia)})
                     if arg["profesional"] == "cualquiera" else day_slots(conn, pros[arg["profesional"]], servicio, dia))
            if arg["profesional"] == "cualquiera":
                assert dia in any_slots(conn, servicio) and any_slots(conn, servicio)[dia] == horas
            resultados.append({"espacios": arg["profesional"], "horas": [h.strftime("%H:%M") for h in horas
                                                                         if h.strftime("%H:%M") in arg["ver"]]})
        else:
            raise ValueError(f"Paso desconocido: {accion}")
    citas = [{"profesional": c["nombre"], "paciente": c["nombres"], "inicio": _delta(c["rango"].lower)} for c in conn.execute(
        "select p.nombre, pa.nombres, c.rango from cita c join profesional p on p.id=c.profesional_id "
        "join paciente pa on pa.id=c.paciente_id order by c.id")]
    return {"resultados": resultados, "citas": citas}


def _snapshot(conn) -> dict:
    mensajes = [{
        "direccion": m["direccion"], "plantilla": m["plantilla"], "estado": m["estado_entrega"],
        "momento": _delta(m["momento"]), "texto": _sin_tokens(m["texto"] or ""),
        "botones": [b["title"] for b in (m["botones"] or [])],
        **({"canal": m["canal"], "asunto": m["asunto"]} if m["canal"] == "correo" else {}),
    } for m in conn.execute("select * from mensaje order by id")]
    pendientes = [{"tipo": t["tipo"], "ejecutar_en": _delta(t["ejecutar_en"])} for t in conn.execute(
        "select tipo, ejecutar_en from tarea_programada where estado='pendiente' order by ejecutar_en, id")]
    citas = [{"estado": c["estado"], "inicio": _delta(c["rango"].lower) if c["rango"] else None}
             for c in conn.execute("select estado, rango from cita order by id")]
    return {"mensajes": mensajes, "citas": citas, "tareas_pendientes": pendientes}


@pytest.mark.parametrize("ruta", CASOS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_golden(conn, ruta):
    caso = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    obtenido = _ejecutar_asignacion(conn, caso) if "profesionales" in caso["dado"] else _ejecutar(conn, caso)
    golden = ruta.with_suffix(".golden.yaml")
    if ACTUALIZAR:
        golden.write_text(yaml.safe_dump(obtenido, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
        return
    assert golden.exists(), f"Falta {golden.name}. Genéralo con `make golden-update` y revísalo."
    assert obtenido == yaml.safe_load(golden.read_text(encoding="utf-8")), (
        f"El resultado cambió respecto de {golden.name}. Si es intencional: `make golden-update` y revisa el diff.")
