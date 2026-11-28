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
    usuario: str = Field(min_length=1, max_length=128)
    clave: str = Field(min_length=1, max_length=128)


class CambioClave(Entrada):
    actual: str = Field(min_length=1, max_length=128)
    nueva: str = Field(min_length=1, max_length=128)


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
    valor: int | None = Field(None, description="Valor promedio en pesos; `null` si no se ha configurado.")


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

Segmento = Literal["internacional", "deportista"]


class PacienteResumen(Salida):
    id: int
    nombres: str
    apellidos: str
    documento: str | None
    celular: str | None
    internacional: bool = Field(description="Paciente internacional (segmento de alto valor).")
    deportista: bool = Field(description="Deportista de alto nivel (segmento de alto valor).")


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


SegmentoOrigen = Literal["recepcion", "importacion", "sitio_en"]


class Segmentos(Entrada):
    internacional: bool = Field(description="Paciente internacional (segmento de alto valor).")
    deportista: bool = Field(description="Deportista de alto nivel (segmento de alto valor).")


class SegmentosOut(Salida):
    internacional: bool = Field(description="Paciente internacional (segmento de alto valor).")
    deportista: bool = Field(description="Deportista de alto nivel (segmento de alto valor).")
    segmento_origen: SegmentoOrigen | None = Field(
        description="De dónde salió la última marca: la recepción, la importación del Excel o el registro en el sitio en inglés.")
    segmento_marcado_en: Momento | None


class FichaPaciente(Salida):
    id: int
    nombres: str
    apellidos: str
    documento: str | None
    celular: str | None
    correo: str | None
    acepta_mensajes: bool
    internacional: bool = Field(description="Paciente internacional (segmento de alto valor).")
    deportista: bool = Field(description="Deportista de alto nivel (segmento de alto valor).")
    segmento_origen: SegmentoOrigen | None


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
    gestionado: bool = Field(description="Solo cuenta en los entrantes: falso mientras nadie lo haya respondido o descartado.")


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
    internacional: bool = Field(description="Paciente internacional (segmento de alto valor).")
    deportista: bool = Field(description="Deportista de alto nivel (segmento de alto valor).")


class EnRiesgoOut(Salida):
    tratamiento_id: int
    paciente_id: int
    paciente: str
    ultima_cita: date
    dias_sin_cita: int
    caso_id: int | None
    celular: str | None
    servicio: str | None
    internacional: bool = Field(description="Paciente internacional (segmento de alto valor).")
    deportista: bool = Field(description="Deportista de alto nivel (segmento de alto valor).")


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


class AdjuntoOut(Salida):
    id: int
    nombre: str
    tipo: str
    tamano: int = Field(description="Bytes")


class ContactoOut(Salida):
    id: int
    documento: str
    celular: str
    nota: str
    momento: Momento
    origen: Literal["paciente", "sitio"] = Field(description="`sitio`: llegó por un formulario del sitio web")
    interes: Literal["evaluacion_virtual", "experiencia", "contacto"] | None = None
    idioma: Literal["es", "en"] | None = None
    nombre: str | None = None
    correo: str | None = None
    pais: str | None = None
    paquete: str | None = None
    mensaje: str | None = None
    paciente_id: int | None = Field(None, description="Paciente al que la recepción vinculó la solicitud")
    paciente: str | None = None
    adjuntos: list[AdjuntoOut] = []


class VincularSolicitud(Entrada):
    paciente_id: int


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

