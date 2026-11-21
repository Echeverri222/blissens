"""Rutas públicas para el portal del paciente (mobile-first): identificación, mis citas,
selector interactivo de cupos, agendamiento, reprogramación y cancelación con motivos.
"""
from datetime import date, datetime
import re

from fastapi import APIRouter, Depends, Query

from .. import agenda, clock, config, db, links, settings
from .. import correo as correo_mod
from .. import data
from ..lifecycle import ALIVE
from . import schemas as sc
from .comun import ApiError, solo_json

router = APIRouter(prefix="/publico", tags=["Público"], dependencies=[Depends(solo_json)])


def _conectar():
    return db.connect(negocio=None)


def _resolver_negocio(conn, nombre_corto: str | None = None):
    corto = nombre_corto or settings.NEGOCIO_POR_DEFECTO
    negocio = conn.execute("select * from negocio_de_nombre(%s)", (corto,)).fetchone()
    if negocio is None or not negocio["activo"]:
        raise ApiError(404, "negocio_invalido", "La clínica indicada no existe o no está activa.")
    db.fijar(conn, negocio["id"])
    return negocio


def _paciente_de_token(conn, token: str) -> tuple[dict, dict]:
    """Valida la firma y vigencia del token y fija el contexto del negocio."""
    nid = links.negocio_del_token(token)
    if nid is None:
        raise ApiError(404, "enlace_invalido", "Este enlace no es válido o ya venció. Pide uno nuevo a la clínica.")
    db.fijar(conn, nid)
    vigencia = config.get(conn, "vigencia_enlace_dias")
    pid = links.read_token(token, vigencia)
    if pid is None:
        raise ApiError(404, "enlace_invalido", "Este enlace no es válido o ya venció. Pide uno nuevo a la clínica.")
    p = conn.execute("select * from paciente where id=%s", (pid,)).fetchone()
    if p is None:
        raise ApiError(404, "enlace_invalido", "Este enlace no es válido o ya venció.")
    negocio = conn.execute("select * from negocio where id=%s", (nid,)).fetchone()
    return p, negocio


def _citas_activas(conn, paciente_id: int):
    now = clock.now(conn)
    return conn.execute(
        "select c.*, p.nombre as profesional, s.nombre as servicio from cita c "
        "join profesional p on p.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "where c.paciente_id=%s and c.estado = any(%s) and (c.rango is null or upper(c.rango) > %s) order by c.dia, c.rango",
        (paciente_id, list(ALIVE), now)).fetchall()


def _catalogo_espacios(conn, servicio_id: int | None = None, profesional_id: int | None = 0):
    services = conn.execute("select * from servicio where autoagendable order by id").fetchall()
    pros = conn.execute("select * from profesional where activo order by id").fetchall()
    if not services:
        return sc.CatalogoEspaciosPublicoOut(sid=0, pid=0, servicios=[], profesionales=[], dias=[])
    sid = servicio_id if servicio_id and any(s["id"] == servicio_id for s in services) else services[0]["id"]
    pid = profesional_id or 0
    slots = agenda.available_slots(conn, pid, sid) if pid else agenda.any_slots(conn, sid)
    dias = [
        sc.EspaciosDia(fecha=d, horas=horas)
        for d, horas in slots.items()
    ]
    return sc.CatalogoEspaciosPublicoOut(
        sid=sid,
        pid=pid,
        servicios=[sc.ServicioOut(id=s["id"], nombre=s["nombre"], duracion_min=s["duracion_min"], autoagendable=s["autoagendable"]) for s in services],
        profesionales=[sc.ProfesionalOut(id=pr["id"], nombre=pr["nombre"], especialidad=pr["especialidad"]) for pr in pros],
        dias=dias,
    )


# ----------------------------------------------------------------- Endpoints Públicos

