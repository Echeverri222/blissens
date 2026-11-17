"""Panel de la auxiliar e indicadores (Streamlit). Usa los mismos servicios de dominio que la aplicación web."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from estudia import (agenda, bandejas, clock, config, db, fmt, followup, indicators,  # noqa: E402
                     messaging, tasks)

st.set_page_config(page_title="Estud-IA · Panel", page_icon="🦷", layout="wide")


def hm(d):
    return fmt.hora(d.astimezone(clock.TZ)) if d else "—"


def fh(d):
    return fmt.fecha_hora(d.astimezone(clock.TZ)) if d else "—"


def run(fn, *a, ok=None, **k):
    """Ejecuta una acción de dominio en su propia transacción y muestra el resultado."""
    try:
        with db.connect() as c:
            fn(c, *a, **k)
        if ok:
            st.toast(ok)
    except Exception as e:  # el panel muestra el motivo en vez de caerse
        st.error(str(e))
    st.rerun()


conn = db.connect()
now = clock.now(conn)
st.sidebar.title("Estud-IA")
st.sidebar.caption("Blissens Odontología")
page = st.sidebar.radio("Sección", ["Hoy", "Bandejas", "Agendar", "Paciente", "Indicadores", "Sistema"])
st.sidebar.caption(f"Hora del sistema: {fmt.fecha_hora(now)}" + (" · modo demo" if config.get(conn, "demo_mode") else ""))

pros = {p["id"]: p["nombre"] for p in conn.execute("select id, nombre from profesional where activo order by id")}
services = {s["id"]: s for s in conn.execute("select * from servicio order by id")}


# ------------------------------------------------------------------ Hoy
if page == "Hoy":
    st.header("Agenda del día")
    c1, c2 = st.columns(2)
    day = c1.date_input("Día", value=now.date())
    pro_sel = c2.selectbox("Profesional", [None, *pros], format_func=lambda i: "Todos" if i is None else pros[i])
    rows = bandejas.today_agenda(conn, day, pro_sel)
    if not rows:
        st.info("No hay citas ese día.")
    for r in rows:
        cols = st.columns([1.2, 2.5, 2.5, 1.5, 1.2, 1.2])
        cols[0].write(hm(r["rango"].lower) if r["rango"] else "sin hora")
        cols[1].write(r["paciente"])
        cols[2].write(f'{r["servicio"]} · {r["profesional"]}')
        cols[3].write(r["estado"].replace("_", " "))
        if r["estado"] in ("programada", "confirmada", "no_confirmada"):
            if cols[4].button("Atendida", key=f"at{r['id']}"):
                run(agenda.mark_outcome, r["id"], "atendida", ok="Marcada como atendida")
            if cols[5].button("No asistió", key=f"na{r['id']}"):
                run(agenda.mark_outcome, r["id"], "no_asistio", ok="Marcada como no asistió")

# ------------------------------------------------------------------ Bandejas
elif page == "Bandejas":
    st.header("Bandejas de trabajo")
    nc, seg, rie, cup, sd, si = (bandejas.no_confirmadas(conn), bandejas.seguimientos(conn), bandejas.en_riesgo(conn),
                                 bandejas.cupos_libres(conn), bandejas.sin_desenlace(conn), bandejas.sin_interpretar(conn))
    cont, baja = bandejas.contactos_pendientes(conn), bandejas.dados_de_baja(conn)
    tabs = st.tabs([f"No confirmadas ({len(nc)})", f"Seguimientos ({len(seg)})", f"Pacientes en riesgo ({len(rie)})",
                    f"Cupos libres ({len(cup)})", f"Citas sin desenlace ({len(sd)})", f"Mensajes sin interpretar ({len(si)})",
                    f"Contactos y bajas ({len(cont) + len(baja)})"])
    with tabs[0]:
        st.caption("Citas próximas sin confirmación, ordenadas por cercanía. Llama primero a las más urgentes.")
        st.dataframe(pd.DataFrame([{"Cita": fh(r["inicio"]), "Paciente": r["paciente"], "Celular": r["celular"],
                                    "Profesional": r["profesional"]} for r in nc]), width="stretch", hide_index=True)
    with tabs[1]:
        st.caption("Casos abiertos y escalados. Registra aquí lo que hayas gestionado por teléfono.")
        for r in seg:
            cols = st.columns([2.5, 2, 1.6, 1.4, 1.4, 1.4])
            cols[0].write(f"**{r['paciente']}** · {r['celular'] or 'sin celular'}")
            cols[1].write(r["tipo"].replace("_", " ") + (" · ESCALADO" if r["escalado"] else ""))
            cols[2].write(f"{r['intentos']} intentos · último: {(r['ultimo'] or 'pendiente').replace('_', ' ')}")
            if cols[3].button("Aceptó", key=f"a{r['id']}"):
                run(followup.register_manual, r["id"], "acepto", "Gestión telefónica", ok="Registrado")
            if cols[4].button("Rechazó", key=f"r{r['id']}"):
                run(followup.register_manual, r["id"], "rechazo", "Gestión telefónica", ok="Registrado")
            if cols[5].button("Sin respuesta", key=f"s{r['id']}"):
                run(followup.register_manual, r["id"], "sin_respuesta", "Llamada sin respuesta", ok="Registrado")
    with tabs[2]:
        st.caption("Tratamientos activos sin cita futura y con más días que el umbral desde la última cita.")
        st.dataframe(pd.DataFrame([{"Paciente": f"{r['nombres']} {r['apellidos']}", "Última cita": r["ultima_cita"],
                                    "Días sin cita": r["dias_sin_cita"],
                                    "Mensaje de recuperación": "enviado" if r["caso_id"] else "aún no"} for r in rie]),
                     width="stretch", hide_index=True)
    with tabs[3]:
        st.dataframe(pd.DataFrame([{"Cupo": fh(r["inicio"]), "Profesional": r["profesional"], "Estado": r["estado"],
                                    "Causa": r["causa"], "Ofertado a": r["ofrecido_a"] or "—"} for r in cup]),
                     width="stretch", hide_index=True)
    with tabs[4]:
        st.caption("Citas pasadas que quedaron sin desenlace. Ciérralas para no dejar huecos en los datos.")
        for r in sd:
            cols = st.columns([2.2, 2.5, 2, 1.3, 1.3])
            cols[0].write(fh(r["inicio"]))
            cols[1].write(r["paciente"])
            cols[2].write(r["profesional"])
            if cols[3].button("Atendida", key=f"sda{r['id']}"):
                run(agenda.mark_outcome, r["id"], "atendida")
            if cols[4].button("No asistió", key=f"sdn{r['id']}"):
                run(agenda.mark_outcome, r["id"], "no_asistio")
    with tabs[5]:
        for r in si:
            cols = st.columns([2, 4, 2, 1.4])
            cols[0].write(r["paciente"])
            cols[1].write(f"“{r['texto']}”")
            cols[2].write(fh(r["momento"]))
            if cols[3].button("Resuelto", key=f"m{r['id']}"):
                run(lambda c, i: c.execute("update mensaje set gestionado=true where id=%s", (i,)), r["id"])
    with tabs[6]:
        st.subheader("Solicitudes de contacto")
        st.caption("Alguien intentó agendar con un documento ya registrado pero otro celular. Llámalo para validar.")
        for r in cont:
            cols = st.columns([2, 2, 3, 1.4])
            cols[0].write(r["documento"])
            cols[1].write(r["celular"])
            cols[2].write(r["nota"])
            if cols[3].button("Gestionada", key=f"c{r['id']}"):
                run(lambda c, i: c.execute("update solicitud_contacto set gestionada=true where id=%s", (i,)), r["id"])
        st.subheader("Citas de pacientes dados de baja")
        st.caption("No reciben mensajes automáticos: gestiona estas citas a mano.")
        st.dataframe(pd.DataFrame([{"Cita": fh(r["inicio"]), "Paciente": r["paciente"], "Celular": r["celular"]}
                                   for r in baja]), width="stretch", hide_index=True)

# ------------------------------------------------------------------ Agendar
elif page == "Agendar":
    st.header("Registrar cita (llamada o WhatsApp)")
    q = st.text_input("Buscar paciente por nombre, documento o celular")
    found = bandejas.find_patients(conn, q) if q else []
    pat = st.selectbox("Paciente", [None, *[p["id"] for p in found]],
                       format_func=lambda i: "— elige —" if i is None else next(
                           f"{p['nombres']} {p['apellidos']} · {p['documento']}" for p in found if p["id"] == i))
    with st.expander("¿Paciente nuevo? Crear"):
        with st.form("nuevo"):
            n, a = st.columns(2)
            nombres, apellidos = n.text_input("Nombres"), a.text_input("Apellidos")
            d, c = st.columns(2)
            doc, cel = d.text_input("Documento"), c.text_input("Celular")
            consent = st.checkbox("El paciente autoriza el tratamiento de sus datos")
            if st.form_submit_button("Crear paciente"):
                from estudia.data import normalize_phone
                if not (nombres and doc and consent):
                    st.error("Faltan nombres, documento o el consentimiento.")
                else:
                    with db.connect() as cx:
                        cx.execute("insert into paciente(nombres, apellidos, documento, celular, consentimiento_en) "
                                   "values (%s,%s,%s,%s,%s)", (nombres, apellidos, doc, normalize_phone(cel), clock.now(cx)))
                    st.success("Paciente creado. Búscalo arriba para agendar.")
    s1, s2 = st.columns(2)
    sid = s1.selectbox("Servicio", list(services), format_func=lambda i: f"{services[i]['nombre']} ({services[i]['duracion_min']} min)")
    pid = s2.selectbox("Profesional", list(pros), format_func=lambda i: pros[i])
    slots = agenda.available_slots(conn, pid, sid, days=21)
    if pat and slots:
        day = st.selectbox("Día", list(slots), format_func=fmt.fecha)
        pick = st.selectbox("Hora", slots[day], format_func=fmt.hora)
        if st.button("Agendar cita", type="primary"):
            try:
                with db.connect() as cx:
                    agenda.book(cx, pat, pid, sid, pick, "auxiliar", "auxiliar")
                st.success("Cita agendada. El paciente recibió la confirmación en el simulador.")
            except agenda.SlotTaken as e:
                st.error(str(e))
    elif not pat:
        st.info("Busca y elige un paciente para ver los espacios.")

# ------------------------------------------------------------------ Paciente
elif page == "Paciente":
    st.header("Ficha del paciente")
    q = st.text_input("Buscar por nombre, documento o celular")
    found = bandejas.find_patients(conn, q) if q else []
    pat = st.selectbox("Paciente", [p["id"] for p in found],
                       format_func=lambda i: next(f"{p['nombres']} {p['apellidos']} · {p['documento']}" for p in found if p["id"] == i)) if found else None
    if pat:
        rec = bandejas.patient_record(conn, pat)
        p = rec["paciente"]
        st.subheader(f"{p['nombres']} {p['apellidos']}")
        st.caption(f"Documento {p['documento']} · Celular {p['celular'] or '—'} · "
                   f"{'Acepta mensajes' if p['acepta_mensajes'] else 'DADO DE BAJA de mensajes automáticos'}")
        t1, t2, t3, t4 = st.tabs(["Citas e historial", "Seguimientos", "Bitácora de mensajes", "Revertir"])
        with t1:
            st.dataframe(pd.DataFrame([{"#": c["id"], "Fecha": fh(c["rango"].lower) if c["rango"] else str(c["dia"]),
                                        "Estado": c["estado"], "Profesional": c["profesional"], "Servicio": c["servicio"],
                                        "Origen": c["origen"]} for c in rec["citas"]]), width="stretch", hide_index=True)
            st.write("**Historial de cambios**")
            st.dataframe(pd.DataFrame([{"Cita": h["cita_id"], "Momento": fh(h["momento"]),
                                        "Cambio": f"{h['estado_anterior'] or '—'} → {h['estado_nuevo']}", "Actor": h["actor"],
                                        "Detalle": h["detalle"]} for h in rec["historial"]]), width="stretch", hide_index=True)
        with t2:
            for c in rec["casos"]:
                st.write(f"**{c['tipo'].replace('_', ' ')}** · {c['estado']}" + (" · escalado" if c["escalado"] else ""))
                st.dataframe(pd.DataFrame(c["intentos"] or []), width="stretch", hide_index=True)
        with t3:
            for m in rec["mensajes"]:
                who = "🏥 Clínica" if m["direccion"] == "saliente" else "👤 Paciente"
                extra = f" · botones: {', '.join(b['title'] for b in m['botones'])}" if m["botones"] else ""
                st.markdown(f"**{who}** · {fh(m['momento'])}  \n{m['texto']}{extra}")
        with t4:
            st.caption("Revertir compensa el cambio con un evento nuevo; nunca borra historial. "
                       "Solo procede si el rango original sigue libre.")
            for h in rec["historial"]:
                if h["estado_anterior"] and not h["revertido"] and h["revierte_id"] is None and \
                        h["estado_nuevo"] in ("cancelada", "reprogramada", "no_asistio", "atendida", "confirmada"):
                    cols = st.columns([1, 3, 3, 1.5])
                    cols[0].write(f"Cita {h['cita_id']}")
                    cols[1].write(f"{h['estado_anterior']} → {h['estado_nuevo']} ({h['actor']})")
                    cols[2].write(fh(h["momento"]))
                    if cols[3].button("Revertir", key=f"rv{h['id']}"):
                        run(agenda.revert, h["id"], ok="Cambio revertido")

# ------------------------------------------------------------------ Indicadores
elif page == "Indicadores":
    st.header("Indicadores")
    last = config.get(conn, "ultimo_diario")
    st.caption(f"Último cierre diario: {last or 'nunca'}")
    if st.button("Ejecutar cierre ahora"):
        with db.connect() as cx:
            first = cx.execute("select min(dia) as d from cita").fetchone()["d"]
            if first:
                indicators.close_range(cx, first, clock.now(cx).date())
        st.toast("Cierre ejecutado")
        st.rerun()
    c1, c2, c3 = st.columns(3)
    first_day = conn.execute("select min(fecha) as d from hecho_diario").fetchone()["d"] or now.date()
    desde = c1.date_input("Desde", value=max(first_day, now.date() - timedelta(days=60)))
    hasta = c2.date_input("Hasta", value=now.date())
    pro_f = c3.selectbox("Profesional", [None, *pros], format_func=lambda i: "Todos" if i is None else pros[i])
    srv_f = st.selectbox("Servicio", [None, *services], format_func=lambda i: "Todos" if i is None else services[i]["nombre"])
    f = {"desde": desde, "hasta": hasta, "profesional_id": pro_f, "servicio_id": srv_f}
    s = indicators.summary(conn, f)
    pct = lambda v: "—" if v is None else f"{v * 100:.1f} %"
    k = st.columns(4)
    k[0].metric("Atención efectiva", pct(s["atencion_efectiva"]), help="Citas atendidas ÷ total de citas del periodo")
    k[1].metric("Inasistencia", pct(s["inasistencia"]), help="No asistió ÷ (atendida + no asistió)")
    k[2].metric("Recuperación de cancelaciones", pct(s["recuperacion"]), help="Cancelaciones que terminaron en cita nueva ÷ total")
    k[3].metric("Confirmación", pct(s["confirmacion"]), help="Confirmadas explícitamente ÷ citas con recordatorio enviado")
    k = st.columns(4)
    k[0].metric("Ocupación", pct(s["ocupacion"]), help="Minutos atendidos ÷ minutos de horario sin bloqueos")
    k[1].metric("Cancelaciones", s["cancelaciones"], f"{s['cancelaciones_tardias']} tardías", delta_color="off")
    k[2].metric("Cupos liberados", s["cupos_liberados"])
    k[3].metric("Cupos ocupados por oferta", s["cupos_ocupados_oferta"],
                f"{s['cupos_ocupados_agendamiento']} por agendamiento · {s['cupos_vacios']} vacíos", delta_color="off")
    tr = indicators.trend(conn, f)
    if tr:
        df = pd.DataFrame(tr)
        df["fecha"] = pd.to_datetime(df["fecha"])
        wk = df.set_index("fecha").resample("W").sum(numeric_only=True).reset_index()
        wk["inasistencia"] = wk["no_asistio"] / (wk["atendidas"] + wk["no_asistio"]).where(lambda x: x > 0)
        st.plotly_chart(px.line(wk, x="fecha", y="inasistencia", markers=True, title="Inasistencia por semana"),
                        width="stretch")
    a, b = st.columns(2)
    for dim, col in (("profesional", a), ("servicio", b)):
        rows = indicators.by_dimension(conn, f, dim)
        if rows:
            col.plotly_chart(px.bar(pd.DataFrame(rows), x="nombre", y="inasistencia", title=f"Inasistencia por {dim}"),
                             width="stretch")
    reasons = indicators.reasons(conn, f)
    a, b = st.columns(2)
    if reasons:
        a.plotly_chart(px.bar(pd.DataFrame(reasons), x="motivo", y=["cancelaciones", "tardias"], barmode="group",
                              title="Motivos de cancelación (y cuántas fueron tardías)"), width="stretch")
    tb = indicators.time_between(conn, f)
    if tb:
        b.plotly_chart(px.bar(pd.DataFrame(tb), x="servicio", y="dias", title="Días promedio entre citas por servicio"),
                       width="stretch")
    tbp = indicators.time_between_patient(conn, f)
    st.caption(f"Tiempo promedio entre citas atendidas consecutivas por paciente: {'—' if tbp is None else f'{tbp:.1f} días'}")

# ------------------------------------------------------------------ Sistema
else:
    st.header("Sistema")
    st.subheader("Tareas fallidas")
    failed = bandejas.tareas_fallidas(conn)
    if failed:
        st.error(f"{len(failed)} tareas fallidas: atiende a mano lo que el sistema no pudo hacer.")
        st.dataframe(pd.DataFrame(failed), width="stretch", hide_index=True)
    else:
        st.success("No hay tareas fallidas.")
    pend = conn.execute("select count(*) as n from tarea_programada where estado='pendiente'").fetchone()["n"]
    st.write(f"Tareas pendientes: **{pend}** · Último cierre diario: **{config.get(conn, 'ultimo_diario') or 'nunca'}**")
    st.subheader("Configuración vigente (solo lectura)")
    st.dataframe(pd.DataFrame([{"Parámetro": k, "Valor": str(v)} for k, v in config.effective(conn).items()]),
                 width="stretch", hide_index=True)

conn.close()
