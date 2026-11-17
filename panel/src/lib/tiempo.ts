// Todo se muestra y calcula en hora de Bogotá (UTC-5, sin horario de verano), sin importar la zona del navegador.
const TZ = "America/Bogota";
const DESFASE = "-05:00";

const partes = new Intl.DateTimeFormat("en-CA", {
  timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function p(d: Date | string) {
  const o: Record<string, string> = {};
  for (const x of partes.formatToParts(typeof d === "string" ? new Date(d) : d)) o[x.type] = x.value;
  return o;
}

/** "2026-11-16" en Bogotá. */
export const fechaDe = (d: Date | string): string => { const o = p(d); return `${o.year}-${o.month}-${o.day}`; };
/** "08:00" en Bogotá. */
export const horaDe = (d: Date | string): string => { const o = p(d); return `${o.hour}:${o.minute}`; };
export const minutosDelDia = (d: Date | string): number => { const o = p(d); return Number(o.hour) * 60 + Number(o.minute); };

/** Instante absoluto de una fecha y hora de Bogotá. */
export const aIso = (fecha: string, hhmm: string): string => `${fecha}T${hhmm}:00${DESFASE}`;
export const inicioDelDia = (fecha: string): number => Date.parse(aIso(fecha, "00:00"));

const mediodia = (f: string) => new Date(`${f}T12:00:00Z`);

export function sumarDias(fecha: string, n: number): string {
  const d = mediodia(fecha);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Lunes de la semana de esa fecha. */
export function lunesDe(fecha: string): string {
  const dow = (mediodia(fecha).getUTCDay() + 6) % 7;
  return sumarDias(fecha, -dow);
}

export const diasDeSemana = (fecha: string): string[] => Array.from({ length: 7 }, (_, i) => sumarDias(lunesDe(fecha), i));

const fmt = (opts: Intl.DateTimeFormatOptions, d: Date) => new Intl.DateTimeFormat("es-CO", { timeZone: "UTC", ...opts }).format(d);
const quitarPunto = (s: string) => s.replace(/\./g, "");

export const etiquetaDia = (f: string) => quitarPunto(fmt({ weekday: "short", day: "numeric", month: "short" }, mediodia(f)));
export const nombreDia = (f: string) => fmt({ weekday: "long" }, mediodia(f));
export const diaCorto = (f: string) => quitarPunto(fmt({ weekday: "short" }, mediodia(f)));
export const numeroDia = (f: string) => fmt({ day: "numeric" }, mediodia(f));
export const fechaLarga = (f: string) => fmt({ weekday: "long", day: "numeric", month: "long", year: "numeric" }, mediodia(f));
export const mesAnio = (f: string) => fmt({ month: "long", year: "numeric" }, mediodia(f));

const largo = new Intl.DateTimeFormat("es-CO", { timeZone: TZ, weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
/** "lun 16 nov, 08:00" en Bogotá. */
export const fechaHora = (d: Date | string): string => quitarPunto(largo.format(typeof d === "string" ? new Date(d) : d)).replace(",", "");

export const hhmm = (min: number): string => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

/** Hora del sistema (la que entrega la sesión) avanzada con el reloj del navegador desde que se leyó. */
export const ahoraSistema = (horaSistema: string, leidaEn: number, ahora: number = Date.now()): Date =>
  new Date(Date.parse(horaSistema) + (ahora - leidaEn));
