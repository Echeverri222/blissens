// Distribución de la rejilla de calendario: función pura, sin librería de calendario (PRD #3 §6.4).
import type { Agenda, Bloqueo, CitaAgenda, Cupo } from "@/api/tipos";
import { inicioDelDia } from "./tiempo";

/** Tramo en minutos desde las 00:00 de Bogotá del día de la columna. */
export interface Tramo { desde: number; hasta: number }
export interface TramoBloqueo extends Tramo { motivos: string[]; ids: number[] }
export interface CajaCita extends Tramo { cita: CitaAgenda }
export interface CajaCupo extends Tramo { cupo: Cupo }
export interface ColumnaDia {
  fecha: string;
  profesionalId: number | null;
  franjas: Tramo[];
  bloqueos: TramoBloqueo[];
  citas: CajaCita[];
  cupos: CajaCupo[];
  /** Las canceladas no ocupan la rejilla: se cruzarían con la cita que tomó su lugar. */
  canceladas: CitaAgenda[];
  /** Citas importadas sin hora. */
  sinHora: CitaAgenda[];
}

const DIA = 24 * 60;

function recortar(inicio: string, fin: string, fecha: string): Tramo | null {
  const base = inicioDelDia(fecha);
  const desde = Math.max(0, Math.round((Date.parse(inicio) - base) / 60000));
  const hasta = Math.min(DIA, Math.round((Date.parse(fin) - base) / 60000));
  return hasta > desde ? { desde, hasta } : null;
}

/** Une tramos que se tocan o se cruzan: dos bloqueos cruzados se dibujan como una sola zona. */
export function unir<T extends Tramo>(tramos: T[]): Tramo[] {
  const orden = [...tramos].sort((a, b) => a.desde - b.desde);
  const res: Tramo[] = [];
  for (const t of orden) {
    const ult = res[res.length - 1];
    if (ult && t.desde <= ult.hasta) ult.hasta = Math.max(ult.hasta, t.hasta);
    else res.push({ desde: t.desde, hasta: t.hasta });
  }
  return res;
}

function unirBloqueos(bloqueos: { tramo: Tramo; b: Bloqueo }[]): TramoBloqueo[] {
  const orden = [...bloqueos].sort((a, b) => a.tramo.desde - b.tramo.desde);
  const res: TramoBloqueo[] = [];
  for (const { tramo, b } of orden) {
    const ult = res[res.length - 1];
    if (ult && tramo.desde <= ult.hasta) {
      ult.hasta = Math.max(ult.hasta, tramo.hasta);
      if (b.motivo && !ult.motivos.includes(b.motivo)) ult.motivos.push(b.motivo);
      ult.ids.push(b.id);
    } else res.push({ ...tramo, motivos: b.motivo ? [b.motivo] : [], ids: [b.id] });
  }
  return res;
}

export function columnaDia(fecha: string, profesionalId: number | null, a: Agenda): ColumnaDia {
  const delPro = <T extends { profesional_id: number }>(x: T) => profesionalId === null || x.profesional_id === profesionalId;
  const franjas = a.franjas.filter((f) => delPro(f) && f.fecha === fecha)
    .map((f) => recortar(f.inicio, f.fin, fecha)).filter((t): t is Tramo => t !== null);
  const bloqueos = a.bloqueos.filter(delPro).flatMap((b) => {
    const t = recortar(b.inicio, b.fin, fecha);
    return t ? [{ tramo: t, b }] : [];
  });
  const citas: CajaCita[] = [];
  const canceladas: CitaAgenda[] = [];
  for (const c of a.citas.filter(delPro)) {
    if (!c.inicio || !c.fin) continue;
    const t = recortar(c.inicio, c.fin, fecha);
    if (!t) continue;
    if (c.estado === "cancelada") canceladas.push(c);
    else citas.push({ ...t, cita: c });
  }
  citas.sort((x, y) => x.desde - y.desde);
  const cupos = a.cupos_liberados.filter(delPro).flatMap((cupo) => {
    const t = recortar(cupo.inicio, cupo.fin, fecha);
    return t ? [{ ...t, cupo }] : [];
  });
  const sinHora = a.citas_sin_hora.filter((c) => delPro(c) && c.dia === fecha);
  return { fecha, profesionalId, franjas: unir(franjas), bloqueos: unirBloqueos(bloqueos), citas, cupos, canceladas, sinHora };
}

/** Horas que muestra la rejilla: lo que cubren franjas, citas y bloqueos, redondeado a la hora; mínimo 7:00 a 19:00. */
export function rangoVisible(cols: ColumnaDia[], base: Tramo = { desde: 7 * 60, hasta: 19 * 60 }): Tramo {
  let desde = base.desde;
  let hasta = base.hasta;
  for (const c of cols) {
    for (const t of [...c.franjas, ...c.citas, ...c.bloqueos.filter((b) => b.hasta - b.desde < DIA)]) {
      desde = Math.min(desde, t.desde);
      hasta = Math.max(hasta, t.hasta);
    }
  }
  return { desde: Math.floor(desde / 60) * 60, hasta: Math.min(DIA, Math.ceil(hasta / 60) * 60) };
}

/** Posición vertical (en %) de una caja dentro del rango visible, recortada a sus bordes. */
export function posicion(t: Tramo, visible: Tramo): { arriba: number; alto: number } | null {
  const d = Math.max(t.desde, visible.desde);
  const h = Math.min(t.hasta, visible.hasta);
  if (h <= d) return null;
  const total = visible.hasta - visible.desde;
  return { arriba: ((d - visible.desde) / total) * 100, alto: ((h - d) / total) * 100 };
}
