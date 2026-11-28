// Único módulo que conoce las direcciones de la API. Añade la cookie, convierte toda respuesta de error en un
// `ApiError` con `codigo` y `mensaje`, y expone funciones tipadas por recurso.
import type { CitaEnConflicto } from "./tipos";
import type {
  Agenda, Baja, Bloqueo, Cierre, CitaDetalle, Contacto, ConteoBandejas, Desenlace, Profesional, Servicio, Motivo, Horario,
  EnRiesgo, Espacios, FichaCompleta, FiltrosIndicadores, FilaDimension, MotivoIndicador, NoConfirmada, NuevoBloqueo,
  NuevoPaciente, PacienteResumen, Segmento, Segmentos, SegmentosOut, PuntoTendencia, Resumen, ResultadoGestion, Seguimiento, Sesion, SinDesenlace,
  SinInterpretar, Sistema, FaltaRepetida, CitaPerdida, Recordatorios, CeldaDiaHora, ResumenDia, TiempoEntreCitas, CupoLibre, NuevoUsuario, UsuarioAdmin, UsuarioConClave, Rol, Metas, Pendientes, Reagendamiento, AsistenteEstado, AsistenteRespuesta,
} from "./tipos";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(public codigo: string, mensaje: string, public status: number, public citas?: CitaEnConflicto[]) {
    super(mensaje);
    this.name = "ApiError";
  }
  get mensaje() { return this.message; }
}

type Query = Record<string, string | number | undefined | null>;
let alPerderSesion: (() => void) | null = null;
/** La sesión se registra aquí para reaccionar a un 401 en cualquier llamada. */
export const alNoAutenticado = (fn: (() => void) | null) => { alPerderSesion = fn; };

async function pedir<T>(metodo: string, ruta: string, opts: { query?: Query; cuerpo?: unknown; esSesion?: boolean } = {}): Promise<T> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(opts.query ?? {})) if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  const url = `${BASE}${ruta}${params.size ? `?${params}` : ""}`;
  let r: Response;
  try {
    r = await fetch(url, {
      method: metodo, credentials: "same-origin",
      headers: opts.cuerpo !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.cuerpo !== undefined ? JSON.stringify(opts.cuerpo) : undefined,
    });
  } catch {
    throw new ApiError("red", "No se pudo conectar con el sistema. Revisa tu conexión e inténtalo de nuevo.", 0);
  }
  if (r.ok) return (await r.json()) as T;
  let datos: { codigo?: string; mensaje?: string; citas?: CitaEnConflicto[] } = {};
  try { datos = await r.json(); } catch { /* respuesta sin cuerpo JSON */ }
  const error = new ApiError(datos.codigo ?? "desconocido", datos.mensaje ?? "Algo salió mal. Inténtalo de nuevo.", r.status, datos.citas);
  if (error.codigo === "no_autenticado" && !opts.esSesion) alPerderSesion?.();
  throw error;
}

const get = <T>(ruta: string, query?: Query) => pedir<T>("GET", ruta, { query });
const post = <T>(ruta: string, cuerpo?: unknown) => pedir<T>("POST", ruta, { cuerpo: cuerpo ?? {} });