@router.post("/identificar", response_model=sc.IdentificarOut, summary="Identificar o registrar paciente")
def identificar(datos: sc.IdentificarIn):
    conn = _conectar()
    try:
        negocio = _resolver_negocio(conn, datos.negocio)
        doc = re.sub(r"\D", "", datos.documento)
        phone = data.normalize_phone(datos.celular)
        if not doc or not phone:
            raise ApiError(422, "datos_invalidos", "Revisa tu documento y tu celular (10 dígitos, empieza por 3).")
        
        p = conn.execute("select * from paciente where documento=%s", (doc,)).fetchone()
        if p and p["celular"] == phone:
            token = links.make_token(p["id"], conn=conn)
            return sc.IdentificarOut(
                estado="autenticado",
                token=token,
                paciente=sc.PacientePublico(
                    id=p["id"], nombres=p["nombres"], apellidos=p["apellidos"],
                    documento=p["documento"], celular=p["celular"], correo=p["correo"],
                    acepta_mensajes=p["acepta_mensajes"]
                ),
            )
        if p:
            # Documento existente con otro celular: prevención de filtración de datos sensibles
            conn.execute(
                "insert into solicitud_contacto(documento, celular, nota, momento) values (%s,%s,%s,%s)",
                (doc, phone, "Documento ya registrado con otro celular", clock.now(conn))
            )
            conn.commit()
            return sc.IdentificarOut(
                estado="contacto_pendiente",
                mensaje="No pudimos continuar de forma automática. La clínica se pondrá en contacto contigo muy pronto para ayudarte a agendar."
            )
        
        # Paciente no registrado previamente
        if not datos.nombres or not datos.nombres.strip():
            return sc.IdentificarOut(estado="requiere_registro")
        
        if not datos.consentimiento:
            raise ApiError(422, "requiere_consentimiento", "Para registrarte necesitamos tu autorización para tratar tus datos.")
        
        now = clock.now(conn)
        pid = conn.execute(
            "insert into paciente(nombres, apellidos, documento, celular, consentimiento_en, consentimiento_version, creado_en) "
            "values (%s,%s,%s,%s,%s,%s,%s) returning id",
            (datos.nombres.strip(), (datos.apellidos or "").strip(), doc, phone, now,
             config.get(conn, "consentimiento_version"), now)
        ).fetchone()["id"]
        conn.commit()
        
        token = links.make_token(pid, conn=conn)
        return sc.IdentificarOut(
            estado="registrado",
            token=token,
            paciente=sc.PacientePublico(
                id=pid, nombres=datos.nombres.strip(), apellidos=(datos.apellidos or "").strip(),
                documento=doc, celular=phone, correo=None, acepta_mensajes=True
            ),
        )
    finally:
        conn.close()


@router.get("/citas", response_model=sc.MisCitasPublicoOut, summary="Consultar citas activas del paciente")
def mis_citas(token: str = Query(..., description="Token firmado del paciente")):
    conn = _conectar()
    try:
        p, negocio = _paciente_de_token(conn, token)
        citas_db = _citas_activas(conn, p["id"])
        citas = []
        for c in citas_db:
            inicio = c["rango"].lower if c["rango"] else None
            fin = c["rango"].upper if c["rango"] else None
            citas.append(sc.CitaPacientePublico(
                id=c["id"],
                estado=c["estado"],
                dia=c["dia"],
                inicio=inicio,
                fin=fin,
                profesional=c["profesional"],
                servicio=c["servicio"]
            ))
        termino = config.get(conn, "termino_negocio")
        return sc.MisCitasPublicoOut(
            paciente=sc.PacientePublico(
                id=p["id"], nombres=p["nombres"], apellidos=p["apellidos"],
                documento=p["documento"], celular=p["celular"], correo=p["correo"],
                acepta_mensajes=p["acepta_mensajes"]
            ),
            citas=citas,
            termino_negocio=termino,
            nombre_negocio=negocio["nombre"],
            consentimiento_texto=config.get(conn, "texto_consentimiento").format(nombre=negocio["nombre"])
        )
    finally:
        conn.close()


@router.get("/espacios", response_model=sc.CatalogoEspaciosPublicoOut, summary="Consultar espacios disponibles")
def espacios(
    token: str = Query(..., description="Token firmado del paciente"),
    servicio_id: int | None = Query(None, description="ID del servicio"),
    profesional_id: int = Query(0, description="ID del profesional o 0 para cualquiera")
):
    conn = _conectar()
    try:
        _paciente_de_token(conn, token)
        return _catalogo_espacios(conn, servicio_id, profesional_id)
    finally:
        conn.close()


