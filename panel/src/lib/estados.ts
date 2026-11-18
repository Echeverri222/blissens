import type { Estado } from "@/api/tipos";

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