export const api = {
  sesion: {
    actual: () => pedir<Sesion>("GET", "/sesion", { esSesion: true }),
    entrar: (usuario: string, clave: string) => pedir<Sesion>("POST", "/sesion", { cuerpo: { usuario, clave }, esSesion: true }),
    salir: () => pedir<{ ok: boolean }>("DELETE", "/sesion", { esSesion: true }),
    cambiarClave: (actual: string, nueva: string) => post<{ ok: boolean }>("/sesion/clave", { actual, nueva }),
    elegirNegocio: (negocio_id: number) => pedir<Sesion>("POST", "/sesion/negocio", { cuerpo: { negocio_id }, esSesion: true }),
  },
  marca: () => get<{ nombre: string }>("/marca"),
  admin: {
    usuarios: () => get<UsuarioAdmin[]>("/admin/usuarios"),
    crearUsuario: (d: NuevoUsuario) => post<UsuarioConClave>("/admin/usuarios", d),
    cambiarAcceso: (id: number, d: { rol: Rol; profesional_id: number | null; administrador: boolean }) =>
      pedir<UsuarioAdmin>("PUT", `/admin/usuarios/${id}`, { cuerpo: d }),
    desactivar: (id: number) => post<UsuarioAdmin>(`/admin/usuarios/${id}/desactivar`),
    activar: (id: number) => post<UsuarioAdmin>(`/admin/usuarios/${id}/activar`),
    claveTemporal: (id: number) => post<UsuarioConClave>(`/admin/usuarios/${id}/clave-temporal`),
    valorServicio: (id: number, valor: number | null) => pedir<Servicio>("PUT", `/admin/servicios/${id}`, { cuerpo: { valor } }),
    metas: () => get<Record<string, Record<string, number>>>("/admin/metas"),
    fijarMetas: (m: Metas) => pedir<Record<string, Record<string, number>>>("PUT", "/admin/metas", { cuerpo: m }),
  },
  catalogos: {
    profesionales: () => get<Profesional[]>("/profesionales"),
    servicios: () => get<Servicio[]>("/servicios"),
    motivos: () => get<Motivo[]>("/motivos-cancelacion"),
  },
  agenda: {
    rango: (desde: string, hasta: string, profesionalId?: number) => get<Agenda>("/agenda", { desde, hasta, profesional_id: profesionalId }),
    horario: (profesionalId: number) => get<Horario>(`/profesionales/${profesionalId}/horario`),
  },
  citas: {
    detalle: (id: number) => get<CitaDetalle>(`/citas/${id}`),
    agendar: (d: { paciente_id: number; profesional_id: number; servicio_id: number; inicio: string }) => post<{ cita_id: number }>("/citas", d),
    cancelar: (id: number, motivo_id: number, texto?: string) => post<{ ok: boolean }>(`/citas/${id}/cancelar`, { motivo_id, texto: texto || null }),
    cambiarFecha: (id: number, inicio: string) => post<{ cita_id: number }>(`/citas/${id}/cambiar-fecha`, { inicio }),
    confirmar: (id: number) => post<{ ok: boolean }>(`/citas/${id}/confirmar`),
    desenlace: (id: number, desenlace: Desenlace) => post<{ ok: boolean }>(`/citas/${id}/desenlace`, { desenlace }),
    espacios: (profesionalId: number, servicioId: number, dias = 21) =>
      get<Espacios>("/espacios", { profesional_id: profesionalId, servicio_id: servicioId, dias }),
    revertir: (historialId: number) => post<{ historial_id: number }>(`/historial/${historialId}/revertir`),
  },
  bloqueos: {
    listar: (desde: string, hasta: string, profesionalId?: number) => get<Bloqueo[]>("/bloqueos", { desde, hasta, profesional_id: profesionalId }),
    crear: (b: NuevoBloqueo) => post<Bloqueo>("/bloqueos", b),
    eliminar: (id: number) => pedir<{ ok: boolean }>("DELETE", `/bloqueos/${id}`),
  },
  pacientes: {
    buscar: (q: string, segmento?: Segmento) => get<PacienteResumen[]>("/pacientes", { q, segmento }),
    crear: (p: NuevoPaciente) => post<{ paciente_id: number }>("/pacientes", p),
    ficha: (id: number) => get<FichaCompleta>(`/pacientes/${id}`),
    segmentos: (id: number, s: Segmentos) => pedir<SegmentosOut>("PUT", `/pacientes/${id}/segmentos`, { cuerpo: s }),
  },
  bandejas: {
    conteo: () => get<ConteoBandejas>("/bandejas"),
    noConfirmadas: () => get<NoConfirmada[]>("/bandejas/no-confirmadas"),
    seguimientos: () => get<Seguimiento[]>("/bandejas/seguimientos"),
    enRiesgo: () => get<EnRiesgo[]>("/bandejas/en-riesgo"),
    enRiesgoFiltrado: (f: Pick<FiltrosIndicadores, "profesional_id" | "servicio_id">) => get<EnRiesgo[]>("/bandejas/en-riesgo", f),
    cuposLibres: () => get<CupoLibre[]>("/bandejas/cupos-libres"),
    sinDesenlace: () => get<SinDesenlace[]>("/bandejas/sin-desenlace"),
    sinInterpretar: () => get<SinInterpretar[]>("/bandejas/sin-interpretar"),
    contactos: () => get<Contacto[]>("/bandejas/contactos"),
    dadosDeBaja: () => get<Baja[]>("/bandejas/dados-de-baja"),
    gestionSeguimiento: (id: number, resultado: ResultadoGestion, detalle?: string) =>
      post<{ ok: boolean }>(`/seguimientos/${id}/gestion`, { resultado, detalle: detalle ?? "" }),
    gestionarMensaje: (id: number) => post<{ ok: boolean }>(`/mensajes/${id}/gestionar`),
    gestionarContacto: (id: number) => post<{ ok: boolean }>(`/contactos/${id}/gestionar`),
    vincularContacto: (id: number, pacienteId: number) => post<{ ok: boolean }>(`/contactos/${id}/paciente`, { paciente_id: pacienteId }),
    /** Enlace de descarga (la cookie de sesión va sola: mismo origen). */
    urlAdjunto: (solicitudId: number, adjuntoId: number) => `${BASE}/contactos/${solicitudId}/adjuntos/${adjuntoId}`,
  },
  indicadores: {
    resumen: (f: FiltrosIndicadores, comparar = false) => get<Resumen>("/indicadores/resumen", { ...f, comparar: comparar ? "true" : undefined }),
    tendencia: (f: FiltrosIndicadores, agrupar: "dia" | "semana" = "semana") => get<PuntoTendencia[]>("/indicadores/tendencia", { ...f, agrupar }),
    porProfesional: (f: FiltrosIndicadores) => get<FilaDimension[]>("/indicadores/por-profesional", f),
    porServicio: (f: FiltrosIndicadores) => get<FilaDimension[]>("/indicadores/por-servicio", f),
    motivos: (f: FiltrosIndicadores) => get<MotivoIndicador[]>("/indicadores/motivos", f),
    tiempoEntreCitas: (f: FiltrosIndicadores) => get<TiempoEntreCitas>("/indicadores/tiempo-entre-citas", f),
    faltasRepetidas: (f: FiltrosIndicadores) => get<FaltaRepetida[]>("/indicadores/faltas-repetidas", f),
    citasPerdidas: (f: FiltrosIndicadores) => get<CitaPerdida[]>("/indicadores/citas-perdidas", f),
    recordatorios: (f: FiltrosIndicadores) => get<Recordatorios>("/indicadores/recordatorios", f),
    pendientes: (f: FiltrosIndicadores) => get<Pendientes>("/indicadores/pendientes", f),
    reagendamiento: (f: FiltrosIndicadores) => get<Reagendamiento>("/indicadores/reagendamiento", f),
    diaHora: (f: FiltrosIndicadores) => get<CeldaDiaHora[]>("/indicadores/dia-hora", f),
    cierre: () => post<Cierre>("/indicadores/cierre"),
  },
  asistente: {
    estado: () => get<AsistenteEstado>("/asistente/estado"),
    enviar: (texto: string, conversacion_id: number | null) => post<AsistenteRespuesta>("/asistente/mensajes", { texto, conversacion_id }),
  },
  resumenDia: () => get<ResumenDia>("/resumen-dia"),
  sistema: () => get<Sistema>("/sistema"),
};
