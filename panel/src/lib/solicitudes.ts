/** Solicitudes que llegan del sitio público: se guardan en `solicitud_contacto` con documento «—» y los datos en `nota`. */
export type SolicitudWeb = { tipo: string; paquete?: string; idioma?: string; nombre?: string; correo?: string; pais?: string; mensaje?: string };

const PREFIJO = "Sitio web ·";

export function esSolicitudWeb(r: { documento: string; nota: string }): boolean {
  return r.documento.trim() === "—" || r.nota.startsWith(PREFIJO);
}

export function leerSolicitudWeb(nota: string): SolicitudWeb {
  // El mensaje va al final y puede contener « | »: se corta primero.
  const m = nota.indexOf(" | Mensaje: ");
  const cuerpo = m >= 0 ? nota.slice(0, m) : nota;
  const mensaje = m >= 0 ? nota.slice(m + " | Mensaje: ".length) : undefined;
  const [cabecera, ...campos] = cuerpo.split(" | ");
  const partes = cabecera.replace(PREFIJO, "").split(" · ").map((p) => p.trim()).filter(Boolean);
  const idioma = partes.find((p) => p.startsWith("idioma "))?.slice(7);
  const sueltas = partes.filter((p) => !p.startsWith("idioma "));
  const s: SolicitudWeb = { tipo: sueltas[0] ?? "Contacto", paquete: sueltas[1], idioma, mensaje };
  for (const c of campos) {
    if (c.startsWith("Nombre: ")) s.nombre = c.slice(8);
    else if (c.startsWith("Correo: ")) s.correo = c.slice(8);
    else if (c.startsWith("País: ")) s.pais = c.slice(6);
  }
  return s;
}

/** Dígitos para `https://wa.me/`; null si no parece un teléfono. */
export function digitosWhatsApp(celular: string): string | null {
  const d = celular.replace(/\D/g, "");
  return d.length >= 7 ? d : null;
}
