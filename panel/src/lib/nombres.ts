/** Nombre y primer apellido de «nombres apellidos» (sin separar en la base): con 4 o más palabras, la 1.ª y la 3.ª. */
export function nombreCorto(completo: string): string {
  const t = completo.trim().split(/\s+/);
  if (t.length <= 2) return t.join(" ");
  return t.length === 3 ? `${t[0]} ${t[1]}` : `${t[0]} ${t[2]}`;
}

/** «Dra. Ana Pérez» → «Dra. Pérez». */
export function profesionalCorto(nombre: string): string {
  const t = nombre.trim().split(/\s+/);
  return t.length <= 2 ? nombre.trim() : /\.$/.test(t[0]) ? `${t[0]} ${t[t.length - 1]}` : t[t.length - 1];
}
