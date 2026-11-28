/** Solicitudes que llegan del sitio público: `origen = "sitio"`, con sus datos en columnas propias. */
import type { Contacto } from "@/api/tipos";

const INTERESES = { evaluacion_virtual: "Evaluación virtual", experiencia: "Experiencia", contacto: "Contacto" } as const;
const PAQUETES: Record<string, string> = { premium: "Premium (hotel)", standard: "Standard (Airbnb)", essential: "Essential (transporte)" };

export function esSolicitudWeb(r: Pick<Contacto, "origen">): boolean {
  return r.origen === "sitio";
}

/** «Evaluación virtual», «Experiencia · Premium (hotel)»… */
export function tipoDeSolicitud(r: Pick<Contacto, "interes" | "paquete">): string {
  const tipo = r.interes ? INTERESES[r.interes] : "Contacto";
  return r.paquete ? `${tipo} · ${PAQUETES[r.paquete] ?? r.paquete}` : tipo;
}

/** Dígitos para `https://wa.me/`; null si no parece un teléfono. */
export function digitosWhatsApp(celular: string): string | null {
  const d = celular.replace(/\D/g, "");
  return d.length >= 7 ? d : null;
}

/** «1,2 MB», «340 KB». */
export function tamanoLegible(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Nombres y apellidos para crear la ficha: la última palabra va a apellidos si hay más de una. */
export function separarNombre(nombre: string | null | undefined): { nombres: string; apellidos: string } {
  const partes = (nombre ?? "").trim().split(/\s+/).filter(Boolean);
  if (partes.length <= 1) return { nombres: partes[0] ?? "", apellidos: "" };
  if (partes.length === 2) return { nombres: partes[0], apellidos: partes[1] };
  return { nombres: partes.slice(0, -2).join(" "), apellidos: partes.slice(-2).join(" ") };
}
