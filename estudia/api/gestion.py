"""Rutas de la auxiliar: pacientes, bandejas, indicadores y sistema. Todas exigen el rol auxiliar."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from .. import bandejas, clock, config, followup, indicators, lifecycle, pacientes, permisos
from . import schemas as sc
from .comun import ApiError, auxiliar, get_conn, inicio, solo_json

router = APIRouter(dependencies=[Depends(solo_json)])


# ----------------------------------------------------------------- pacientes

@router.get("/pacientes", tags=["Pacientes"], summary="Buscar pacientes por nombre, documento o celular",
            response_model=list[sc.PacienteResumen])
def buscar(q: str = Query(min_length=1), conn=Depends(get_conn), u=Depends(auxiliar)):
    return bandejas.find_patients(conn, q)


@router.post("/pacientes", tags=["Pacientes"], summary="Crear un paciente (con consentimiento)",
             response_model=sc.PacienteCreado, status_code=201)
def crear(datos: sc.NuevoPaciente, conn=Depends(get_conn), u=Depends(auxiliar)):
    return sc.PacienteCreado(paciente_id=pacientes.create(
        conn, datos.nombres, datos.apellidos, datos.documento, datos.celular, datos.consentimiento))


@router.get("/pacientes/{paciente_id}", tags=["Pacientes"], summary="Ficha completa del paciente",
            response_model=sc.FichaCompleta)
def ficha(paciente_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not conn.execute("select 1 from paciente where id=%s", (paciente_id,)).fetchone():
        raise permisos.NoExiste("No existe ese paciente")
    r = bandejas.patient_record(conn, paciente_id)
    return sc.FichaCompleta(
        paciente=r["paciente"], citas=[{**c, "inicio": inicio(c)} for c in r["citas"]], historial=r["historial"],
        casos=[{**c, "intentos": c["intentos"] or []} for c in r["casos"]], mensajes=r["mensajes"])


# ----------------------------------------------------------------- bandejas

def _nombre(r: dict) -> dict:
    return {**r, "paciente": f"{r['nombres']} {r['apellidos']}".strip()}


@router.get("/bandejas", tags=["Bandejas"], summary="Conteo de todas las bandejas", response_model=sc.ConteoBandejas)
def conteo(conn=Depends(get_conn), u=Depends(auxiliar)):
    return sc.ConteoBandejas(
        no_confirmadas=len(bandejas.no_confirmadas(conn)), seguimientos=len(bandejas.seguimientos(conn)),
        en_riesgo=len(bandejas.en_riesgo(conn)), cupos_libres=len(bandejas.cupos_libres(conn)),
        sin_desenlace=len(bandejas.sin_desenlace(conn)), sin_interpretar=len(bandejas.sin_interpretar(conn)),
        contactos=len(bandejas.contactos_pendientes(conn)), dados_de_baja=len(bandejas.dados_de_baja(conn)))


@router.get("/bandejas/no-confirmadas", tags=["Bandejas"], summary="Citas próximas sin confirmación",
            response_model=list[sc.NoConfirmadaOut])
def no_confirmadas(conn=Depends(get_conn), u=Depends(auxiliar)):
    return [{**r, "cita_id": r["id"]} for r in bandejas.no_confirmadas(conn)]


@router.get("/bandejas/seguimientos", tags=["Bandejas"], summary="Casos de seguimiento abiertos y escalados",
            response_model=list[sc.SeguimientoOut])
def seguimientos(conn=Depends(get_conn), u=Depends(auxiliar)):
    return bandejas.seguimientos(conn)


@router.get("/bandejas/en-riesgo", tags=["Bandejas"], summary="Pacientes con tratamiento a medias",
            response_model=list[sc.EnRiesgoOut])
def en_riesgo(conn=Depends(get_conn), u=Depends(auxiliar)):
    return [_nombre(r) for r in bandejas.en_riesgo(conn)]


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
    return [{**r, "cita_id": r["id"]} for r in bandejas.dados_de_baja(conn)]


# ----------------------------------------------------------------- acciones de bandeja

@router.post("/seguimientos/{caso_id}/gestion", tags=["Acciones de bandeja"],
             summary="Registrar la gestión (llamada) de un seguimiento", response_model=sc.Ok)
def gestion(caso_id: int, datos: sc.Gestion, conn=Depends(get_conn), u=Depends(auxiliar)):
    caso = conn.execute("select estado from caso_seguimiento where id=%s", (caso_id,)).fetchone()
    if caso is None:
        raise permisos.NoExiste("No existe ese seguimiento")
    if caso["estado"] not in ("abierto", "agotado"):
        raise lifecycle.InvalidTransition("Ese seguimiento ya está cerrado")
    followup.register_manual(conn, caso_id, datos.resultado, datos.detalle)
    return sc.Ok()


@router.post("/mensajes/{mensaje_id}/gestionar", tags=["Acciones de bandeja"],
             summary="Marcar un mensaje entrante como gestionado", response_model=sc.Ok)
def gestionar_mensaje(mensaje_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not bandejas.mark_message_managed(conn, mensaje_id):
        raise permisos.NoExiste("No existe ese mensaje")
    return sc.Ok()


@router.post("/contactos/{solicitud_id}/gestionar", tags=["Acciones de bandeja"],
             summary="Marcar una solicitud de contacto como gestionada", response_model=sc.Ok)
def gestionar_contacto(solicitud_id: int, conn=Depends(get_conn), u=Depends(auxiliar)):
    if not bandejas.mark_contact_managed(conn, solicitud_id):
        raise permisos.NoExiste("No existe esa solicitud")
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
def resumen(conn=Depends(get_conn), f=Depends(filtros), u=Depends(auxiliar)):
    return indicators.summary(conn, f)


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


@router.post("/indicadores/cierre", tags=["Indicadores"], summary="Ejecutar el cierre de todo el historial",
             response_model=sc.CierreOut, description="Idempotente: repetirlo reemplaza los hechos diarios sin duplicar.")
def cierre(conn=Depends(get_conn), u=Depends(auxiliar)):
    r = indicators.close_all(conn)
    return sc.CierreOut(**r, ultimo_cierre=config.get(conn, "ultimo_diario"))


# ----------------------------------------------------------------- sistema

@router.get("/sistema", tags=["Sistema"], summary="Tareas, último cierre y configuración vigente",
            response_model=sc.SistemaOut)
def sistema(conn=Depends(get_conn), u=Depends(auxiliar)):
    return sc.SistemaOut(tareas_fallidas=bandejas.tareas_fallidas(conn), tareas_pendientes=bandejas.pending_tasks(conn),
                         ultimo_cierre=config.get(conn, "ultimo_diario"), configuracion=config.effective(conn))
