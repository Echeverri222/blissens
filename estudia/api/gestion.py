"""Rutas de la auxiliar: pacientes, bandejas, indicadores y sistema. Todas exigen el rol auxiliar."""
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from .. import (
    alertas,
    bandejas,
    clock,
    config,
    correo,
    familia,
    followup,
    indicators,
    lifecycle,
    pacientes,
    permisos,
    planes,
    solicitudes,
)
from . import schemas as sc
from .comun import ApiError, auditar, auxiliar, get_conn, inicio, solo_json

router = APIRouter(dependencies=[Depends(solo_json)])


# ----------------------------------------------------------------- pacientes

@router.get("/pacientes", tags=["Pacientes"], summary="Buscar pacientes por nombre, documento o celular",
            description="Con `segmento` se queda con los internacionales o los deportistas de alto nivel (si se repite, con "
                        "los que tengan cualquiera de las marcas); sin `q`, los lista a todos. Devuelve como mucho "
                        f"{bandejas.TOPE_BUSQUEDA}, en orden de apellidos.",
            response_model=list[sc.PacienteResumen], dependencies=[auditar("buscar_paciente")])
def buscar(q: str | None = Query(None, min_length=1), segmento: list[sc.Segmento] = Query([]),
           fallecidos: bool = Query(False, description="Incluye a los marcados como fallecidos (por defecto no salen)."),
           semaforo: sc.ColorSemaforo | None = Query(None, description="Solo los de ese color (R5)."),
           conn=Depends(get_conn), u=Depends(auxiliar)):
    if not q and not segmento:
        raise ApiError(422, "falta_filtro", "Escribe un nombre, documento o celular, o elige un segmento")
    return bandejas.find_patients(conn, q or "", tuple(segmento), fallecidos, semaforo)


@router.post("/pacientes", tags=["Pacientes"], summary="Crear un paciente (con consentimiento)",
             response_model=sc.PacienteCreado, status_code=201)
def crear(datos: sc.NuevoPaciente, conn=Depends(get_conn), u=Depends(auxiliar)):
    return sc.PacienteCreado(paciente_id=pacientes.create(
        conn, datos.nombres, datos.apellidos, datos.documento, datos.celular, datos.consentimiento))


@router.put("/pacientes/{paciente_id}/identificacion", tags=["Pacientes"], response_model=sc.PacienteIdentificado,
            summary="Ponerle el documento a un prospecto: pasa a paciente",
            description="Un prospecto es quien escribió desde el sitio web y aún no tiene documento. Con el documento (y el "
                        "celular, si le falta) pasa a ser paciente y ya se le pueden agendar citas. 409 si otro paciente "
                        "ya tiene ese documento.",
            dependencies=[auditar("editar_documento")])
def identificar_paciente(paciente_id: int, datos: sc.Identificacion, conn=Depends(get_conn), u=Depends(auxiliar)):
    r = pacientes.completar_documento(conn, paciente_id, datos.documento, datos.celular)
    if r is None:
        raise permisos.NoExiste("No existe ese paciente")
    return r


@router.put("/pacientes/{paciente_id}/correo", tags=["Pacientes"], response_model=sc.ConsentimientoCorreo,
            summary="Registrar el correo del paciente y si autoriza recibir correos",
            dependencies=[auditar("editar_correo")])
