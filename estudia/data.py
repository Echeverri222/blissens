"""Datos: ficticios (Faker es_CO, reproducibles) e importación de Excel (solo local)."""
import json
import random
import re
import sys
import unicodedata
from datetime import date, datetime, time, timedelta

import psycopg
from faker import Faker

from . import agenda, catalog, clock, config, db, followup, indicators, lifecycle, settings, usuarios
from .agenda import rng

TABLES = ["acceso", "hecho_diario_profesional", "hecho_diario", "solicitud_adjunto", "solicitud_contacto", "tarea_programada", "mensaje",
          "oferta_adelanto", "cupo_liberado", "intento", "caso_seguimiento", "cancelacion", "historial_estado",
          "cita", "tratamiento", "bloqueo", "horario_atencion", "paciente", "profesional", "servicio",
          "motivo_cancelacion", "plantilla", "configuracion"]


def wipe(conn) -> None:
    """Vacía SOLO el negocio activo (nunca los demás), sin tocar usuarios ni el negocio mismo."""
    for t in TABLES:
        conn.execute(f"delete from {t} where negocio_id = negocio_activo()")


VALORES_DEMO = {  # pesos, ficticios y redondos (nunca cifras reales)
    "Valoración o revisión": 80_000, "Limpieza": 100_000, "Control de ortodoncia o alineadores": 150_000,
    "Urgencia": 120_000, "Resina u operatoria": 200_000, "Blanqueamiento": 350_000,
    "Preparación de rehabilitación": 400_000, "Cirugía": 500_000,
}


def valores_demo(conn) -> None:
    """Fija el valor ficticio de los servicios del catálogo (solo el negocio activo). Seguro de repetir."""
    for nombre, valor in VALORES_DEMO.items():
        conn.execute("update servicio set valor=%s where nombre=%s", (valor, nombre))


def _at(day: date, hhmm: time) -> datetime:
    return datetime.combine(day, hhmm, tzinfo=clock.TZ)


def _cerrar_tratamiento(conn, rnd, tid, fin: str, today: date) -> None:
    """Estado final del plan según cómo terminó su cadena de citas. Los que se perdieron hace poco siguen activos:
    son los que la detección de riesgo debe encontrar."""
    estado = "activo"
    if fin == "finalizado":
        estado = "finalizado"
    elif fin == "perdido":
        ultima = conn.execute("select max(dia) d from cita where tratamiento_id=%s", (tid,)).fetchone()["d"]
        if ultima and ultima < today - timedelta(days=60) and rnd.random() < 0.5:
            estado = "abandonado"
    conn.execute("update tratamiento set estado=%s where id=%s", (estado, tid))


# Equipo ficticio con las especialidades que describe la ficha del reto. El título es dato: no se deduce del nombre.
PROFESIONALES = [
    ("Dra. Laura Restrepo", "Rehabilitación oral"),
    ("Dr. Santiago Gómez", "Cirugía oral e implantología"),
    ("Dra. Natalia Vélez", "Periodoncia"),
    ("Dr. Felipe Arango", "Ortodoncia"),
]
REHAB, CIRUGIA, PERIO, ORTO = range(4)
SERVICIOS_POR_PROFESIONAL = {  # qué atiende cada uno y con qué peso
    REHAB: {"Valoración o revisión": 20, "Preparación de rehabilitación": 40, "Resina u operatoria": 25,
            "Blanqueamiento": 10, "Urgencia": 5},
    CIRUGIA: {"Valoración o revisión": 25, "Cirugía": 60, "Urgencia": 15},
    PERIO: {"Limpieza": 60, "Valoración o revisión": 25, "Urgencia": 15},
    ORTO: {"Control de ortodoncia o alineadores": 92, "Valoración o revisión": 8},
}
# Perfiles de paciente: (fracción, profesional, sesiones del plan, días entre sesiones, ¿tiene plan?)
PERFILES = {
    "ortodoncia": (0.22, ORTO, (4, 12), (24, 35), True),
    "rehabilitacion": (0.14, REHAB, (3, 8), (10, 21), True),
    "implantes": (0.07, CIRUGIA, (2, 5), (14, 30), True),
    "periodoncia": (0.12, PERIO, (2, 4), (20, 45), True),
    "ocasional": (0.20, None, (1, 2), (45, 120), False),   # revisión, limpieza o urgencia sueltas
    "inactivo": (0.16, None, (1, 2), (30, 90), False),     # vino hace más de 4 meses y no ha vuelto
    "nuevo": (0.09, None, (1, 1), (0, 0), False),          # llegó en estos meses: valoración y, a veces, un plan
}
VENTANA_DIAS = 118     # historia: unos cuatro meses hasta ayer
HORIZONTE_DIAS = 35    # citas futuras: hasta cinco semanas
ESTADOS_PASADOS = (["atendida", "no_asistio", "cancelada", "reprogramada"], [46, 16, 25, 13])
ABANDONO_POR_MES = [0.03, 0.06, 0.10, 0.15]  # el plan se cae cada vez más: nadie hace seguimiento
PIERDE_TRAS_FALLA = 0.4  # tras cancelar o no asistir, muchos no vuelven a agendar (sin protocolo de seguimiento)
SALIO_EN_VIVO = 21     # días: antes de esto el motivo de cancelación casi nunca se registraba


