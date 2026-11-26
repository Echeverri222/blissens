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
Accion = Literal["desenlace", "confirmar", "cancelar", "cambiar_fecha"]


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


class NegocioOut(Salida):
    id: int
    nombre_corto: str
    nombre: str
    zona_horaria: str


class SesionOut(Salida):
    usuario: str
    nombre: str
    rol: Literal["auxiliar", "especialista"] | None
    profesional_id: int | None
    profesional: str | None
    hora_sistema: Momento
    modo_demo: bool
    negocio: NegocioOut | None
    negocios: list[NegocioOut]
    administrador: bool
    debe_cambiar_clave: bool
    simulador: bool


class ElegirNegocio(Entrada):
    negocio_id: int


class MarcaOut(Salida):
    nombre: str


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
    acciones: list[Accion] = Field(description="Lo que el usuario que consulta puede hacer con la cita ahora")


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
    reversible: bool = Field(description="Si el usuario que consulta puede intentar revertir este movimiento")


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
    acciones: list[Accion] = Field(description="Lo que el usuario que consulta puede hacer con la cita ahora")
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


class ConsentimientoCorreo(Entrada):
    correo: str | None = None
    acepta: bool


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


class ResponsableOut(Salida):
    id: int
    nombre: str
    parentesco: str | None = Field(description="Parentesco de este paciente con su responsable")


class FamiliarOut(Salida):
    id: int
    nombre: str
    parentesco: str | None
    menor: bool


class FamiliaOut(Salida):
    """Quién gestiona las citas de este paciente desde su enlace, y de quiénes las gestiona él (docs/prd-familia.md)."""
    responsable: ResponsableOut | None
    familiares: list[FamiliarOut]
    menor: bool


class FichaCompleta(Salida):
    paciente: FichaPaciente
    familia: FamiliaOut
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


class ResumenDiaOut(Salida):
    citas_hoy: int = Field(description="Citas vivas de hoy, de todos los profesionales")
    sin_confirmar: int = Field(description="Citas programadas o sin confirmar que empiezan desde ahora hasta el fin de mañana")
    mensajes: int = Field(description="Mensajes entrantes por responder")
    por_cerrar: int = Field(description="Citas pasadas sin desenlace")


class NoConfirmadaOut(Salida):
    cita_id: int
    estado: Literal["programada", "no_confirmada"] = Field(
        description="`no_confirmada`: «Sin confirmar»; `programada` (de hoy o mañana): «Sin respuesta aún»")
    inicio: Momento
    profesional: str
    paciente_id: int
    paciente: str
    celular: str | None
    recordatorio_enviado: bool
    recordatorio_en: Momento | None = Field(None, description="Cuándo salió el último recordatorio, si se registró la hora")


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


# ----------------------------------------------------------------- administración

class UsuarioAdmin(Salida):
    acceso_id: int
    id: int
    nombre_usuario: str
    nombre: str
    rol: Literal["auxiliar", "especialista"]
    activo: bool
    administrador: bool
    profesional_id: int | None
    ultimo_acceso: Momento | None
    bloqueado: bool


class NuevoUsuario(Entrada):
    usuario: str = Field(min_length=1, max_length=60)
    nombre: str = Field(min_length=1, max_length=120)
    rol: Literal["auxiliar", "especialista"]
    profesional_id: int | None = None
    administrador: bool = False


class CambioAcceso(Entrada):
    rol: Literal["auxiliar", "especialista"]
    profesional_id: int | None = None
    administrador: bool = False


class UsuarioConClave(Salida):
    usuario: UsuarioAdmin
    clave_temporal: str | None = Field(description="Se muestra una sola vez; la persona debe cambiarla al ingresar")