class ResumenBase(Salida):
    citas: int
    atendidas: int
    no_asistio: int
    atencion_efectiva: float | None = Field(description="Obsoleto: atendidas ÷ todas las citas. Usa `asistencia`.")
    asistencia: float | None = Field(description="Atendidas ÷ (atendidas + no asistió + canceladas).")
    inasistencia: float | None
    cancelaciones: int
    cancelaciones_tardias: int
    cancelaciones_recuperadas: int
    recuperacion: float | None
    confirmacion: float | None
    sin_desenlace: int = Field(description="Citas pasadas del rango que siguen programadas, confirmadas o sin confirmar.")
    capacidad_aplica: bool = Field(description="False con un servicio elegido: ocupación y cupos no se consolidan por servicio.")
    ocupacion: float | None
    minutos_disponibles: int | None
    minutos_atendidos: int
    cupos_liberados: int | None
    cupos_ocupados_oferta: int | None
    cupos_ocupados_agendamiento: int | None
    cupos_vacios: int | None
    valor_perdido: int = Field(description="Pesos perdidos: inasistencias + cancelaciones tardías no reagendadas, al valor de cada servicio.")
    valor_perdido_inasistencia: int
    valor_perdido_tardias: int
    citas_sin_valor: int = Field(description="Citas perdidas cuyo servicio no tiene valor configurado: no suman al dinero perdido.")


class MetaMinima(Entrada):
    min: float = Field(ge=0, le=1)


class MetaMaxima(Entrada):
    max: float = Field(ge=0, le=1)


class MetaDinero(Entrada):
    max: int = Field(ge=0, le=10**12)


class Metas(Entrada):
    """Metas de los indicadores; todas son opcionales. Tasas entre 0 y 1; el dinero en pesos."""
    inasistencia: MetaMaxima | None = None
    asistencia: MetaMinima | None = None
    confirmacion: MetaMinima | None = None
    dinero_perdido: MetaDinero | None = None


class ResumenOut(ResumenBase):
    metas: dict[str, dict[str, float]] = Field(description="Metas vigentes, p. ej. `{\"inasistencia\": {\"max\": 0.15}}`; solo las que existen.")
    desde_anterior: date | None = Field(None, description="Solo con `comparar=true`.")
    hasta_anterior: date | None = None
    anterior: ResumenBase | None = Field(None, description="Mismas cifras del periodo anterior (igual duración, termina el día antes de `desde`).")


class ResumenTiempos(Salida):
    resueltos: int
    mediana_horas: float | None
    p90_horas: float | None
    abiertos_hoy: int
    vencidos: int = Field(description="Abiertos hoy con más de 48 h (desenlaces y mensajes) o 7 días (seguimientos).")


class PendientesUsuario(Salida):
    usuario_id: int | None
    usuario: str | None = Field(description="`null`: no se registró quién resolvió (antes de `registro_desde`).")
    resueltos: int
    mediana_horas: float | None


class PendientesOut(Salida):
    cierre_citas: ResumenTiempos
    mensajes: ResumenTiempos
    seguimientos: ResumenTiempos
    por_usuario: list[PendientesUsuario]
    registro_desde: date = Field(description="Desde esta fecha se registra quién resuelve cada pendiente.")


class BucketsReagendamiento(Salida):
    mismo_dia: int
    d1_3: int = Field(alias="1_3")
    d4_14: int = Field(alias="4_14")
    d15_60: int = Field(alias="15_60")
    no_reagendo: int


class ReagendamientoOut(Salida):
    mediana_dias: float | None = Field(description="Entre quienes volvieron a agendar.")
    total: int = Field(description="Cancelaciones del periodo.")
    buckets: BucketsReagendamiento


class PuntoTendencia(Salida):
    fecha: date
    citas: int
    atendidas: int
    no_asistio: int
    sin_desenlace: int
    inasistencia: float | None


class FilaDimension(Salida):
    id: int
    nombre: str
    citas: int
    atendidas: int
    no_asistio: int
    canceladas: int
    inasistencia: float | None
    valor_perdido: int = Field(description="Pesos perdidos en el periodo (ver `valor_perdido` del resumen).")


class FaltasRepetidasOut(Salida):
    paciente_id: int
    paciente: str
    celular: str | None
    faltas: int
    ultima_falta: date
    tiene_cita_futura: bool