def seed(conn, seed_value: int = 42, patients: int = 420) -> dict:
    """Conjunto ficticio reproducible con la forma de la clínica que describe el reto (nunca sus cifras reales):
    cuatro especialistas, pacientes de ortodoncia y de planes de rehabilitación que se van cayendo, cancelaciones que no
    se reagendan, inasistencias, pacientes nuevos que no vuelven, antiguos inactivos, y cinco semanas futuras."""
    wipe(conn)
    catalog.load(conn)
    valores_demo(conn)
    config.set_(conn, "direccion", "Blissens Odontología, Calle 10 # 43-20, consultorio 301, Medellín")
    rnd = random.Random(seed_value)
    fake = Faker("es_CO")
    Faker.seed(seed_value)
    now = clock.now(conn)
    today = now.date()
    inicio = today - timedelta(days=VENTANA_DIAS)

    pros = []
    for nombre, esp in PROFESIONALES:
        pid = conn.execute("insert into profesional(nombre, especialidad) values (%s,%s) returning id",
                           (nombre, esp)).fetchone()["id"]
        catalog.default_hours(conn, pid)
        pros.append(pid)
    services = conn.execute("select * from servicio order by id").fetchall()
    svc_by_name = {s["nombre"]: s for s in services}
    reasons = [r["id"] for r in conn.execute("select id from motivo_cancelacion order by orden")]
    reason_weights = [14, 20, 10, 8, 14, 12, 6, 16]
    umbral_tardia = config.get(conn, "umbral_tardia_horas")

    busy: dict[int, list[tuple[datetime, datetime]]] = {p: [] for p in pros}

    def free(pro, s, e):
        return not any(b0 < e and s < b1 for b0, b1 in busy[pro])

    def pick_slot(pro, day, dur, after=None):
        """Busca un espacio libre ese día dentro del horario de atención."""
        if day.weekday() > 4:
            return None
        windows = [(time(8, 0), time(12, 0)), (time(13, 0), time(17, 0))]
        cands = []
        for w0, w1 in windows:
            cur = _at(day, w0)
            while cur + timedelta(minutes=dur) <= _at(day, w1):
                if (after is None or cur >= after) and free(pro, cur, cur + timedelta(minutes=dur)):
                    cands.append(cur)
                cur += timedelta(minutes=30)
        return rnd.choice(cands) if cands else None

    def slot_from(pro, day, dur, after=None):
        """El primer día hábil desde `day` (hasta una semana) con espacio para ese profesional."""
        for k in range(7):
            start = pick_slot(pro, day + timedelta(days=k), dur, after)
            if start:
                return start
        return None

    def make_appt(pid, pro, svc, start, estado, origen="paciente", tid=None, detail="Datos ficticios"):
        dur = svc["duracion_min"]
        busy[pro].append((start, start + timedelta(minutes=dur)))
        cid = conn.execute(
            "insert into cita(paciente_id, profesional_id, servicio_id, tratamiento_id, dia, rango, estado, origen, creada_en) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
            (pid, pro, svc["id"], tid, start.date(), rng(start, dur), estado, origen,
             min(now, start - timedelta(days=rnd.randint(2, 20))))).fetchone()["id"]
        conn.execute("insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, detalle, momento) "
                     "values (%s,null,%s,'sistema',%s,%s)",
                     (cid, estado, detail, min(now, start - timedelta(days=1))))
        return cid

    def cancellation(cid, start, canal, hours_ahead, at, con_motivo=True):
        conn.execute(
            "insert into cancelacion(cita_id, motivo_id, canal, antelacion_horas, tardia, momento) values (%s,%s,%s,%s,%s,%s)",
            (cid, rnd.choices(reasons, reason_weights)[0] if con_motivo else None, canal, hours_ahead,
             hours_ahead < umbral_tardia, at))

    def servicio_de(pro_idx, primera=False):
        if primera:
            return svc_by_name["Valoración o revisión"]
        pesos = SERVICIOS_POR_PROFESIONAL[pro_idx]
        return svc_by_name[rnd.choices(list(pesos), list(pesos.values()))[0]]

    def pasado(pid, pro_idx, svc, start, tid):
        """Una cita ya ocurrida, con lo que pasó: atendida, inasistencia, cancelación (a veces sin motivo) o cambio."""
        pro = pros[pro_idx]
        est = rnd.choices(*ESTADOS_PASADOS)[0]
        cid = make_appt(pid, pro, svc, start, est, tid=tid)
        if est == "cancelada":
            tardia = rnd.random() < 0.4
            horas = rnd.randint(1, umbral_tardia - 1) if tardia else rnd.randint(umbral_tardia, 96)
            reciente = start.date() > today - timedelta(days=SALIO_EN_VIVO)
            canal = rnd.choice(["whatsapp", "enlace", "auxiliar"]) if reciente else rnd.choices(["whatsapp", "auxiliar"], [70, 30])[0]
            cancellation(cid, start, canal, horas, start - timedelta(hours=horas), con_motivo=reciente or rnd.random() < 0.3)
        elif est in ("atendida", "no_asistio") and rnd.random() < 0.85:  # recordatorio automático del software
            conn.execute("update cita set datos_origen='{\"recordatorio_enviado\": true}' where id=%s", (cid,))
            if rnd.random() < (0.55 if est == "atendida" else 0.15):
                conn.execute("insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, detalle, momento) "
                             "values (%s,'programada','confirmada','paciente','Confirmó por WhatsApp',%s)",
                             (cid, start - timedelta(days=1)))
        return cid, est

    def futura(pid, pro_idx, svc, start, tid):
        lead = start - now
        est = "confirmada" if lead < timedelta(hours=24) else "programada"
        cid = make_appt(pid, pros[pro_idx], svc, start, est, tid=tid)
        if est == "programada":
            agenda._schedule_reminders(conn, cid, start, now)
        return cid

    def recorrido(pid, pro_idx, tid, desde, sesiones, intervalo, plan):
        """La cadena de citas de un paciente desde `desde`: avanza con cada atención, se reagenda tras una falla o se
        pierde (sin seguimiento). Termina en la primera cita futura. Devuelve 'finalizado', 'perdido' o 'vigente'."""
        day, hechas = desde, 0
        primera = True
        while hechas < sesiones:
            if day > today + timedelta(days=HORIZONTE_DIAS):
                return "vigente"
            svc = servicio_de(pro_idx, primera=primera and not plan)
            start = slot_from(pros[pro_idx], day, svc["duracion_min"],
                              after=now + timedelta(hours=2) if day >= today else None)
            if start is None:
                day += timedelta(days=7)
                continue
            if start >= now:
                futura(pid, pro_idx, svc, start, tid)
                return "vigente"
            cid, est = pasado(pid, pro_idx, svc, start, tid)
            primera = False
            mes = min(3, (start.date() - inicio).days // 30)
            if est == "atendida":
                hechas += 1
                if plan and rnd.random() < ABANDONO_POR_MES[mes]:
                    return "perdido"
                day = start.date() + timedelta(days=rnd.randint(*intervalo))
            elif est == "reprogramada":
                day = start.date() + timedelta(days=rnd.randint(2, 10))
            else:  # cancelada o no asistió
                if rnd.random() < PIERDE_TRAS_FALLA:
                    return "perdido"
                if est == "cancelada":  # la reagendó: cuenta como cancelación recuperada
                    conn.execute("update cita set estado='reprogramada' where id=%s", (cid,))
                day = start.date() + timedelta(days=rnd.randint(3, 15))
        return "finalizado"

    # --- Pacientes por perfil ---
    perfiles = []
    for nombre, (frac, *_rest) in PERFILES.items():
        perfiles += [nombre] * max(1, round(patients * frac))
    perfiles = perfiles[:patients]
    rnd.shuffle(perfiles)
    used_docs = set()
    pat_ids = []
    for i, perfil in enumerate(perfiles):
        while True:
            doc = str(rnd.randint(10_000_000, 1_099_999_999))
            if doc not in used_docs:
                used_docs.add(doc)
                break
        _, pro_idx, sesiones, intervalo, plan = PERFILES[perfil]
        if pro_idx is None:
            pro_idx = rnd.choices([REHAB, PERIO, CIRUGIA], [45, 45, 10])[0]
        if perfil == "nuevo":
            primera = inicio + timedelta(days=rnd.randint(0, VENTANA_DIAS + 10))
            creado = _at(primera, time(8, 0)) - timedelta(days=rnd.randint(2, 10))
        else:
            creado = now - timedelta(days=rnd.randint(VENTANA_DIAS + 15, 900))
            # La mayoría de los planes ya iban a mitad de camino cuando empieza la ventana; unos pocos arrancan después.
            arranca_ya = plan and rnd.random() < 0.75
            primera = inicio + timedelta(days=rnd.randint(0, intervalo[1] if arranca_ya else VENTANA_DIAS))
        alto_valor = perfil in ("rehabilitacion", "implantes")  # quienes viajan a rehabilitarse
        segmento = rnd.choices(["local", "internacional", "deportista"],
                               [77, 15, 8] if alto_valor else [92, 3, 5])[0]
        nombre, apellidos = fake.first_name(), f"{fake.last_name()} {fake.last_name()}"
        celular = ("+1" + str(rnd.randint(2_000_000_000, 9_999_999_999)) if segmento == "internacional" and rnd.random() < 0.6
                   else "+573" + str(rnd.randint(0, 999_999_999)).zfill(9))
        pid = conn.execute(
            "insert into paciente(external_id, nombres, apellidos, documento, celular, correo, fecha_nacimiento, "
            "internacional, deportista, segmento_origen, consentimiento_en, creado_en) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
            (f"F{i + 1}", nombre, apellidos, doc, celular, f"paciente{i + 1}@ejemplo.com",
             fake.date_of_birth(minimum_age=12 if perfil == "ortodoncia" else 18, maximum_age=35 if perfil == "ortodoncia" else 80),
             segmento == "internacional", segmento == "deportista",
             "importacion" if segmento != "local" else None, creado, min(creado, now))).fetchone()["id"]
        pat_ids.append(pid)

        if perfil == "inactivo":  # última visita hace más de cuatro meses
            day = today - timedelta(days=rnd.randint(VENTANA_DIAS + 10, 330))
            for _ in range(rnd.randint(*sesiones)):
                svc = servicio_de(pro_idx, primera=True) if rnd.random() < 0.4 else servicio_de(pro_idx)
                start = slot_from(pros[pro_idx], day, svc["duracion_min"])
                if start and start.date() < inicio:
                    make_appt(pid, pros[pro_idx], svc, start, "atendida")
                day += timedelta(days=rnd.randint(*intervalo))
            continue

        if perfil == "nuevo":
            fin = recorrido(pid, pro_idx, None, primera, 1, (0, 0), False)
            if fin == "finalizado" and rnd.random() < 0.35:  # la valoración se convierte en un plan
                plan_idx = rnd.choice([REHAB, CIRUGIA])
                _, _, ses, inter, _ = PERFILES["rehabilitacion" if plan_idx == REHAB else "implantes"]
                tid = conn.execute(
                    "insert into tratamiento(paciente_id, profesional_id, tipo, estado, generado_en) values "
                    "(%s,%s,'tratamiento','activo',%s) returning id",
                    (pid, pros[plan_idx], min(today, primera + timedelta(days=3)))).fetchone()["id"]
                ultima = conn.execute("select max(dia) d from cita where paciente_id=%s", (pid,)).fetchone()["d"]
                fin = recorrido(pid, plan_idx, tid, ultima + timedelta(days=rnd.randint(5, 15)),
                                rnd.randint(*ses), inter, True)
                _cerrar_tratamiento(conn, rnd, tid, fin, today)
            continue

        tid = None
        if plan:
            tid = conn.execute(
                "insert into tratamiento(paciente_id, profesional_id, tipo, estado, generado_en) values (%s,%s,%s,'activo',%s) "
                "returning id", (pid, pros[pro_idx], "tratamiento", min(creado.date() + timedelta(days=7), primera))
            ).fetchone()["id"]
        fin = recorrido(pid, pro_idx, tid, primera, rnd.randint(*sesiones), intervalo, plan)
        if tid:
            _cerrar_tratamiento(conn, rnd, tid, fin, today)

    # --- Escenarios para que todas las bandejas tengan contenido ---
    def scenario_future(pro, days_ahead_range, count):
        out = []
        for _ in range(count):
            pid = rnd.choice(pat_ids)
            svc = servicio_de(pros.index(pro))
            day = today + timedelta(days=rnd.randint(*days_ahead_range))
            start = pick_slot(pro, day, svc["duracion_min"], after=now + timedelta(hours=3))
            if start:
                busy[pro].append((start, start + timedelta(minutes=svc["duracion_min"])))
                out.append((pid, svc, start))
        return out

    # No confirmadas: citas próximas sin respuesta.
    for pro in pros:
        for pid, svc, start in scenario_future(pro, (1, 2), 2):
            cid = make_appt(pid, pro, svc, start, "no_confirmada")
            conn.execute("update cita set datos_origen = '{\"recordatorio_enviado\": true}' where id=%s", (cid,))
    # Programadas de mañana con el recordatorio de 48 h ya enviado: la tarea de 24 h las pasará a «sin confirmar».
    for pro in pros:
        for pid, svc, start in scenario_future(pro, (1, 1), 1):
            cid = make_appt(pid, pro, svc, start, "programada")
            conn.execute("update cita set datos_origen = %s::jsonb where id=%s",
                         (json.dumps({"recordatorio_enviado": True, "recordatorio_en": (now - timedelta(hours=3)).isoformat()}), cid))
            agenda._schedule_reminders(conn, cid, start, now)
    # Cancelaciones recientes con caso abierto y cupo libre.
    for pro in pros:
        for pid, svc, start in scenario_future(pro, (3, 9), 2):
            cid = make_appt(pid, pro, svc, start, "programada")
            lifecycle.transition(conn, cid, "cancelada", "paciente", "Cancelación por whatsapp")
            cancellation(cid, start, "whatsapp", round((start - now).total_seconds() / 3600, 1), now - timedelta(hours=5))
            conn.execute("insert into cupo_liberado(profesional_id, rango, cita_origen_id, causa, creado_en) "
                         "values (%s,%s,%s,'cancelacion',%s)", (pro, rng(start, svc["duracion_min"]), cid, now))
            caso = followup.open_case(conn, "cancelacion", pid, cita_id=cid, send_first=False)
            if caso:
                followup.send_attempt(conn, caso, "cancelacion_recibida")
    # Casos agotados y escalados (de hace semanas).
    for pid in rnd.sample(pat_ids, 3):
        caso = conn.execute(
            "insert into caso_seguimiento(tipo, paciente_id, estado, escalado, abierto_en, cerrado_en) "
            "values ('tratamiento_a_medias',%s,'agotado',true,%s,%s) returning id",
            (pid, now - timedelta(days=30), now - timedelta(days=3))).fetchone()["id"]
        for n in range(1, 5):
            conn.execute("insert into intento(caso_id, numero, canal, resultado, momento) values (%s,%s,'automatico',"
                         "'sin_respuesta',%s)", (caso, n, now - timedelta(days=30 - 7 * n)))
    # Citas sin desenlace: ayer y hoy antes de la hora actual.
    for pro in pros:
        for day in (today - timedelta(days=1), today):
            for _ in range(2):
                pid = rnd.choice(pat_ids)
                svc = servicio_de(pros.index(pro))
                start = pick_slot(pro, day, svc["duracion_min"])
                if start and start < now - timedelta(minutes=svc["duracion_min"]):
                    make_appt(pid, pro, svc, start, rnd.choice(["confirmada", "programada"]))
    # Mensajes sin interpretar y solicitud de contacto.
    for pid, texto in zip(rnd.sample(pat_ids, 5), ["Hola, ¿tienen disponibilidad para mañana?",
                                                    "Gracias, ¿puedo pagar con transferencia?",
                                                    "¿Hasta qué hora atienden los viernes?",
                                                    "Buenas, no voy a poder ir esta semana, ¿me pueden mover la cita?",
                                                    "Hi, I'll be in Medellín next month, can I continue my treatment?"]):
        conn.execute("insert into mensaje(paciente_id, direccion, texto, gestionado, momento) values (%s,'entrante',%s,false,%s)",
                     (pid, texto, now - timedelta(hours=rnd.randint(1, 20))))
    conn.execute("insert into solicitud_contacto(documento, celular, nota, momento) values (%s,%s,%s,%s)",
                 ("00000000", "+573000000000", "Documento ya registrado con otro celular", now - timedelta(hours=3)))
    # Una evaluación virtual desde el sitio en inglés (datos ficticios; los correos ya figuran enviados).
    conn.execute(
        "insert into solicitud_contacto(documento, celular, nota, momento, origen, interes, idioma, nombre, correo, pais, "
        "mensaje, aviso_enviado_en, acuse_enviado_en) values ('—','+13055550100','Sitio web · Evaluación virtual',%s,"
        "'sitio','evaluacion_virtual','en','Visitante de Ejemplo','visitante@example.com','Estados Unidos',"
        "'I would like a quote for veneers. I can travel in March.',%s,%s)", (now - timedelta(hours=5),) * 3)

    # Dos pacientes dados de baja con cita próxima: sus citas se gestionan a mano.
    conn.execute("update paciente set acepta_mensajes=false where id in (select paciente_id from cita "
                 "where estado='programada' and lower(rango) > %s order by lower(rango) desc limit 2)", (now + timedelta(days=3),))
    config.set_(conn, "ultimo_diario", today.isoformat())
    indicators.close_range(conn, inicio, today - timedelta(days=1))
    n = {t: conn.execute(f"select count(*) as n from {t}").fetchone()["n"] for t in ("paciente", "cita", "mensaje")}
    n["usuarios"] = usuarios.crear_demo(conn)
    return n


# ---------------------------------------------------------------- Importación de Excel

def _norm(texto) -> str:
    """Clave de comparación: minúsculas, sin tildes ni puntuación y con los espacios colapsados."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


# Estado del software de la clínica (clave normalizada) -> (estado de la cita, quién canceló si es una cancelación).
# «Anulado» lo anula la clínica; «anulado por pte./pcte. vía WhatsApp» lo anula el paciente.
_ESTADOS_ORIGEN = {
    "atendido": ("atendida", None), "cambio de fecha": ("reprogramada", None),
    "anulado": ("cancelada", "clinica"),
    "anulado por pte via whatsapp": ("cancelada", "whatsapp"), "anulado por pcte via whatsapp": ("cancelada", "whatsapp"),
    "no asiste": ("no_asistio", None),
    "confirmado por telefono": ("confirmada", None), "confirmado por email": ("confirmada", None),
    "confirmado whatsapp": ("confirmada", None), "confirmado por whatsapp": ("confirmada", None),
    "confirmado por pte via whatsapp": ("confirmada", None), "confirmado por pcte via whatsapp": ("confirmada", None),
    "confirmado": ("confirmada", None),
    "no confirmado": ("programada", None), "notificado": ("programada", None), "notif automatica": ("programada", None),
    "notif fallida": ("programada", None),
}
ESTADOS = _ESTADOS_ORIGEN


def estado_de(texto) -> tuple[str, str | None] | None:
    """(estado, canal de cancelación) del texto del software, o None si no se reconoce."""
    k = _norm(texto)
    if k in _ESTADOS_ORIGEN:
        return _ESTADOS_ORIGEN[k]
    palabras = set(k.split())
    if "anulado" in palabras and "whatsapp" in palabras and palabras & {"pte", "pcte", "paciente"}:
        return "cancelada", "whatsapp"
    return None


KEYWORDS = [  # (palabras clave, nombre de servicio)
    (("limpieza", "profilaxis", "detartraje"), "Limpieza"),
    (("urgencia", "dolor"), "Urgencia"),
    (("blanqueamiento",), "Blanqueamiento"),
    (("resina", "operatoria", "calza", "obturacion", "obturación"), "Resina u operatoria"),
    (("cirugia", "cirugía", "extraccion", "extracción", "implante"), "Cirugía"),
    (("rehabilitacion", "rehabilitación", "corona", "carilla", "protesis", "prótesis"), "Preparación de rehabilitación"),
    (("control", "ortodoncia", "alineador", "brackets"), "Control de ortodoncia o alineadores"),
    (("revision", "revisión", "valoracion", "valoración", "diagnostico", "diagnóstico"), "Valoración o revisión"),
]


def normalize_phone(raw) -> str | None:
    if raw is None:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if digits.endswith("0") and "." in str(raw):  # '3001234567.0'
        digits = "".join(ch for ch in str(raw).split(".")[0] if ch.isdigit())
    if len(digits) == 10 and digits.startswith("3"):
        return "+57" + digits
    if len(digits) == 12 and digits.startswith("57") and digits[2] == "3":
        return "+" + digits
    return None


def infer_service(comment, services_by_name) -> str:
    text = (str(comment) if comment is not None else "").lower()
    for words, name in KEYWORDS:
        if any(w in text for w in words):
            return name
    return "Otro"


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in ("", "nan", "nat", "none") else s


def _id(v):
    s = _s(v)
    if s is None:
        return None
    try:
        return str(int(float(s)))
    except ValueError:
        return s


SEGMENTOS = (("internacional", ("internac", "exterior", "extranj", "foreign")), ("deportista", ("deport", "atleta")))


def segmentos_de(*textos) -> dict[str, bool]:
    """Las marcas de alto valor que dice «Tipo Paciente» en el software de la clínica. Solo cuenta una palabra que
    empieza así («Deportista», «del exterior»), no una que la lleve dentro («Coldeportes»)."""
    t = " ".join(filter(None, (_s(x) for x in textos))).lower()
    return {marca: any(re.search(rf"\b{w}", t) for w in palabras) for marca, palabras in SEGMENTOS}


ANONIMO_AVISO = "Datos anonimizados: no los publiques igual; son solo para la demo local."


def _edad_a_fecha(nacimiento: date, hoy: date) -> date:
    """Una fecha de nacimiento (1 de julio) que conserva la edad que tiene hoy la persona."""
    edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    return date(hoy.year - edad - ((hoy.month, hoy.day) < (7, 1)), 7, 1)


def importar(conn, folder=None, anonimo: bool = False, anonimo_profesionales: bool = False) -> dict:
    """Importa agenda y estados desde una carpeta local ignorada por git. Idempotente; no dispara mensajes ni casos.

    Con `anonimo` (R23) los pacientes salen como «Paciente001…», sin apellido, documento ni correo; el celular pasa a un
    número falso del simulador, la fecha de nacimiento conserva solo la edad y todas las fechas se corren un número fijo
    de semanas (que solo vive en memoria). No se guarda el texto original del estado."""
    import pandas as pd

    folder = folder or settings.DATOS_REALES_DIR
    from pathlib import Path
    files = list(Path(folder).glob("*.xlsx"))
    f_states = next((f for f in files if "estados" in f.name.lower()), None)
    f_agenda = next((f for f in files if "estados" not in f.name.lower() and "agenda" in f.name.lower()), None)
    if not f_states or not f_agenda:
        raise SystemExit(f"No encontré los archivos de agenda y de estados en {folder}")
    est = pd.read_excel(f_states, dtype=str)
    ag = pd.read_excel(f_agenda, dtype=str)
    est.columns = [c.strip() for c in est.columns]
    ag.columns = [c.strip() for c in ag.columns]

    def col(df, prefix):
        return next(c for c in df.columns if c.lower().startswith(prefix.lower()))

    def col_opcional(df, prefix):
        return next((c for c in df.columns if c.lower().startswith(prefix.lower())), None)

    # «Convenio» es la aseguradora: no dice el segmento. El comentario de la cita (p. ej. «Deportista») se lee en memoria
    # para marcar el segmento y nunca se guarda: puede traer notas clínicas.
    c_segmento = [c for c in (col_opcional(ag, "Tipo Paciente"), col_opcional(ag, "Comentario")) if c]
    c_antiguedad = col_opcional(est, "Antigüedad")
    hoy = clock.now(conn).date()
    desfase = timedelta(weeks=random.SystemRandom().choice([w for w in range(-26, 27) if w])) if anonimo else timedelta(0)
    numeros: dict[str, dict[str, int]] = {"paciente": {}, "cita": {}, "tratamiento": {}, "profesional": {}}

    def numero(clase: str, clave: str) -> int:
        return numeros[clase].setdefault(clave, len(numeros[clase]) + 1)

    c_cita_e, c_cita_a = col(est, "# Cita"), col(ag, "# Cita")
    ag["_k"] = ag[c_cita_a].map(_id)
    ag = ag.drop_duplicates("_k").set_index("_k")
    yes_no = [c for c in est.columns if est[c].dropna().isin(["Sí", "No"]).all() and est[c].notna().any()]

    if conn.execute("select 1 from paciente where external_id ~ '^F[0-9]+$' limit 1").fetchone():
        wipe(conn)  # no se mezclan datos ficticios con reales
    catalog.load(conn)
    services = {r["nombre"]: r["id"] for r in conn.execute("select id, nombre from servicio")}
    if "Otro" not in services:
        services["Otro"] = conn.execute(
            "insert into servicio(nombre, duracion_min, autoagendable, admite_adelanto) values ('Otro',30,false,false) "
            "on conflict (negocio_id, nombre) do update set nombre='Otro' returning id").fetchone()["id"]

    pros: dict[str, int] = {}
    stats = {"citas": 0, "pacientes": 0, "sin_hora": 0, "estado_desconocido": 0, "segmentados": 0, "por_depurar": 0}
    seen_patients = set()
    for _, r in est.iterrows():
        cid_ext = _id(r[c_cita_e])
        if not cid_ext:
            continue
        a = ag.loc[cid_ext] if cid_ext in ag.index else None
        # Profesional
        pname = " ".join(filter(None, [_s(r.get(col(est, "Nombre Profesional"))),
                                         _s(r.get(col(est, "Apellidos Profesional")))])) or "Sin asignar"
        if anonimo_profesionales:
            pname = f"Especialista {chr(64 + numero('profesional', pname))}" if numero("profesional", pname) <= 26 \
                else f"Especialista {numero('profesional', pname)}"
        if pname not in pros:
            row = conn.execute(
                "insert into profesional(nombre, especialidad, external_id) values (%s,%s,%s) "
                "on conflict (negocio_id, external_id) do update set nombre=excluded.nombre returning id",
                (pname, _s(r.get(col(est, "Especialidad"))) or "", f"prof:{pname}")).fetchone()
            pros[pname] = row["id"]
            if not conn.execute("select 1 from horario_atencion where profesional_id=%s", (row["id"],)).fetchone():
                catalog.default_hours(conn, row["id"])
        pro = pros[pname]
        # Paciente
        pext = _id(r[col(est, "# Paciente")])
        if pext not in seen_patients:
            doc = _s(a[col(ag, "#Número de identificación")]) if a is not None else None
            birth = None
            if a is not None and _s(a.get(col(ag, "Fecha de nac"))):
                try:
                    d = pd.to_datetime(a[col(ag, "Fecha de nac")]).date()
                    birth = d if d.year > 1920 else None
                except Exception:
                    birth = None
            phone = normalize_phone(a[col(ag, "Celular")]) if a is not None else None
            correo = _s(a[col(ag, "E-Mail")]) if a is not None else None
            nombres, apellidos = _s(r[col(est, "Nombre Paciente")]) or "", _s(r[col(est, "Apellidos Paciente")]) or ""
            ext = pext
            if anonimo:
                n = numero("paciente", pext)
                nombres, apellidos, doc, correo, ext = f"Paciente{n:03d}", "", None, None, f"anon-{n:03d}"
                phone = f"+57300000{n % 10000:04d}" if phone else None
                birth = _edad_a_fecha(birth, hoy) if birth else None
            cur = conn.execute(
                "insert into paciente(external_id, nombres, apellidos, documento, celular, correo, fecha_nacimiento, "
                "consentimiento_en) values (%s,%s,%s,%s,%s,%s,%s,null) on conflict (negocio_id, external_id) do nothing returning id",
                (ext, nombres, apellidos, doc, phone, correo, birth))
            if cur.fetchone():
                stats["pacientes"] += 1
            seen_patients.add(pext)
        elif a is not None:  # completa datos que faltaban en citas anteriores del mismo paciente
            phone = normalize_phone(a[col(ag, "Celular")])
            if phone:
                if anonimo:
                    phone = f"+57300000{numero('paciente', pext) % 10000:04d}"
                conn.execute("update paciente set celular=%s where external_id=%s and celular is null",
                             (phone, f"anon-{numero('paciente', pext):03d}" if anonimo else pext))
        pat = conn.execute("select id from paciente where external_id=%s",
                           (f"anon-{numero('paciente', pext):03d}" if anonimo else pext,)).fetchone()["id"]
        marcas = segmentos_de(*(a[c] for c in c_segmento)) if a is not None else {}
        if any(marcas.values()):  # solo suma marcas (y confirma las del sitio en inglés); lo que decidió la recepción no se toca
            if conn.execute(
                    "update paciente set internacional = internacional or %s, deportista = deportista or %s, "
                    "segmento_origen='importacion', segmento_marcado_en=%s, segmento_marcado_por=null "
                    "where id=%s and segmento_origen is distinct from 'recepcion' "
                    "and (internacional < %s or deportista < %s or segmento_origen = 'sitio_en') returning id",
                    (marcas["internacional"], marcas["deportista"], clock.now(conn), pat,
                     marcas["internacional"], marcas["deportista"])).fetchone():
                stats["segmentados"] += 1
        # Tratamiento
        text_ = _id(r[col(est, "# Tratamiento")])
        tid = None
        if text_:
            tipo = "diagnostico" if "diagn" in (_s(r.get(col(est, "Tratamiento o"))) or "").lower() else "tratamiento"
            tid = conn.execute(
                "insert into tratamiento(paciente_id, profesional_id, tipo, external_id) values (%s,%s,%s,%s) "
                "on conflict (negocio_id, external_id) do update set tipo=excluded.tipo returning id",
                (pat, pro, tipo, f"trat:{numero('tratamiento', text_) if anonimo else text_}")).fetchone()["id"]
        # Cita
        estado_texto = _s(r[col(est, "Estado actual")]) or ""
        reconocido = estado_de(estado_texto)
        if reconocido is None:
            stats["estado_desconocido"] += 1
        estado, canal_cancelacion = reconocido or ("programada", None)
        dia = pd.to_datetime(r[col(est, "Fecha Cita")]).date() + desfase
        rango, servicio = None, "Otro"
        if a is not None:
            servicio = infer_service(a.get(col(ag, "Comentario")), services)
            h0, h1 = _s(a.get(col(ag, "Hora Inicio"))), _s(a.get(col(ag, "Hora Fin")))
            if h0 and h1:
                t0, t1 = pd.to_datetime(h0).time(), pd.to_datetime(h1).time()
                s, e = _at(dia, t0), _at(dia, t1)
                if e > s:
                    rango = rng(s, int((e - s).total_seconds() // 60))
        if servicio == "Otro" and _norm(_s(r.get(col(est, "Especialidad")))) == "ro":
            servicio = "Valoración o revisión"  # «RO» es Revisión Odontológica si el comentario no dice otro servicio
        if rango is None:
            stats["sin_hora"] += 1
        datos = {c: str(r[c]) for c in yes_no if _s(r[c])}
        if not anonimo:
            datos["estado_origen"] = estado_texto  # texto original, para auditar el mapeo
        if c_antiguedad and _norm(_s(r.get(c_antiguedad))) == "no aplica":
            datos["paciente_nuevo"] = True
        por_depurar = estado in ("programada", "confirmada", "no_confirmada") and dia < hoy
        ext_cita = f"cita:{numero('cita', cid_ext) if anonimo else cid_ext}"
        params = (pat, pro, services[servicio], tid, dia, estado, json.dumps(datos), ext_cita)
        for attempt_range in ([rango, None] if rango else [None]):
            try:
                with conn.transaction():
                    row = conn.execute(
                        "insert into cita(paciente_id, profesional_id, servicio_id, tratamiento_id, dia, rango, estado, origen, "
                        "datos_origen, external_id) values (%s,%s,%s,%s,%s,%s,%s,'importacion',%s,%s) "
                        "on conflict (negocio_id, external_id) do update set estado=excluded.estado, datos_origen=excluded.datos_origen "
                        "returning id, (xmax = 0) as nueva",
                        (params[0], params[1], params[2], params[3], params[4], attempt_range, params[5], params[6],
                         params[7])).fetchone()
                break
            except psycopg.errors.ExclusionViolation:
                continue  # se cruza con otra cita viva importada: queda solo con fecha
        if row["nueva"]:
            conn.execute("insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, detalle, momento) "
                         "values (%s,null,%s,'sistema','Importación de Excel',%s)", (row["id"], estado, clock.now(conn)))
            stats["citas"] += 1
        if estado == "cancelada" and canal_cancelacion and not conn.execute(
                "select 1 from cancelacion where cita_id=%s", (row["id"],)).fetchone():
            # Sin motivo, y no abre caso de seguimiento: el importador nunca los abre. Lo que anuló la clínica queda
            # con canal 'clinica' para que los indicadores no lo cuenten como cancelación del paciente.
            conn.execute("insert into cancelacion(cita_id, motivo_id, canal, antelacion_horas, tardia, momento) "
                         "values (%s,null,%s,0,false,%s)", (row["id"], canal_cancelacion, clock.now(conn)))
        if por_depurar and row["nueva"]:
            stats["por_depurar"] += 1
    return stats


def _print_users(users: list[dict]) -> None:
    print("\nUsuarios de demostración (solo con datos ficticios):")
    for u in users:
        print(f"  {u['usuario']:<16} {u['rol']:<13} contraseña: {u['clave']}")


def _negocio() -> str:
    import os
    return os.environ.get("NEGOCIO") or settings.NEGOCIO_POR_DEFECTO


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if cmd in ("seed", "reset") and settings.ENTORNO == "produccion":
        raise SystemExit(f"'{cmd}' no existe en producción: borraría datos de los negocios.")
    if cmd == "importar" and settings.ENTORNO == "demo":
        raise SystemExit("En el entorno demo solo se admiten datos ficticios: 'importar' se niega.")
    if cmd == "seed":
        with db.connect(negocio=_negocio()) as conn:  # solo el negocio indicado
            n = seed(conn)
        print(f"Datos ficticios cargados en '{_negocio()}': {n['paciente']} pacientes, {n['cita']} citas, {n['mensaje']} mensajes.")
        _print_users(n["usuarios"])
    elif cmd == "reset":
        from . import migrate
        with db.connect_admin() as conn:
            conn.execute("drop schema public cascade; create schema public;")
        migrate.run()
        with db.connect(negocio=_negocio()) as conn:
            n = seed(conn)
        print(f"Base reconstruida desde cero: {n['paciente']} pacientes, {n['cita']} citas.")
        _print_users(n["usuarios"])
    elif cmd == "importar":
        anonimo = "--anonimo" in sys.argv[2:]
        if anonimo and settings.ENTORNO != "local":
            raise SystemExit("'importar --anonimo' solo corre en el entorno local: escribe en la base de datos local.")
        with db.connect(negocio=_negocio()) as conn:
            s = importar(conn, anonimo=anonimo, anonimo_profesionales="--anonimo-profesionales" in sys.argv[2:])
        print("Importación terminada:", s)
        if anonimo:
            print(ANONIMO_AVISO)
    else:
        raise SystemExit(f"Comando desconocido: {cmd}")


if __name__ == "__main__":
    main()
