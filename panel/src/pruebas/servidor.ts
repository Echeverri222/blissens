// API simulada a nivel de red, con respuestas tipadas con los tipos generados desde el esquema.
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { Agenda, CitaAgenda, CitaDetalle, Sesion } from "@/api/tipos";

const BLISSENS = { id: 1, nombre_corto: "blissens", nombre: "Blissens Odontología", zona_horaria: "America/Bogota" };
const NEG = { negocio: BLISSENS, negocios: [BLISSENS] };
export const AUX: Sesion = { usuario: "recepcion", nombre: "Recepción", rol: "auxiliar", profesional_id: null, profesional: null, hora_sistema: "2026-11-16T10:30:00-05:00", modo_demo: true, ...NEG, administrador: false, debe_cambiar_clave: false, simulador: true };
export const ESP: Sesion = { usuario: "esp1", nombre: "Dra. Uno", rol: "especialista", profesional_id: 1, profesional: "Dra. Uno", hora_sistema: "2026-11-16T10:30:00-05:00", modo_demo: false, ...NEG, administrador: false, debe_cambiar_clave: false, simulador: true };

export const cita = (o: Partial<CitaAgenda> = {}): CitaAgenda => ({
  id: 10, estado: "programada", dia: "2026-11-16", inicio: "2026-11-16T09:00:00-05:00", fin: "2026-11-16T10:00:00-05:00", profesional_id: 1, profesional: "Dra. Uno",
  servicio_id: 1, servicio: "Valoración", paciente_id: 7, paciente: "Ana Pérez", celular: "+573001112233", acciones: ["desenlace"], ...o,
});

export const agenda = (citas: CitaAgenda[] = [cita()], o: Partial<Agenda> = {}): Agenda => ({
  desde: "2026-11-16", hasta: "2026-11-16", profesional_id: null, citas, citas_sin_hora: [], bloqueos: [], cupos_liberados: [],
  franjas: [{ profesional_id: 1, fecha: "2026-11-16", inicio: "2026-11-16T08:00:00-05:00", fin: "2026-11-16T17:00:00-05:00" }], ...o,
});

export const detalle = (o: Partial<CitaDetalle> = {}): CitaDetalle => ({
  id: 10, estado: "programada", dia: "2026-11-16", inicio: "2026-11-16T09:00:00-05:00", fin: "2026-11-16T10:00:00-05:00", profesional_id: 1, profesional: "Dra. Uno",
  servicio_id: 1, servicio: "Valoración", paciente: { id: 7, nombre: "Ana Pérez", celular: "+573001112233" }, acciones: ["desenlace"],
  historial: [{ id: 1, estado_anterior: null, estado_nuevo: "programada", actor: "sistema", usuario: null, detalle: "", momento: "2026-11-15T10:00:00-05:00", revierte_id: null, revertido: false, reversible: false }], ...o,
});

/** Peticiones que modifican, en orden, para que las pruebas verifiquen lo que se envió. */
export const enviadas: { metodo: string; ruta: string; cuerpo: unknown }[] = [];
export const registrar = async (request: Request) => {
  const u = new URL(request.url);
  enviadas.push({ metodo: request.method, ruta: u.pathname + u.search, cuerpo: request.method === "GET" ? undefined : await request.json().catch(() => undefined) });
};

export const error = (status: number, codigo: string, mensaje: string, extra: object = {}) => HttpResponse.json({ codigo, mensaje, ...extra }, { status });

const base = "*/api/v1";
export const manejadores = (sesion: Sesion | null = AUX) => [
  http.get(`${base}/sesion`, () => (sesion ? HttpResponse.json(sesion) : error(401, "no_autenticado", "Inicia sesión para continuar."))),
  http.get(`${base}/profesionales`, () => HttpResponse.json([{ id: 1, nombre: "Dra. Uno", especialidad: "General" }, { id: 2, nombre: "Dr. Dos", especialidad: "General" }])),
  http.get(`${base}/servicios`, () => HttpResponse.json([{ id: 1, nombre: "Valoración", duracion_min: 60, autoagendable: true }])),
  http.get(`${base}/motivos-cancelacion`, () => HttpResponse.json([{ id: 3, etiqueta: "Calamidad" }])),
  http.get(`${base}/agenda`, () => HttpResponse.json(agenda())),
  http.get(`${base}/citas/:id`, () => HttpResponse.json(detalle())),
  http.get(`${base}/bandejas`, () => HttpResponse.json({ no_confirmadas: 2, seguimientos: 1, en_riesgo: 0, cupos_libres: 0, sin_desenlace: 0, sin_interpretar: 0, contactos: 0, dados_de_baja: 0 })),
  http.get(`${base}/resumen-dia`, () => HttpResponse.json({ citas_hoy: 1, sin_confirmar: 2, mensajes: 0, por_cerrar: 0 })),
  // Listas de las bandejas, vacías por defecto: cada prueba reemplaza la que necesita.
  ...["no-confirmadas", "seguimientos", "en-riesgo", "cupos-libres", "sin-desenlace", "sin-interpretar", "contactos", "dados-de-baja"].map((r) => http.get(`${base}/bandejas/${r}`, () => HttpResponse.json([]))),
];

export const servidor = setupServer(...manejadores());
