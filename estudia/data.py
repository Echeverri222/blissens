"""Datos: ficticios (Faker es_CO, reproducibles) e importación de Excel (solo local)."""
import json
import random
import re
import sys
from datetime import date, datetime, time, timedelta

import psycopg
from faker import Faker

from . import agenda, catalog, clock, config, db, followup, indicators, lifecycle, settings, usuarios
from .agenda import rng

TABLES = ["acceso", "hecho_diario_profesional", "hecho_diario", "solicitud_contacto", "tarea_programada", "mensaje",
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


def seed(conn, seed_value: int = 42, patients: int = 250) -> dict:
    """Conjunto ficticio reproducible: 2 profesionales, ~250 pacientes, ~4 meses de historia y 3 semanas futuras."""
    wipe(conn)
    catalog.load(conn)
    valores_demo(conn)
    rnd = random.Random(seed_value)
    fake = Faker("es_CO")
    Faker.seed(seed_value)
    now = clock.now(conn)
    today = now.date()

    pros = []
    for esp in ("Odontología general", "Ortodoncia"):
        mujer = rnd.random() < 0.5
        nombre = f"{'Dra.' if mujer else 'Dr.'} {fake.first_name_female() if mujer else fake.first_name_male()} {fake.last_name()}"
        pid = conn.execute("insert into profesional(nombre, especialidad) values (%s,%s) returning id",
                           (nombre, esp)).fetchone()["id"]
        catalog.default_hours(conn, pid)
        pros.append(pid)
    services = conn.execute("select * from servicio order by id").fetchall()
    svc_weights = [25, 15, 30, 5, 15, 5, 3, 2]
    reasons = [r["id"] for r in conn.execute("select id from motivo_cancelacion order by orden")]
    reason_weights = [14, 20, 10, 8, 14, 12, 6, 16]

    busy: dict[int, list[tuple[datetime, datetime]]] = {p: [] for p in pros}

    def free(pro, s, e):
        return not any(b0 < e and s < b1 for b0, b1 in busy[pro])

    def pick_slot(pro, day, dur, after=None):
        """Busca un espacio libre ese día dentro del horario de atención."""
        if day.weekday() > 4:
            return None
        windows = [(time(7, 30), time(12, 0)), (time(13, 0), time(17, 30))]
        cands = []
        for w0, w1 in windows:
            cur = _at(day, w0)
            while cur + timedelta(minutes=dur) <= _at(day, w1):
                if (after is None or cur >= after) and free(pro, cur, cur + timedelta(minutes=dur)):
                    cands.append(cur)
                cur += timedelta(minutes=30)
        return rnd.choice(cands) if cands else None

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

    def cancellation(cid, start, canal, hours_ahead, at):
        conn.execute(
            "insert into cancelacion(cita_id, motivo_id, canal, antelacion_horas, tardia, momento) values (%s,%s,%s,%s,%s,%s)",
            (cid, rnd.choices(reasons, reason_weights)[0], canal, hours_ahead,
             hours_ahead < config.get(conn, "umbral_tardia_horas"), at))

    # --- Pacientes ---
    pat_ids = []
    used_docs = set()
    for i in range(patients):
        while True:
            doc = str(rnd.randint(10_000_000, 1_099_999_999))
            if doc not in used_docs:
                used_docs.add(doc)
                break
        creado = now - timedelta(days=rnd.randint(30, 400))
        nombre, apellidos = fake.first_name(), f"{fake.last_name()} {fake.last_name()}"
        celular = "+573" + str(rnd.randint(0, 999_999_999)).zfill(9)
        nacimiento = fake.date_of_birth(minimum_age=6, maximum_age=80)
        segmento = rnd.choices(["local", "internacional", "deportista"], [88, 6, 6])[0]  # mismo orden de sorteo de siempre
        pid = conn.execute(
            "insert into paciente(external_id, nombres, apellidos, documento, celular, correo, fecha_nacimiento, "
            "internacional, deportista, segmento_origen, consentimiento_en, creado_en) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
            (f"F{i + 1}", nombre, apellidos, doc, celular, f"paciente{i + 1}@ejemplo.com", nacimiento,
             segmento == "internacional", segmento == "deportista",
             "importacion" if segmento != "local" else None, creado, creado)).fetchone()["id"]
        pat_ids.append(pid)

    # --- Tratamientos, historia y citas futuras ---
    n_risk, active_with_future = 0, []
    hist_status = ["atendida", "no_asistio", "cancelada", "reprogramada"]
    hist_weights = [48, 14, 16, 12]
    for idx, pid in enumerate(pat_ids):
        pro = pros[idx % 2] if rnd.random() < 0.85 else rnd.choice(pros)
        has_t = rnd.random() < 0.7
        estado_t = rnd.choices(["activo", "finalizado", "abandonado"], [65, 20, 15])[0] if has_t else None
        tid = None
        if has_t:
            tid = conn.execute(
                "insert into tratamiento(paciente_id, profesional_id, tipo, estado, generado_en) values (%s,%s,%s,%s,%s) "
                "returning id", (pid, pro, rnd.choice(["diagnostico", "tratamiento", "tratamiento"]), estado_t,
                                 today - timedelta(days=rnd.randint(30, 120)))).fetchone()["id"]
        at_risk_p = estado_t == "activo" and n_risk < 18 and idx % 3 == 0
        latest_hist = today - timedelta(days=(40 if at_risk_p else 2))
        if at_risk_p:
            n_risk += 1
        day = today - timedelta(days=rnd.randint(60, 118))
        for _ in range(rnd.randint(1, 5)):
            if day > latest_hist:
                break
            svc = rnd.choices(services, svc_weights)[0]
            start = pick_slot(pro, day, svc["duracion_min"])
            if start:
                est = rnd.choices(hist_status, hist_weights)[0]
                cid = make_appt(pid, pro, svc, start, est, tid=tid)
                if est == "cancelada":
                    cancellation(cid, start, rnd.choice(["whatsapp", "enlace", "auxiliar"]), rnd.randint(2, 70),
                                 start - timedelta(hours=rnd.randint(2, 70)))
                    if rnd.random() < 0.25:  # reagendó después de cancelar
                        conn.execute("update cita set estado='reprogramada' where id=%s", (cid,))
                elif est in ("atendida", "no_asistio") and rnd.random() < 0.7:
                    conn.execute("update cita set datos_origen='{\"recordatorio_enviado\": true}' where id=%s", (cid,))
                    if est == "atendida" and rnd.random() < 0.7:
                        conn.execute("insert into historial_estado(cita_id, estado_anterior, estado_nuevo, actor, detalle, momento) "
                                     "values (%s,'programada','confirmada','paciente','Confirmó por WhatsApp',%s)",
                                     (cid, start - timedelta(days=1)))
            day += timedelta(days=rnd.randint(7, 30))
        if estado_t == "activo" and not at_risk_p:
            active_with_future.append((pid, pro, tid))
        if not has_t and rnd.random() < 0.25:
            active_with_future.append((pid, pro, None))

    # Citas futuras (3 semanas), más densas en los próximos días para poder probar 48 h y 24 h.
    future_days = [today + timedelta(days=d) for d in range(0, 22) if (today + timedelta(days=d)).weekday() < 5]
    for pid, pro, tid in active_with_future:
        if rnd.random() < 0.9:
            svc = rnd.choices(services, svc_weights)[0]
            day = rnd.choice(future_days[:4] if rnd.random() < 0.35 else future_days)
            start = pick_slot(pro, day, svc["duracion_min"])
            if start:
                is_past = start < now
                lead = start - now
                est = "confirmada" if (is_past or lead < timedelta(hours=24)) else "programada"
                cid = make_appt(pid, pro, svc, start, est, tid=tid)
                if not is_past and est == "programada":
                    agenda._schedule_reminders(conn, cid, start, now)

    # --- Escenarios para que todas las bandejas tengan contenido ---
    def scenario_future(pro, days_ahead_range, count):
        out = []
        for _ in range(count):
            pid = rnd.choice(pat_ids)
            svc = rnd.choice(services[:5])
            day = today + timedelta(days=rnd.randint(*days_ahead_range))
            start = pick_slot(pro, day, svc["duracion_min"], after=now + timedelta(hours=3))
            if start:
                busy[pro].append((start, start + timedelta(minutes=svc["duracion_min"])))
                out.append((pid, svc, start))
        return out

    # No confirmadas: citas próximas sin respuesta.
    for pro in pros:
        for pid, svc, start in scenario_future(pro, (1, 2), 4):
            cid = make_appt(pid, pro, svc, start, "no_confirmada")
            conn.execute("update cita set datos_origen = '{\"recordatorio_enviado\": true}' where id=%s", (cid,))
    # Programadas de mañana con el recordatorio de 48 h ya enviado: la tarea de 24 h las pasará a «sin confirmar».
    for pro in pros:
        for pid, svc, start in scenario_future(pro, (1, 1), 2):
            cid = make_appt(pid, pro, svc, start, "programada")
            conn.execute("update cita set datos_origen = %s::jsonb where id=%s",
                         (json.dumps({"recordatorio_enviado": True, "recordatorio_en": (now - timedelta(hours=3)).isoformat()}), cid))
            agenda._schedule_reminders(conn, cid, start, now)
    # Cancelaciones recientes con caso abierto y cupo libre.
    for pro in pros:
        for pid, svc, start in scenario_future(pro, (3, 9), 3):
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
            for _ in range(3):
                pid = rnd.choice(pat_ids)
                svc = rnd.choice(services[:5])
                start = pick_slot(pro, day, svc["duracion_min"])
                if start and start < now - timedelta(minutes=svc["duracion_min"]):
                    make_appt(pid, pro, svc, start, rnd.choice(["confirmada", "programada"]))
    # Mensajes sin interpretar y solicitud de contacto.
    for pid, texto in zip(rnd.sample(pat_ids, 3), ["Hola, ¿tienen disponibilidad para mañana?",
                                                    "Gracias, ¿puedo pagar con transferencia?",
                                                    "¿Hasta qué hora atienden los viernes?"]):
        conn.execute("insert into mensaje(paciente_id, direccion, texto, gestionado, momento) values (%s,'entrante',%s,false,%s)",
                     (pid, texto, now - timedelta(hours=rnd.randint(1, 20))))
    conn.execute("insert into solicitud_contacto(documento, celular, nota, momento) values (%s,%s,%s,%s)",
                 ("00000000", "+573000000000", "Documento ya registrado con otro celular", now - timedelta(hours=3)))

    # Dos pacientes dados de baja con cita próxima: sus citas se gestionan a mano.
    conn.execute("update paciente set acepta_mensajes=false where id in (select paciente_id from cita "
                 "where estado='programada' and lower(rango) > %s order by lower(rango) desc limit 2)", (now + timedelta(days=3),))
    config.set_(conn, "ultimo_diario", today.isoformat())
    indicators.close_range(conn, today - timedelta(days=118), today - timedelta(days=1))
    n = {t: conn.execute(f"select count(*) as n from {t}").fetchone()["n"] for t in ("paciente", "cita", "mensaje")}
    n["usuarios"] = usuarios.crear_demo(conn)
    return n


# ---------------------------------------------------------------- Importación de Excel

ESTADOS = {
    "atendido": "atendida", "cambio de fecha": "reprogramada", "anulado": "cancelada",
    "anulado por pcte. via whatsapp": "cancelada", "no asiste": "no_asistio",
    "confirmado por teléfono": "confirmada", "confirmado por email": "confirmada",
    "confirmado whatsapp": "confirmada", "confirmado por whatsapp": "confirmada",
    "no confirmado": "programada", "notificado": "programada", "notif. automática": "programada",
    "notif. fallida": "programada",
}

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


def importar(conn, folder=None) -> dict:
    """Importa agenda y estados desde una carpeta local ignorada por git. Idempotente; no dispara mensajes ni casos."""
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

    c_segmento = [c for c in (col_opcional(ag, "Tipo Paciente"),) if c]  # «Convenio» es la aseguradora: no dice el segmento

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
    stats = {"citas": 0, "pacientes": 0, "sin_hora": 0, "estado_desconocido": 0, "segmentados": 0}
    seen_patients = set()
    for _, r in est.iterrows():
        cid_ext = _id(r[c_cita_e])
        if not cid_ext:
            continue
        a = ag.loc[cid_ext] if cid_ext in ag.index else None
        # Profesional
        pname = " ".join(filter(None, [_s(r.get(col(est, "Nombre Profesional"))),
                                         _s(r.get(col(est, "Apellidos Profesional")))])) or "Sin asignar"
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
            cur = conn.execute(
                "insert into paciente(external_id, nombres, apellidos, documento, celular, correo, fecha_nacimiento, "
                "consentimiento_en) values (%s,%s,%s,%s,%s,%s,%s,null) on conflict (negocio_id, external_id) do nothing returning id",
                (pext, _s(r[col(est, "Nombre Paciente")]) or "", _s(r[col(est, "Apellidos Paciente")]) or "",
                 doc, phone, _s(a[col(ag, "E-Mail")]) if a is not None else None, birth))
            if cur.fetchone():
                stats["pacientes"] += 1
            seen_patients.add(pext)
        elif a is not None:  # completa datos que faltaban en citas anteriores del mismo paciente
            phone = normalize_phone(a[col(ag, "Celular")])
            if phone:
                conn.execute("update paciente set celular=%s where external_id=%s and celular is null", (phone, pext))
        pat = conn.execute("select id from paciente where external_id=%s", (pext,)).fetchone()["id"]
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
                (pat, pro, tipo, f"trat:{text_}")).fetchone()["id"]
        # Cita
        estado_o = (_s(r[col(est, "Estado actual")]) or "").lower()
        estado = ESTADOS.get(estado_o)
        if estado is None:
            stats["estado_desconocido"] += 1
            estado = "programada"
        dia = pd.to_datetime(r[col(est, "Fecha Cita")]).date()
        rango, servicio = None, "Otro"
        if a is not None:
            servicio = infer_service(a.get(col(ag, "Comentario")), services)
            h0, h1 = _s(a.get(col(ag, "Hora Inicio"))), _s(a.get(col(ag, "Hora Fin")))
            if h0 and h1:
                t0, t1 = pd.to_datetime(h0).time(), pd.to_datetime(h1).time()
                s, e = _at(dia, t0), _at(dia, t1)
                if e > s:
                    rango = rng(s, int((e - s).total_seconds() // 60))
        if rango is None:
            stats["sin_hora"] += 1
        datos = {c: str(r[c]) for c in yes_no if _s(r[c])}
        params = (pat, pro, services[servicio], tid, dia, estado, datos and json.dumps(datos) or "{}", f"cita:{cid_ext}")
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
        with db.connect(negocio=_negocio()) as conn:
            s = importar(conn)
        print("Importación terminada:", s)
    else:
        raise SystemExit(f"Comando desconocido: {cmd}")


if __name__ == "__main__":
    main()
