"""Modelos de entrada y salida de la API. El esquema OpenAPI que generan es el contrato con el front."""
from datetime import date, datetime, time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from .. import clock


def _iso(d: datetime) -> str:
    return d.astimezone(clock.TZ).isoformat()


# Toda fecha y hora sale en ISO 8601 con la zona horaria de Bogotá.
Momento = Annotated[datetime, PlainSerializer(_iso, return_type=str, when_used="json")]
Estado = Literal["programada", "confirmada", "no_confirmada", "cancelada", "reprogramada", "atendida", "no_asistio"]
Actor = Literal["paciente", "auxiliar", "especialista", "sistema"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------- errores y genéricos

class Error(Salida):
    codigo: str = Field(description="Código estable, para que el front decida qué hacer")
    mensaje: str = Field(description="Mensaje en español, listo para mostrar")
    citas: list["CitaEnConflicto"] | None = Field(None, description="Solo en `bloqueo_con_citas`")


class Ok(Salida):
    ok: bool = True


# ----------------------------------------------------------------- sesión

class Credenciales(Entrada):
    usuario: str
    clave: str


class CambioClave(Entrada):
    actual: str
    nueva: str


class SesionOut(Salida):
    usuario: str
    nombre: str
    rol: Literal["auxiliar", "especialista"]
    profesional_id: int | None
    profesional: str | None
    hora_sistema: Momento
    modo_demo: bool


# ----------------------------------------------------------------- catálogos

class ProfesionalOut(Salida):
    id: int
    nombre: str
    especialidad: str


class ServicioOut(Salida):
    id: int
    nombre: str
    duracion_min: int
    autoagendable: bool


class MotivoOut(Salida):
    id: int
    etiqueta: str


# ----------------------------------------------------------------- agenda

class CitaAgenda(Salida):
    id: int
    estado: Estado
    dia: date
    inicio: Momento | None
    fin: Momento | None
    profesional_id: int
    profesional: str
    servicio_id: int
    servicio: str
    paciente_id: int
    paciente: str
    celular: str | None


class BloqueoOut(Salida):
    id: int
    profesional_id: int
    inicio: Momento
    fin: Momento
    motivo: str
    creado_por: str | None = Field(None, description="Nombre visible del usuario que lo creó")


class FranjaOut(Salida):
    profesional_id: int
    fecha: date
    inicio: Momento
    fin: Momento


class CupoOut(Salida):
    id: int
    profesional_id: int
    inicio: Momento
    fin: Momento
    estado: Literal["abierto", "en_oferta"]
    causa: str


class AgendaOut(Salida):
    desde: date
    hasta: date
    profesional_id: int | None
    citas: list[CitaAgenda]
    citas_sin_hora: list[CitaAgenda] = Field(description="Citas importadas sin hora, por día")
    bloqueos: list[BloqueoOut]
    franjas: list[FranjaOut]
    cupos_liberados: list[CupoOut]


class HorarioFranja(Salida):
    dia_semana: int = Field(description="0 = lunes")
    desde: time
    hasta: time


class HorarioOut(Salida):
    profesional_id: int
    franjas: list[HorarioFranja]


# ----------------------------------------------------------------- citas

class PacienteMinimo(Salida):
    id: int
    nombre: str
    celular: str | None


class CambioHistorial(Salida):
    id: int
    estado_anterior: Estado | None
    estado_nuevo: Estado
    actor: Actor
    usuario: str | None = Field(None, description="Nombre visible del usuario que hizo el cambio")
    detalle: str
    momento: Momento
    revierte_id: int | None
    revertido: bool


class CitaDetalle(Salida):
    id: int
    estado: Estado
    dia: date
    inicio: Momento | None
    fin: Momento | None
    profesional_id: int
    profesional: str
    servicio_id: int
    servicio: str
    paciente: PacienteMinimo
    historial: list[CambioHistorial]


class CitaEnConflicto(Salida):
    id: int
    estado: Estado
    inicio: Momento
    fin: Momento
    servicio: str
    paciente_id: int
    paciente: str


class NuevaCita(Entrada):
    paciente_id: int
    profesional_id: int
    servicio_id: int
    inicio: datetime


class Cancelacion(Entrada):
    motivo_id: int
    texto: str | None = None


class CambioFecha(Entrada):
    inicio: datetime


class Desenlace(Entrada):
    desenlace: Literal["atendida", "no_asistio"]


class CitaCreada(Salida):
    cita_id: int


class Reversion(Salida):
    historial_id: int


class EspaciosDia(Salida):
    fecha: date
    horas: list[Momento]


class EspaciosOut(Salida):
    profesional_id: int
    servicio_id: int
    dias: list[EspaciosDia]


# ----------------------------------------------------------------- bloqueos

class NuevoBloqueo(Entrada):
    profesional_id: int | None = Field(None, description="Obligatorio para la auxiliar; el especialista usa el suyo")
    inicio: datetime
    fin: datetime
    motivo: str = ""


# ----------------------------------------------------------------- pacientes

class PacienteResumen(Salida):
    id: int
    nombres: str
    apellidos: str
    documento: str | None
    celular: str | None


class NuevoPaciente(Entrada):
    nombres: str
    apellidos: str = ""
    documento: str
    celular: str
    consentimiento: bool


class PacienteCreado(Salida):
    paciente_id: int


class FichaPaciente(Salida):
    id: int
    nombres: str
    apellidos: str
    documento: str | None
    celular: str | None
    correo: str | None
    acepta_mensajes: bool


class CitaFicha(Salida):
    id: int
    estado: Estado
    dia: date
    inicio: Momento | None
    origen: str
    profesional: str
    servicio: str


class CambioFicha(CambioHistorial):
    cita_id: int


class IntentoOut(Salida):
    numero: int
    canal: str
    resultado: str | None
    momento: Momento


class CasoOut(Salida):
    id: int
    tipo: str
    estado: str
    escalado: bool
    abierto_en: Momento
    cerrado_en: Momento | None
    intentos: list[IntentoOut]


class MensajeOut(Salida):
    id: int
    direccion: Literal["saliente", "entrante"]
    texto: str
    botones: list[Any]
    momento: Momento


class FichaCompleta(Salida):
    paciente: FichaPaciente
    citas: list[CitaFicha]
    historial: list[CambioFicha]
    casos: list[CasoOut]
    mensajes: list[MensajeOut]


# ----------------------------------------------------------------- bandejas

class ConteoBandejas(Salida):
    no_confirmadas: int
    seguimientos: int
    en_riesgo: int
    cupos_libres: int
    sin_desenlace: int
    sin_interpretar: int
    contactos: int
    dados_de_baja: int


class NoConfirmadaOut(Salida):
    cita_id: int
    inicio: Momento
    profesional: str
    paciente_id: int
    paciente: str
    celular: str | None


class SeguimientoOut(Salida):
    id: int
    tipo: str
    estado: str
    escalado: bool
    abierto_en: Momento
    paciente_id: int
    paciente: str
    celular: str | None
    intentos: int
    ultimo: str | None


class EnRiesgoOut(Salida):
    tratamiento_id: int
    paciente_id: int
    paciente: str
    ultima_cita: date
    dias_sin_cita: int
    caso_id: int | None


class CupoLibreOut(Salida):
    id: int
    inicio: Momento
    fin: Momento
    estado: str
    causa: str
    profesional: str
    ofertas: int
    ofrecido_a: str | None


class SinDesenlaceOut(Salida):
    cita_id: int
    inicio: Momento
    estado: Estado
    profesional: str
    paciente_id: int
    paciente: str


class SinInterpretarOut(Salida):
    id: int
    momento: Momento
    texto: str
    paciente_id: int
    paciente: str


class ContactoOut(Salida):
    id: int
    documento: str
    celular: str
    nota: str
    momento: Momento


class BajaOut(Salida):
    cita_id: int
    inicio: Momento
    paciente_id: int
    paciente: str
    celular: str | None


class Gestion(Entrada):
    resultado: Literal["acepto", "rechazo", "sin_respuesta"]
    detalle: str = ""


# ----------------------------------------------------------------- indicadores

class ResumenOut(Salida):
    citas: int
    atendidas: int
    no_asistio: int
    atencion_efectiva: float | None
    inasistencia: float | None
    cancelaciones: int
    cancelaciones_tardias: int
    cancelaciones_recuperadas: int
    recuperacion: float | None
    confirmacion: float | None
    ocupacion: float | None
    minutos_disponibles: int
    minutos_atendidos: int
    cupos_liberados: int
    cupos_ocupados_oferta: int
    cupos_ocupados_agendamiento: int
    cupos_vacios: int


class PuntoTendencia(Salida):
    fecha: date
    citas: int
    atendidas: int
    no_asistio: int
    inasistencia: float | None


class FilaDimension(Salida):
    nombre: str
    citas: int
    atendidas: int
    no_asistio: int
    inasistencia: float | None


class MotivoIndicador(Salida):
    motivo: str
    cancelaciones: int
    tardias: int


class TiempoServicio(Salida):
    servicio: str
    dias: float
    pares: int


class TiempoEntreCitas(Salida):
    por_servicio: list[TiempoServicio]
    por_paciente_dias: float | None


class CierreOut(Salida):
    dias: int
    desde: date | None
    hasta: date | None
    ultimo_cierre: str | None


# ----------------------------------------------------------------- sistema

class TareaFallida(Salida):
    id: int
    tipo: str
    ejecutar_en: Momento
    intentos: int
    error: str | None


class SistemaOut(Salida):
    tareas_fallidas: list[TareaFallida]
    tareas_pendientes: int
    ultimo_cierre: str | None
    configuracion: dict[str, Any]


Error.model_rebuild()
