// Pesos colombianos sin decimales: "$ 80.000".
const COP = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
export const pesos = (v: number | null | undefined): string => (v === null || v === undefined ? "—" : COP.format(v));
