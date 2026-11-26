"""Rutas de sesión, catálogos, agenda, citas y bloqueos. Delgadas: validan, autorizan y llaman al dominio."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import agenda, clock, config, horario, permisos, usuarios
from . import schemas as sc
from .comun import (
    COOKIE,
    ApiError,
    a_bogota,
    auditar,
    auxiliar,
    fin,
    get_conn,
    inicio,
    solo_json,
    usuario_actual,
    usuario_sin_negocio,
)

router = APIRouter(dependencies=[Depends(solo_json)])
MAX_DIAS = 42


# ----------------------------------------------------------------- sesión

def _negocios(conn, u: dict) -> list[dict]:
    return [{"id": a["negocio_id"], "nombre_corto": a["nombre_corto"], "nombre": a["nombre"],
             "zona_horaria": a["zona_horaria"]} for a in usuarios._accesos_vigentes(conn, u["id"])]


def _sesion(conn, u: dict) -> sc.SesionOut:
    from .. import settings
    negocios = _negocios(conn, u)
    activo = next((n for n in negocios if n["id"] == u["negocio_id"]), None)
    pro = conn.execute("select nombre from profesional where id=%s", (u["profesional_id"],)).fetchone() \
        if u["profesional_id"] else None
    return sc.SesionOut(usuario=u["nombre_usuario"], nombre=u["nombre"], rol=u["rol"], profesional_id=u["profesional_id"],
                        profesional=pro["nombre"] if pro else None, hora_sistema=clock.now(conn),
                        modo_demo=clock.demo_activo(conn) if activo else False, negocio=activo, negocios=negocios,
                        administrador=u["administrador"], debe_cambiar_clave=u["debe_cambiar_clave"],
                        simulador=settings.ENTORNO != "produccion")


@router.get("/marca", tags=["Sesión"], summary="Nombre que muestra la pantalla de ingreso", response_model=sc.MarcaOut,
            description="No pide sesión: es el nombre del negocio por defecto si existe; si no, el del producto.")
def marca(conn=Depends(get_conn)):
    from .. import settings
    r = conn.execute("select nombre from negocio_de_nombre(%s)", (settings.NEGOCIO_POR_DEFECTO,)).fetchone()
    return sc.MarcaOut(nombre=r["nombre"] if r else "Estud-IA")


@router.post("/sesion", tags=["Sesión"], summary="Iniciar sesión", response_model=sc.SesionOut,
             description="Deja la cookie de sesión puesta. Con 5 fallos seguidos el usuario queda bloqueado 15 minutos (429). "
                         "Con acceso a varios negocios la sesión nace sin negocio activo: se elige con `POST /sesion/negocio`.")
def iniciar(datos: sc.Credenciales, response: Response, request: Request, conn=Depends(get_conn)):
    from .. import settings
    token, u = usuarios.iniciar_sesion(conn, datos.usuario, datos.clave)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=settings.BASE_URL.startswith("https"),
                        max_age=config.plataforma("sesion_horas") * 3600, path="/")
    return _sesion(conn, u)


@router.get("/sesion", tags=["Sesión"], summary="Sesión actual y hora del sistema", response_model=sc.SesionOut)
def sesion(conn=Depends(get_conn), u=Depends(usuario_sin_negocio)):
    return _sesion(conn, u)


@router.post("/sesion/negocio", tags=["Sesión"], summary="Cambiar el negocio activo", response_model=sc.SesionOut,
             description="Exige un acceso vigente a ese negocio; si no, 404. No hay que volver a ingresar.")
def elegir_negocio(datos: sc.ElegirNegocio, request: Request, conn=Depends(get_conn), u=Depends(usuario_sin_negocio)):
    nuevo = usuarios.elegir_negocio(conn, request.state.token, u["id"], datos.negocio_id)
    return _sesion(conn, nuevo)


@router.delete("/sesion", tags=["Sesión"], summary="Cerrar sesión", response_model=sc.Ok)
def cerrar(request: Request, response: Response, conn=Depends(get_conn), u=Depends(usuario_sin_negocio)):
    usuarios.cerrar_sesion(conn, request.state.token)
    response.delete_cookie(COOKIE, path="/")
    return sc.Ok()


@router.post("/sesion/clave", tags=["Sesión"], summary="Cambiar la contraseña propia", response_model=sc.Ok,
             description="Cierra las demás sesiones del usuario; la actual se conserva.")
def cambiar_clave(datos: sc.CambioClave, request: Request, conn=Depends(get_conn), u=Depends(usuario_sin_negocio)):
    usuarios.cambiar_clave(conn, u["id"], datos.actual, datos.nueva, request.state.token)
    return sc.Ok()


# ----------------------------------------------------------------- catálogos

@router.get("/profesionales", tags=["Catálogos"], summary="Profesionales activos", response_model=list[sc.ProfesionalOut])
def profesionales(conn=Depends(get_conn), u=Depends(usuario_actual)):
    return conn.execute("select id, nombre, especialidad from profesional where activo order by id").fetchall()


@router.get("/servicios", tags=["Catálogos"], summary="Servicios", response_model=list[sc.ServicioOut])
def servicios(conn=Depends(get_conn), u=Depends(usuario_actual)):
    return conn.execute("select id, nombre, duracion_min, autoagendable from servicio order by id").fetchall()


@router.get("/motivos-cancelacion", tags=["Catálogos"], summary="Motivos de cancelación", response_model=list[sc.MotivoOut])
def motivos(conn=Depends(get_conn), u=Depends(usuario_actual)):
    return conn.execute("select id, etiqueta from motivo_cancelacion order by orden").fetchall()


# ----------------------------------------------------------------- agenda

def _rango(desde: date, hasta: date | None) -> date:
    hasta = hasta or desde
    if hasta < desde:
        raise ApiError(422, "rango_invalido", "La fecha final no puede ser anterior a la inicial.")
    if (hasta - desde).days + 1 > MAX_DIAS:
        raise ApiError(422, "rango_invalido", f"El rango no puede pasar de {MAX_DIAS} días.")
    return hasta


def _existe_profesional(conn, profesional_id: int) -> None:
    if not conn.execute("select 1 from profesional where id=%s", (profesional_id,)).fetchone():
        raise permisos.NoExiste("No existe ese profesional")


def _cita_agenda(r: dict, u: dict, ahora) -> dict:
    return {**r, "inicio": inicio(r), "fin": fin(r), "acciones": permisos.acciones_cita(u, r["estado"], inicio(r), ahora)}


def _bloqueo(r: dict) -> dict:
    return {"id": r["id"], "profesional_id": r["profesional_id"], "inicio": r["rango"].lower, "fin": r["rango"].upper,
            "motivo": r["motivo"], "creado_por": r.get("creado_por_nombre")}


@router.get("/agenda", tags=["Agenda"], summary="Agenda por rango de fechas", response_model=sc.AgendaOut,
            description="Hasta 42 días. Devuelve citas (menos las reprogramadas), bloqueos, franjas del horario y cupos "
                        "liberados abiertos. El especialista siempre recibe la suya: el filtro de profesional se ignora.")
def agenda_rango(desde: date, hasta: date | None = None, profesional_id: int | None = None,
                 conn=Depends(get_conn), u=Depends(usuario_actual)):
    hasta = _rango(desde, hasta)
    pro = permisos.alcance_profesional(u, profesional_id)
    if pro is not None:
        _existe_profesional(conn, pro)
    r = agenda.range_agenda(conn, desde, hasta, pro)
    ahora = clock.now(conn)
    return sc.AgendaOut(
        desde=desde, hasta=hasta, profesional_id=pro,
        citas=[_cita_agenda(c, u, ahora) for c in r["citas"]],
        citas_sin_hora=[_cita_agenda(c, u, ahora) for c in r["citas_sin_hora"]],
        bloqueos=[_bloqueo(b) for b in r["bloqueos"]], franjas=r["franjas"],
        cupos_liberados=[{**c, "inicio": c["rango"].lower, "fin": c["rango"].upper} for c in r["cupos"]])


@router.get("/profesionales/{profesional_id}/horario", tags=["Agenda"], summary="Horario semanal de un profesional",
            response_model=sc.HorarioOut)
def horario_semanal(profesional_id: int, conn=Depends(get_conn), u=Depends(usuario_actual)):
    permisos.exigir_profesional(u, profesional_id)
    _existe_profesional(conn, profesional_id)
    return sc.HorarioOut(profesional_id=profesional_id, franjas=horario.schedule(conn, profesional_id))


# ----------------------------------------------------------------- citas

@router.get("/citas/{cita_id}", tags=["Citas"], summary="Detalle de una cita con su historial", response_model=sc.CitaDetalle,
            dependencies=[auditar("ver_cita")])
def detalle_cita(cita_id: int, conn=Depends(get_conn), u=Depends(usuario_actual)):
    permisos.cita_visible(conn, u, cita_id)
    c = conn.execute(
        "select c.id, c.estado, c.dia, c.rango, c.profesional_id, pr.nombre as profesional, c.servicio_id, "
        "s.nombre as servicio, p.id as pid, p.nombres || ' ' || p.apellidos as pnombre, p.celular from cita c "
        "join profesional pr on pr.id=c.profesional_id join servicio s on s.id=c.servicio_id "
        "join paciente p on p.id=c.paciente_id where c.id=%s", (cita_id,)).fetchone()
    hist = conn.execute(
        "select h.id, h.estado_anterior, h.estado_nuevo, h.actor, h.detalle, h.momento, h.revierte_id, u.nombre as usuario, "
        "exists(select 1 from historial_estado r where r.revierte_id=h.id) as revertido from historial_estado h "
        "left join usuario u on u.id=h.usuario_id where h.cita_id=%s order by h.momento, h.id", (cita_id,)).fetchall()
    return sc.CitaDetalle(
        **{k: c[k] for k in ("id", "estado", "dia", "profesional_id", "profesional", "servicio_id", "servicio")},
        inicio=inicio(c), fin=fin(c), paciente={"id": c["pid"], "nombre": c["pnombre"], "celular": c["celular"]},
        acciones=permisos.acciones_cita(u, c["estado"], inicio(c), clock.now(conn)),
        historial=[{**h, "reversible": permisos.puede_revertir(u, h, c["estado"])} for h in hist])


@router.post("/citas", tags=["Citas"], summary="Agendar una cita (auxiliar)", response_model=sc.CitaCreada, status_code=201)
def agendar(datos: sc.NuevaCita, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not conn.execute("select 1 from paciente where id=%s", (datos.paciente_id,)).fetchone():
        raise permisos.NoExiste("No existe ese paciente")
    if not conn.execute("select 1 from profesional where id=%s and activo", (datos.profesional_id,)).fetchone():
        raise permisos.NoExiste("No existe ese profesional")
    if not conn.execute("select 1 from servicio where id=%s", (datos.servicio_id,)).fetchone():
        raise permisos.NoExiste("No existe ese servicio")
    cid = agenda.book(conn, datos.paciente_id, datos.profesional_id, datos.servicio_id, a_bogota(datos.inicio),
                      "auxiliar", "auxiliar", user_id=u["id"])
    return sc.CitaCreada(cita_id=cid)


@router.post("/citas/{cita_id}/confirmar", tags=["Citas"], summary="Registrar la confirmación dada por teléfono (auxiliar)",
             response_model=sc.Ok,
             description="Pasa la cita a confirmada con el actor auxiliar. No cancela nada ni envía mensajes. Solo antes de la hora "
                         "de inicio y desde programada o sin confirmar (409 si no). Se deshace con la reversión del historial.")
def confirmar(cita_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    permisos.cita_visible(conn, u, cita_id)
    agenda.confirm_by_phone(conn, cita_id, user_id=u["id"])
    return sc.Ok()


@router.post("/citas/{cita_id}/cancelar", tags=["Citas"], summary="Cancelar una cita con su motivo (auxiliar)",
             response_model=sc.Ok, description="Mismo proceso que si cancelara el paciente: libera el cupo y abre el seguimiento.")
def cancelar(cita_id: int, datos: sc.Cancelacion, conn=Depends(get_conn), u=Depends(auxiliar)):
    permisos.cita_visible(conn, u, cita_id)
    if not conn.execute("select 1 from motivo_cancelacion where id=%s", (datos.motivo_id,)).fetchone():
        raise permisos.NoExiste("No existe ese motivo")
    agenda.cancel(conn, cita_id, "auxiliar", "panel", reason_id=datos.motivo_id, text=datos.texto, user_id=u["id"])
    return sc.Ok()


@router.post("/citas/{cita_id}/cambiar-fecha", tags=["Citas"], summary="Cambiar la fecha de una cita (auxiliar)",
             response_model=sc.CitaCreada, description="La cita se cierra como reprogramada y se crea una nueva enlazada.")
def cambiar_fecha(cita_id: int, datos: sc.CambioFecha, conn=Depends(get_conn), u=Depends(auxiliar)):
    permisos.cita_visible(conn, u, cita_id)
    nueva = agenda.reschedule(conn, cita_id, a_bogota(datos.inicio), "auxiliar", origin="auxiliar", user_id=u["id"])
    return sc.CitaCreada(cita_id=nueva)


@router.post("/citas/{cita_id}/desenlace", tags=["Citas"], summary="Registrar el desenlace de una cita", response_model=sc.Ok,
             description="Solo desde la hora de inicio. *No asistió* abre el seguimiento, lo marque quien lo marque.")
def desenlace(cita_id: int, datos: sc.Desenlace, conn=Depends(get_conn), u=Depends(usuario_actual)):
    permisos.cita_visible(conn, u, cita_id)
    agenda.mark_outcome(conn, cita_id, datos.desenlace, actor=u["rol"], user_id=u["id"])
    return sc.Ok()


@router.get("/espacios", tags=["Citas"], summary="Espacios disponibles (auxiliar)", response_model=sc.EspaciosOut)
def espacios(profesional_id: int, servicio_id: int, dias: int = Query(21, ge=1, le=90), conn=Depends(get_conn),
             u=Depends(auxiliar)):
    _existe_profesional(conn, profesional_id)
    if not conn.execute("select 1 from servicio where id=%s", (servicio_id,)).fetchone():
        raise permisos.NoExiste("No existe ese servicio")
    por_dia = agenda.available_slots(conn, profesional_id, servicio_id, days=dias)
    return sc.EspaciosOut(profesional_id=profesional_id, servicio_id=servicio_id,
                          dias=[{"fecha": d, "horas": h} for d, h in por_dia.items()])


@router.post("/historial/{historial_id}/revertir", tags=["Reversiones"], summary="Revertir un movimiento del historial",
             response_model=sc.Reversion,
             description="Compensa con un evento nuevo; nunca borra historial. La auxiliar revierte cualquier cambio "
                         "reversible; el especialista solo un desenlace de una cita suya.")
def revertir(historial_id: int, conn=Depends(get_conn), u=Depends(usuario_actual)):
    h = conn.execute("select cita_id, estado_nuevo from historial_estado where id=%s", (historial_id,)).fetchone()
    if h is None:
        raise permisos.NoExiste("No existe ese movimiento")
    permisos.cita_visible(conn, u, h["cita_id"])
    if not permisos.es_auxiliar(u) and h["estado_nuevo"] not in ("atendida", "no_asistio"):
        raise permisos.SinPermiso("El especialista solo puede revertir un desenlace")
    nuevo = agenda.revert(conn, historial_id, actor=u["rol"], user_id=u["id"])
    return sc.Reversion(historial_id=nuevo)


# ----------------------------------------------------------------- bloqueos

@router.get("/bloqueos", tags=["Bloqueos"], summary="Bloqueos por profesional y rango", response_model=list[sc.BloqueoOut])
def listar_bloqueos(desde: date, hasta: date | None = None, profesional_id: int | None = None,
                    conn=Depends(get_conn), u=Depends(usuario_actual)):
    hasta = _rango(desde, hasta)
    return [_bloqueo(b) for b in horario.list_blocks(conn, permisos.alcance_profesional(u, profesional_id), desde, hasta)]


@router.post("/bloqueos", tags=["Bloqueos"], summary="Crear un bloqueo", response_model=sc.BloqueoOut, status_code=201,
             description="Si el rango se cruza con citas vivas se rechaza (409) y se listan; el sistema nunca cancela citas.")
def crear_bloqueo(datos: sc.NuevoBloqueo, conn=Depends(get_conn), u=Depends(usuario_actual)):
    pro = datos.profesional_id
    if permisos.es_auxiliar(u):
        if pro is None:
            raise ApiError(422, "profesional_requerido", "Indica de qué profesional es el bloqueo.")
    elif pro is None:
        pro = u["profesional_id"]
    permisos.exigir_profesional(u, pro)
    _existe_profesional(conn, pro)
    bid = horario.create_block(conn, pro, a_bogota(datos.inicio), a_bogota(datos.fin), datos.motivo.strip(), u["id"])
    return _bloqueo(horario.get_block(conn, bid))


@router.delete("/bloqueos/{bloqueo_id}", tags=["Bloqueos"], summary="Eliminar un bloqueo que aún no terminó",
               response_model=sc.Ok)
def eliminar_bloqueo(bloqueo_id: int, conn=Depends(get_conn), u=Depends(usuario_actual)):
    b = horario.get_block(conn, bloqueo_id)
    if b is None:
        raise permisos.NoExiste("No existe ese bloqueo")
    permisos.exigir_profesional(u, b["profesional_id"])
    horario.delete_block(conn, bloqueo_id)
    return sc.Ok()