def correo_paciente(paciente_id: int, datos: sc.ConsentimientoCorreo, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not conn.execute("select 1 from paciente where id=%s", (paciente_id,)).fetchone():
        raise permisos.NoExiste("No existe ese paciente")
    correo.registrar_consentimiento(conn, paciente_id, datos.correo, datos.acepta)
    p = conn.execute("select correo, acepta_correo from paciente where id=%s", (paciente_id,)).fetchone()
    return sc.ConsentimientoCorreo(correo=p["correo"], acepta=p["acepta_correo"])


@router.put("/pacientes/{paciente_id}/celular", tags=["Pacientes"], response_model=sc.CelularOut,
            summary="Corregir el celular del paciente",
            description="Se valida y normaliza (celular colombiano o número internacional con `+`); 422 «Celular no válido» si no "
                        "sirve. El celular queda sin verificar y lo hereda su hogar si lo compartía.",
            dependencies=[auditar("editar_celular")])
def cambiar_celular(paciente_id: int, datos: sc.NuevoCelular, conn=Depends(get_conn), u=Depends(auxiliar)):
    r = pacientes.cambiar_celular(conn, paciente_id, datos.celular)
    if r is None:
        raise permisos.NoExiste("No existe ese paciente")
    return r


@router.post("/pacientes/{paciente_id}/celular/en-chat", tags=["Pacientes"], response_model=sc.CelularOut,
             summary="Marcar el celular como válido: ya está en un chat de WhatsApp",
             dependencies=[auditar("celular_en_chat")])
def celular_en_chat(paciente_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    r = pacientes.marcar_celular(conn, paciente_id, "valido")
    if r is None:
        raise permisos.NoExiste("No existe ese paciente")
    return r


@router.put("/pacientes/{paciente_id}/segmentos", tags=["Pacientes"], response_model=sc.SegmentosOut,
            summary="Marcar o desmarcar al paciente como internacional o deportista de alto nivel",
            description="Los pacientes de alto valor salen primero en las bandejas de seguimientos y de pacientes en riesgo. "
                        "Lo que marca la recepción manda: la importación del Excel ya no lo cambia.",
            dependencies=[auditar("editar_segmentos")])
def segmentos_paciente(paciente_id: int, datos: sc.Segmentos, conn=Depends(get_conn), u=Depends(auxiliar)):
    r = pacientes.marcar_segmentos(conn, paciente_id, datos.internacional, datos.deportista, u["id"])
    if r is None:
        raise permisos.NoExiste("No existe ese paciente")
    return r


@router.put("/pacientes/{paciente_id}/no-contactar", tags=["Pacientes"], response_model=sc.NoContactarOut,
            summary="Marcar al paciente como «No contactar»",
            description="La clínica deja de escribirle y de llamarle por iniciativa propia (cobro, queja, fallecido u otro motivo): "
                        "no salen mensajes automáticos, se cierran como anulados sus seguimientos abiertos y desaparece de "
                        "las listas de trabajo. Las respuestas directas a lo que la persona haga sí salen, salvo con `fallecido`, "
                        "que lo bloquea todo y lo oculta de las búsquedas para agendar.",
            dependencies=[auditar("marcar_no_contactar")])
def marcar_no_contactar(paciente_id: int, datos: sc.NoContactar, conn=Depends(get_conn), u=Depends(auxiliar)):
    r = pacientes.no_contactar(conn, paciente_id, datos.motivo, datos.nota, u["id"])
    if r is None:
        raise permisos.NoExiste("No existe ese paciente")
    return r


@router.delete("/pacientes/{paciente_id}/no-contactar", tags=["Pacientes"], response_model=sc.NoContactarOut,
               summary="Quitar la marca «No contactar»", dependencies=[auditar("quitar_no_contactar")])
def quitar_no_contactar(paciente_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    r = pacientes.quitar_no_contactar(conn, paciente_id)
    if r is None:
        raise permisos.NoExiste("No existe ese paciente")
    return r


def _plan_o_error(r):
    if r is None:
        raise permisos.NoExiste("No existe ese tratamiento")
    return r


@router.put("/pacientes/{paciente_id}/tratamientos/{tratamiento_id}/plan-entregado", tags=["Pacientes"],
            response_model=sc.PlanOut, summary="Registrar que se entregó el plan de tratamiento",
            description="Fecha (por defecto hoy) y valor opcional, que solo ve el panel. Abre el seguimiento de acompañamiento "
                        "(3 y 7 días, sin montos). 422 si es un prospecto.",
            dependencies=[auditar("plan_entregado")])
def plan_entregado(paciente_id: int, tratamiento_id: int, datos: sc.PlanEntregado, conn=Depends(get_conn),
                   u=Depends(auxiliar)):
    try:
        r = _plan_o_error(planes.plan_entregado(conn, paciente_id, tratamiento_id, datos.fecha, datos.valor_plan))
    except planes.PlanInvalido as e:
        raise ApiError(422, "plan_invalido", str(e)) from None
    return sc.PlanOut(**{k: r[k] for k in ("tratamiento_id", "plan_entregado_en", "caso_id")})


@router.put("/pacientes/{paciente_id}/tratamientos/{tratamiento_id}/abono", tags=["Pacientes"],
            response_model=sc.PlanOut, summary="Registrar un abono al plan (solo la fecha)",
            dependencies=[auditar("registrar_abono")])
def registrar_abono(paciente_id: int, tratamiento_id: int, datos: sc.Abono, conn=Depends(get_conn),
                    u=Depends(auxiliar)):
    try:
        r = _plan_o_error(planes.registrar_abono(conn, paciente_id, tratamiento_id, datos.fecha))
    except planes.PlanInvalido as e:
        raise ApiError(422, "plan_invalido", str(e)) from None
    return sc.PlanOut(**{k: r[k] for k in ("tratamiento_id", "ultimo_abono_en", "caso_id")})


@router.get("/pacientes/{paciente_id}", tags=["Pacientes"], summary="Ficha completa del paciente",
            response_model=sc.FichaCompleta, dependencies=[auditar("ver_ficha")])
def ficha(paciente_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not conn.execute("select 1 from paciente where id=%s", (paciente_id,)).fetchone():
        raise permisos.NoExiste("No existe ese paciente")
    r = bandejas.patient_record(conn, paciente_id)
    estados = {c["id"]: c["estado"] for c in r["citas"]}
    return sc.FichaCompleta(
        paciente={**r["paciente"], "semaforo": pacientes.semaforo(conn, [paciente_id])[paciente_id]}, familia=familia.resumen(conn, paciente_id),
        tratamientos=planes.tratamientos_de(conn, paciente_id),
        citas=[{**c, "inicio": inicio(c)} for c in r["citas"]],
        historial=[{**h, "reversible": permisos.puede_revertir(u, h, estados[h["cita_id"]])} for h in r["historial"]],
        casos=[{**c, "intentos": c["intentos"] or []} for c in r["casos"]], mensajes=r["mensajes"])


# ----------------------------------------------------------------- bandejas

def _con_color(conn, filas: list[dict]) -> list[dict]:
    """A cada fila de una lista de llamadas, el semáforo de su paciente (R5)."""
    colores = pacientes.semaforo(conn, [f["paciente_id"] for f in filas])
    return [{**f, "semaforo": colores.get(f["paciente_id"])} for f in filas]


def _nombre(r: dict) -> dict:
    return {**r, "paciente": f"{r['nombres']} {r['apellidos']}".strip()}


@router.get("/bandejas", tags=["Bandejas"], summary="Conteo de todas las bandejas", response_model=sc.ConteoBandejas)
def conteo(conn=Depends(get_conn), u=Depends(auxiliar)):
    return sc.ConteoBandejas(
        no_confirmadas=len(bandejas.no_confirmadas(conn)), seguimientos=len(bandejas.seguimientos(conn)),
        en_riesgo=len(bandejas.en_riesgo(conn)), cupos_libres=len(bandejas.cupos_libres(conn)),
        sin_desenlace=len(bandejas.sin_desenlace(conn)), sin_interpretar=len(bandejas.sin_interpretar(conn)),
        contactos=len(bandejas.contactos_pendientes(conn)), dados_de_baja=len(bandejas.dados_de_baja(conn)),
        celulares_por_revisar=len(bandejas.celulares_por_revisar(conn)), planes=len(planes.sin_siguiente_paso(conn)))


@router.get("/resumen-dia", tags=["Bandejas"], summary="Contadores de la franja superior de la agenda",
            response_model=sc.ResumenDiaOut)
def resumen_dia(conn=Depends(get_conn), u=Depends(auxiliar)):
    return bandejas.resumen_dia(conn)


@router.get("/bandejas/no-confirmadas", tags=["Bandejas"], summary="Citas próximas sin confirmación",
            description="Las `no_confirmada` y, hasta el fin de mañana, las `programada` que aún no respondieron. "
                        "Los pacientes dados de baja se listan en `dados-de-baja`.",
            response_model=list[sc.NoConfirmadaOut])
def no_confirmadas(conn=Depends(get_conn), u=Depends(auxiliar)):
    return _con_color(conn, [{**r, "cita_id": r["id"]} for r in bandejas.no_confirmadas(conn)])


@router.get("/bandejas/seguimientos", tags=["Bandejas"], summary="Casos de seguimiento abiertos y escalados",
            response_model=list[sc.SeguimientoOut])
def seguimientos(conn=Depends(get_conn), u=Depends(auxiliar)):
    return _con_color(conn, bandejas.seguimientos(conn))


@router.get("/bandejas/en-riesgo", tags=["Bandejas"], summary="Pacientes con tratamiento a medias",
            response_model=list[sc.EnRiesgoOut])
def en_riesgo(profesional_id: int | None = None, servicio_id: int | None = None, conn=Depends(get_conn),
              u=Depends(auxiliar)):
    return [_nombre(r) for r in bandejas.en_riesgo(conn, profesional_id, servicio_id)]


@router.get("/bandejas/planes", tags=["Bandejas"], summary="Planes sin siguiente paso",
            description="Plan entregado hace más de 7 días, sin cita posterior con ese profesional ni abono desde entonces. "
                        "Primero los pacientes de alto valor y luego el `valor_plan` más alto.",
            response_model=list[sc.PlanSinPasoOut])
def planes_sin_siguiente_paso(conn=Depends(get_conn), u=Depends(auxiliar)):
    return planes.sin_siguiente_paso(conn)


@router.get("/bandejas/cupos-libres", tags=["Bandejas"], summary="Cupos liberados abiertos o en oferta",
            response_model=list[sc.CupoLibreOut])
def cupos_libres(conn=Depends(get_conn), u=Depends(auxiliar)):
    return bandejas.cupos_libres(conn)


@router.get("/bandejas/sin-desenlace", tags=["Bandejas"], summary="Citas pasadas sin desenlace",
            response_model=list[sc.SinDesenlaceOut])
def sin_desenlace(conn=Depends(get_conn), u=Depends(auxiliar)):
    return [{**r, "cita_id": r["id"]} for r in bandejas.sin_desenlace(conn)]


@router.get("/bandejas/sin-interpretar", tags=["Bandejas"], summary="Mensajes entrantes sin interpretar",
            response_model=list[sc.SinInterpretarOut])
def sin_interpretar(conn=Depends(get_conn), u=Depends(auxiliar)):
    return bandejas.sin_interpretar(conn)


@router.get("/bandejas/contactos", tags=["Bandejas"], summary="Solicitudes de contacto pendientes",
            response_model=list[sc.ContactoOut])
def contactos(conn=Depends(get_conn), u=Depends(auxiliar)):
    return bandejas.contactos_pendientes(conn)


@router.get("/bandejas/dados-de-baja", tags=["Bandejas"], summary="Citas próximas de pacientes dados de baja",
            response_model=list[sc.BajaOut])
def dados_de_baja(conn=Depends(get_conn), u=Depends(auxiliar)):
    return _con_color(conn, [{**r, "cita_id": r["id"]} for r in bandejas.dados_de_baja(conn)])


@router.get("/bandejas/celulares-por-revisar", tags=["Bandejas"],
            summary="Pacientes con cita o seguimiento cuyo celular no sirve",
            description="Sin celular, con uno no válido o que no es WhatsApp. Si tienen un responsable con celular utilizable, "
                        "trae sus datos para contactarlo a él.", response_model=list[sc.CelularPorRevisarOut])
def celulares_por_revisar(conn=Depends(get_conn), u=Depends(auxiliar)):
    return bandejas.celulares_por_revisar(conn)


# ----------------------------------------------------------------- acciones de bandeja

@router.post("/seguimientos/{caso_id}/gestion", tags=["Acciones de bandeja"],
             summary="Registrar la gestión (llamada) de un seguimiento", response_model=sc.Ok)
def gestion(caso_id: int, datos: sc.Gestion, conn=Depends(get_conn), u=Depends(auxiliar)):
    caso = conn.execute("select estado from caso_seguimiento where id=%s", (caso_id,)).fetchone()
    if caso is None:
        raise permisos.NoExiste("No existe ese seguimiento")
    if caso["estado"] not in ("abierto", "agotado"):
        raise lifecycle.InvalidTransition("Ese seguimiento ya está cerrado")
    followup.register_manual(conn, caso_id, datos.resultado, datos.detalle, user_id=u["id"])
    return sc.Ok()


@router.post("/mensajes/{mensaje_id}/gestionar", tags=["Acciones de bandeja"],
             summary="Marcar un mensaje entrante como gestionado", response_model=sc.Ok)
def gestionar_mensaje(mensaje_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not bandejas.mark_message_managed(conn, mensaje_id, u["id"]):
        raise permisos.NoExiste("No existe ese mensaje")
    return sc.Ok()


@router.post("/contactos/{solicitud_id}/gestionar", tags=["Acciones de bandeja"],
             summary="Marcar una solicitud de contacto como gestionada", response_model=sc.Ok)
def gestionar_contacto(solicitud_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not bandejas.mark_contact_managed(conn, solicitud_id):
        raise permisos.NoExiste("No existe esa solicitud")
    return sc.Ok()


@router.get("/contactos/{solicitud_id}/adjuntos/{adjunto_id}", tags=["Acciones de bandeja"],
            summary="Descargar una foto o PDF adjunto a una solicitud del sitio web",
            response_class=Response, dependencies=[auditar("ver_adjunto_solicitud")],
            responses={200: {"description": "El archivo, siempre como descarga", "content": {
                t: {"schema": {"type": "string", "format": "binary"}}
                for t in ("image/jpeg", "image/png", "image/webp", "application/pdf")}}})
def adjunto_contacto(solicitud_id: int, adjunto_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    a = solicitudes.adjunto(conn, solicitud_id, adjunto_id)
    if a is None:
        raise permisos.NoExiste("No existe ese archivo")
    # Siempre como adjunto y sin adivinar el tipo: el archivo lo subió alguien de fuera.
    return Response(bytes(a["datos"]), media_type=a["tipo"], headers={
        "Content-Disposition": f"attachment; filename=\"{a['nombre']}\"; filename*=UTF-8''{quote(a['nombre'])}",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.post("/contactos/{solicitud_id}/paciente", tags=["Acciones de bandeja"], response_model=sc.Ok,
             summary="Vincular una solicitud del sitio web a un paciente",
             description="Si el paciente no tiene correo toma el de la solicitud (sin autorizar envíos). Una evaluación "
                         "virtual lo marca como internacional. Al anonimizar al paciente, la solicitud se borra con él.")
def vincular_contacto(solicitud_id: int, datos: sc.VincularSolicitud, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not solicitudes.vincular(conn, solicitud_id, datos.paciente_id, u["id"]):
        raise permisos.NoExiste("No existe esa solicitud o ese paciente")
    return sc.Ok()


# ----------------------------------------------------------------- indicadores

def filtros(desde: date | None = None, hasta: date | None = None, profesional_id: int | None = None,
            servicio_id: int | None = None, conn=Depends(get_conn)) -> dict:
    hoy = clock.now(conn).date()
    hasta = hasta or hoy
    desde = desde or hasta - timedelta(days=60)
    if desde > hasta:
        raise ApiError(422, "rango_invalido", "La fecha final no puede ser anterior a la inicial.")
    return {"desde": desde, "hasta": hasta, "profesional_id": profesional_id, "servicio_id": servicio_id}


@router.get("/indicadores/resumen", tags=["Indicadores"], summary="Indicadores del periodo", response_model=sc.ResumenOut)
def resumen(comparar: bool = Query(False, description="Añade `anterior`: las mismas cifras del periodo previo de igual duración."),
            conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.summary(conn, f, comparar)


@router.get("/indicadores/tendencia", tags=["Indicadores"], summary="Tendencia de inasistencia por día o semana",
            response_model=list[sc.PuntoTendencia])
def tendencia(agrupar: str = Query("dia", pattern="^(dia|semana)$"), conn=Depends(get_conn), f=Depends(filtros),
              u=Depends(auxiliar)):
    return indicators.weekly_trend(conn, f) if agrupar == "semana" else indicators.trend(conn, f)


@router.get("/indicadores/por-profesional", tags=["Indicadores"], summary="Inasistencia por profesional",
            response_model=list[sc.FilaDimension])
def por_profesional(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.by_dimension(conn, f, "profesional")


@router.get("/indicadores/por-servicio", tags=["Indicadores"], summary="Inasistencia por servicio",
            response_model=list[sc.FilaDimension])
def por_servicio(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.by_dimension(conn, f, "servicio")


@router.get("/indicadores/motivos", tags=["Indicadores"], summary="Motivos de cancelación",
            response_model=list[sc.MotivoIndicador])
def motivos(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.reasons(conn, f)


@router.get("/indicadores/tiempo-entre-citas", tags=["Indicadores"], summary="Días entre citas atendidas consecutivas",
            response_model=sc.TiempoEntreCitas)
def tiempo_entre_citas(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return sc.TiempoEntreCitas(por_servicio=indicators.time_between(conn, f),
                               por_paciente_dias=indicators.time_between_patient(conn, f))


@router.get("/indicadores/faltas-repetidas", tags=["Indicadores"], summary="Pacientes con 2 o más inasistencias en el periodo",
            response_model=list[sc.FaltasRepetidasOut])
def faltas_repetidas(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.repeat_no_shows(conn, f)


@router.get("/indicadores/citas-perdidas", tags=["Indicadores"],
            summary="Citas del periodo con inasistencia o cancelación tardía",
            description="El detalle detrás de las cifras por profesional o servicio: usa `profesional_id` o `servicio_id`.",
            response_model=list[sc.CitaPerdidaOut])
def citas_perdidas(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.missed_appointments(conn, f)


@router.get("/indicadores/recordatorios", tags=["Indicadores"], summary="Inasistencia con y sin recordatorio, y embudo",
            response_model=sc.RecordatoriosOut)
def recordatorios(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.reminders(conn, f)


@router.get("/indicadores/pendientes", tags=["Indicadores"], summary="¿El equipo cierra sus pendientes?",
            description="Tiempo en resolver desenlaces de citas, mensajes y seguimientos hechos a mano, por quien los resolvió. "
                        "El periodo es el día en que se resolvió; los abiertos son los de hoy.",
            response_model=sc.PendientesOut)
def pendientes(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.pending_followthrough(conn, f)


@router.get("/indicadores/reagendamiento", tags=["Indicadores"], summary="Días entre cancelar y volver a agendar",
            description="Cancelaciones del periodo y cuándo agendó de nuevo el mismo paciente (mismo profesional o servicio, "
                        "hasta 60 días después).", response_model=sc.ReagendamientoOut)
def reagendamiento(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.rebooking(conn, f)


@router.get("/indicadores/dia-hora", tags=["Indicadores"], summary="Atendidas y no asistió por día de la semana y hora",
            response_model=list[sc.CeldaDiaHora])
def dia_hora(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.weekday_hour(conn, f)


@router.get("/indicadores/planes", tags=["Indicadores"], summary="Planes entregados y su siguiente paso",
            description="Planes entregados en el periodo, % con cita o abono dentro de los 15 días y `valor_plan` de los que "
                        "no tienen siguiente paso (solo si hay valores).", response_model=sc.PlanesIndicadorOut)
def indicador_planes(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return planes.resumen_periodo(conn, f["desde"], f["hasta"])


@router.post("/indicadores/cierre", tags=["Indicadores"], summary="Ejecutar el cierre de todo el historial",
             response_model=sc.CierreOut, description="Idempotente: repetirlo reemplaza los hechos diarios sin duplicar.")
def cierre(conn=Depends(get_conn), u=Depends(auxiliar)):
    r = indicators.close_all(conn)
    return sc.CierreOut(**r, ultimo_cierre=config.get(conn, "ultimo_diario"))


# ----------------------------------------------------------------- sistema

@router.get("/sistema", tags=["Sistema"], summary="Tareas, último cierre y configuración vigente",
            response_model=sc.SistemaOut)
def sistema(conn=Depends(get_conn), u=Depends(auxiliar)):
    # Un cierre fechado en el futuro (reloj simulado que retrocedió) no se muestra: el máximo es hoy.
    ultimo, hoy = config.get(conn, "ultimo_diario"), clock.now(conn).date().isoformat()
    return sc.SistemaOut(tareas_fallidas=alertas.fallidas(conn), tareas_pendientes=bandejas.pending_tasks(conn),
                         tareas_atrasadas=alertas.atrasadas(conn),
                         ultimo_cierre=min(ultimo, hoy) if ultimo else None, configuracion=config.effective(conn))