class CitaPerdidaOut(Salida):
    cita_id: int
    dia: date
    inicio: Momento | None
    estado: str
    paciente_id: int
    paciente: str
    profesional: str
    servicio: str
    motivo: str | None
    cancelacion_tardia: bool | None
    reagendada: bool


class GrupoRecordatorio(Salida):
    n: int
    no_asistio: int
    inasistencia: float | None


class EmbudoRecordatorios(Salida):
    citas: int
    con_recordatorio: int
    confirmadas: int
    atendidas: int


class RecordatoriosOut(Salida):
    con_recordatorio: GrupoRecordatorio
    sin_recordatorio: GrupoRecordatorio
    embudo: EmbudoRecordatorios


class CeldaDiaHora(Salida):
    dia_semana: int = Field(description="0 = lunes … 6 = domingo")
    hora: int
    atendidas: int
    no_asistio: int


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
    error: str | None = Field(description="Detalle técnico, para quien administra el sistema")
    titulo: str = Field(description="Qué no salió, en palabras (una tarea)")
    titulo_varias: str = Field(description="Lo mismo para agrupar varias: «recordatorios de cita no salieron»")
    causa: str = Field(description="Por qué, en palabras")
    que_hacer: str = Field(description="Qué hacer con el paciente afectado")
    paciente_id: int | None
    paciente: str | None
    cita_id: int | None
    cita_inicio: Momento | None


class SistemaOut(Salida):
    tareas_fallidas: list[TareaFallida]
    tareas_pendientes: int
    tareas_atrasadas: int = Field(description="Pendientes que debieron salir hace más de 15 minutos: el envío está detenido")
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


class ValorServicio(Entrada):
    valor: int | None = Field(ge=0, lt=10**12, description="Pesos; `null` quita el valor.")


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


# ----------------------------------------------------------------- asistente

class AsistenteEstadoOut(Salida):
    disponible: bool = Field(description="El negocio encendió el asistente para el equipo (y hay clave de la API)")
    perfil: Literal["auxiliar", "especialista"]
    mensajes_restantes: int = Field(description="Mensajes que le quedan hoy a este usuario")


class AsistenteMensajeIn(Entrada):
    conversacion_id: int | None = Field(None, description="Continúa esa conversación; sin él se abre una nueva")
    texto: str = Field(min_length=1, max_length=1000)


class PropuestaOut(Salida):
    tipo: Literal["agendar", "cambiar_fecha", "cancelar", "confirmar_telefono", "desenlace", "bloqueo", "eliminar_bloqueo",
                  "crear_paciente", "segmentos", "gestion_seguimiento", "gestionar_mensaje", "gestionar_contacto",
                  "vincular_contacto", "revertir"]
    parametros: dict[str, Any] = Field(description="Lo que lleva el endpoint existente que la ejecuta, ya con sus ids")
    resumen: str = Field(description="Una línea para la tarjeta de confirmación")


class EnlaceOut(Salida):
    texto: str = Field(description="Tal como aparece en `respuesta` (el nombre completo de un paciente)")
    ruta: str = Field(description="Ruta del panel, p. ej. `/pacientes/12`")


class AsistenteRespuestaOut(Salida):
    conversacion_id: int | None = Field(description="Null solo si se respondió con una respuesta fija sin abrir conversación")
    respuesta: str = Field(description="Texto plano con saltos de línea")
    propuestas: list[PropuestaOut]
    enlaces: list[EnlaceOut] = Field(default=[], description="Nombres de la respuesta que el panel vuelve enlaces (solo recepción)")


class AsistenteTurnoOut(Salida):
    rol: Literal["usuario", "asistente"]
    texto: str
    propuestas: list[PropuestaOut] = Field(description="Solo en turnos del asistente: las que preparó en ese turno")


class AsistenteConversacionOut(Salida):
    conversacion_id: int
    mensajes: list[AsistenteTurnoOut]
