// Todo se muestra y calcula en la zona horaria del negocio activo (Bogotá por defecto), sin importar la del navegador.
let TZ = "America/Bogota";

const formato = (zona: string) => new Intl.DateTimeFormat("en-CA", {
  timeZone: zona, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
let partes = formato(TZ);

/** La sesión fija la zona del negocio activo. */
export function usarZona(zona: string) {
  if (zona === TZ) return;
  TZ = zona;
  partes = formato(zona);
}

function p(d: Date | string) {
  const o: Record<string, string> = {};
  for (const x of partes.formatToParts(typeof d === "string" ? new Date(d) : d)) o[x.type] = x.value;
  return o;
}

/** Desfase de la zona en un instante, en minutos (positivo al este de UTC). */
function desfaseMin(ms: number): number {
  const t = new Intl.DateTimeFormat("en", { timeZone: TZ, timeZoneName: "longOffset" }).formatToParts(new Date(ms))
    .find((x) => x.type === "timeZoneName")?.value ?? "GMT";
  const m = /GMT([+-])(\d{2}):?(\d{2})?/.exec(t);
  return m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3] ?? 0)) : 0;
}

/** "2026-11-16" en la zona del negocio. */
export const fechaDe = (d: Date | string): string => { const o = p(d); return `${o.year}-${o.month}-${o.day}`; };
/** "08:00" en la zona del negocio. */
export const horaDe = (d: Date | string): string => { const o = p(d); return `${o.hour}:${o.minute}`; };
export const minutosDelDia = (d: Date | string): number => { const o = p(d); return Number(o.hour) * 60 + Number(o.minute); };

/** Instante absoluto (ISO con desfase) de una fecha y hora de la zona del negocio. */
export const aIso = (fecha: string, hhmm: string): string => {
  const ref = Date.parse(`${fecha}T${hhmm}:00Z`);
  const d = desfaseMin(ref - desfaseMin(ref) * 60_000);
  const signo = d < 0 ? "-" : "+";
  const a = Math.abs(d);
  return `${fecha}T${hhmm}:00${signo}${String(Math.floor(a / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}`;
};
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
