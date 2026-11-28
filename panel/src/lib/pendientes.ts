import type { ConteoBandejas } from "@/api/tipos";

/** Bandejas que necesitan una llamada (o un clic de recepción) hoy. Las informativas (en riesgo, cupos libres) y los trámites (por cerrar) no cuentan. */
export const LLAMADAS: (keyof ConteoBandejas)[] = ["seguimientos", "contactos", "sin_interpretar", "no_confirmadas", "dados_de_baja", "celulares_por_revisar", "planes"];

/** Una sola cuenta de «Llamadas»: la usan el contador del menú y la pestaña «Qué hacer hoy». */
export const totalLlamadas = (c: ConteoBandejas): number => LLAMADAS.reduce((n, k) => n + c[k], 0);