@router.post("/agendar", response_model=sc.AgendarPublicoOut, summary="Agendar nueva cita")
def agendar(datos: sc.AgendarPublicoIn):
    conn = _conectar()
    try:
        p, _ = _paciente_de_token(conn, datos.token)
        try:
            cid = agenda.book(
                conn, p["id"], datos.profesional_id or None, datos.servicio_id,
                datos.inicio, "paciente", "paciente"
            )
            conn.commit()
            return sc.AgendarPublicoOut(
                ok=True,
                cita_id=cid,
                inicio=datos.inicio,
                mensaje="Tu cita quedó agendada. Te enviamos la confirmación por WhatsApp."
            )
        except agenda.SlotTaken:
            raise ApiError(409, "espacio_ocupado", "Ese espacio acaba de ocuparse. Por favor elige otro horario.")
    finally:
        conn.close()


@router.post("/cambiar/{cita_id}", response_model=sc.CambiarPublicoOut, summary="Reprogramar una cita vigente")
def cambiar(cita_id: int, datos: sc.CambiarPublicoIn):
    conn = _conectar()
    try:
        p, _ = _paciente_de_token(conn, datos.token)
        c = conn.execute(
            "select * from cita where id=%s and paciente_id=%s and estado = any(%s)",
            (cita_id, p["id"], list(ALIVE))
        ).fetchone()
        if c is None:
            raise ApiError(404, "cita_no_vigente", "Esa cita ya no está vigente o no existe.")
        try:
            nueva_id = agenda.reschedule(conn, cita_id, datos.inicio, "paciente")
            conn.commit()
            return sc.CambiarPublicoOut(ok=True, cita_id=nueva_id, mensaje="Fecha cambiada exitosamente")
        except agenda.SlotTaken:
            raise ApiError(409, "espacio_ocupado", "Ese espacio acaba de ocuparse. Por favor elige otro horario.")
    finally:
        conn.close()


@router.get("/motivos-cancelacion", response_model=list[sc.MotivoOut], summary="Listar motivos de cancelación")
def motivos_cancelacion(token: str = Query(...)):
    conn = _conectar()
    try:
        _paciente_de_token(conn, token)
        rows = conn.execute("select * from motivo_cancelacion order by orden").fetchall()
        return [sc.MotivoOut(id=r["id"], etiqueta=r["etiqueta"]) for r in rows]
    finally:
        conn.close()


@router.post("/cancelar/{cita_id}", response_model=sc.CancelarPublicoOut, summary="Cancelar cita y ofrecer retención")
def cancelar(cita_id: int, datos: sc.CancelarPublicoIn):
    conn = _conectar()
    try:
        p, _ = _paciente_de_token(conn, datos.token)
        c = conn.execute(
            "select * from cita where id=%s and paciente_id=%s and estado = any(%s)",
            (cita_id, p["id"], list(ALIVE))
        ).fetchone()
        if c is None:
            raise ApiError(404, "cita_no_vigente", "Esa cita ya no está vigente.")
        
        agenda.cancel(conn, cita_id, "paciente", "enlace", reason_id=datos.motivo_id)
        conn.commit()

        # Ofrecemos espacios alternativos de inmediato para favorecer la retención
        alternativos = _catalogo_espacios(conn, c["servicio_id"], c["profesional_id"])
        return sc.CancelarPublicoOut(
            ok=True,
            cita_id=cita_id,
            mensaje="Tu cita quedó cancelada.",
            espacios_alternativos=alternativos
        )
    finally:
        conn.close()


@router.post("/correo/baja", response_model=sc.Ok, summary="Desuscribirse de correos")
def baja_correo(datos: sc.BajaCorreoIn):
    conn = _conectar()
    try:
        v = correo_mod.leer_token_baja(datos.token)
        if v is None:
            raise ApiError(404, "enlace_invalido", "Este enlace no es válido. Pide ayuda a la clínica.")
        db.fijar(conn, v[0])
        correo_mod.dar_de_baja(conn, v[1])
        conn.commit()
        return sc.Ok()
    finally:
        conn.close()
