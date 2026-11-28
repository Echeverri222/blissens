import type { CitaAgenda, ColorSemaforo, Estado, MotivoNoContactar, Semaforo } from "@/api/tipos";

export const MOTIVOS_NO_CONTACTAR: Record<MotivoNoContactar, string> = {
  queja: "Queja activa", cobro: "Cobro jurídico", fallecido: "Fallecido", otro: "Otro motivo",
};

// El semáforo (R5) siempre lleva texto: el color solo no basta.
export const SEMAFOROS: Record<Semaforo, { texto: string; ayuda: string; punto: string; clases: string }> = {
  verde: { texto: "Al día", ayuda: "Sin pendientes con su agenda", punto: "bg-emerald-600", clases: "bg-emerald-100 text-emerald-900" },
  amarillo: { texto: "Atención", ayuda: "Cambió tres veces la fecha o su cita próxima sigue sin confirmar", punto: "bg-amber-500", clases: "bg-amber-100 text-amber-950" },
  rojo: { texto: "Sin reagendar", ayuda: "Su última cita fue una cancelación o inasistencia y no tiene otra", punto: "bg-rose-600", clases: "bg-rose-100 text-rose-900" },
  perdido: { texto: "Perdido", ayuda: "Sin cita viva y más de 60 días sin venir", punto: "bg-zinc-500", clases: "bg-zinc-200 text-zinc-900" },
  prospecto: { texto: "Prospecto", ayuda: "Escribió desde el sitio web y aún no tiene documento", punto: "bg-sky-500", clases: "bg-sky-100 text-sky-950" },
};
export const COLORES_SEMAFORO: ColorSemaforo[] = ["verde", "amarillo", "rojo", "perdido"];

// Cada estado tiene color, texto y forma (icono) propios: nunca se comunica solo con color.
export const ESTADOS: Record<Estado, { texto: string; clases: string; borde: string; icono: string }> = {
  programada: { texto: "Programada", clases: "bg-sky-100 text-sky-900", borde: "border-sky-500", icono: "calendario" },
  confirmada: { texto: "Confirmada", clases: "bg-emerald-100 text-emerald-900", borde: "border-emerald-600", icono: "check" },
  no_confirmada: { texto: "Sin confirmar", clases: "bg-amber-100 text-amber-950", borde: "border-amber-500", icono: "pregunta" },
  atendida: { texto: "Atendida", clases: "bg-zinc-200 text-zinc-900", borde: "border-zinc-500", icono: "doble" },
  no_asistio: { texto: "No asistió", clases: "bg-rose-100 text-rose-900", borde: "border-rose-600", icono: "usuario-x" },
  cancelada: { texto: "Cancelada", clases: "bg-zinc-100 text-zinc-600 line-through", borde: "border-zinc-300", icono: "x" },
  reprogramada: { texto: "Reprogramada", clases: "bg-violet-100 text-violet-900", borde: "border-violet-500", icono: "repetir" },
};

const VIVAS: Estado[] = ["programada", "confirmada", "no_confirmada"];

/** Una cita viva cuya hora ya terminó: falta registrar si el paciente asistió. */
export const porCerrar = (c: Pick<CitaAgenda, "estado" | "fin">, ahora: Date): boolean =>
  VIVAS.includes(c.estado) && c.fin !== null && Date.parse(c.fin) <= ahora.getTime();

/** Colores de una cita ya pasada y sin cerrar: apagados (el borde conserva el color de su estado). */
export const CLASES_POR_CERRAR = "bg-zinc-100 text-zinc-700";
