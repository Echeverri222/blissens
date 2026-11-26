import { Link } from "react-router-dom";
import { useResumenDia } from "@/api/consultas";
import { cn } from "@/lib/utils";

const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

/** Franja de la auxiliar sobre la agenda: cuántas citas hay hoy y qué necesita atención. En celular es una sola línea que se desliza. */
export function ResumenDia() {
  const q = useResumenDia();
  const r = q.data;
  if (!r) return null;
  const contadores = [
    { a: "/agenda", texto: plural(r.citas_hoy, "cita hoy", "citas hoy"), atencion: false },
    { a: "/bandejas?b=no-confirmadas", texto: `${r.sin_confirmar} sin confirmar hoy y mañana`, atencion: r.sin_confirmar > 0 },
    ...(r.mensajes > 0 ? [{ a: "/bandejas?b=sin-interpretar", texto: plural(r.mensajes, "mensaje por responder", "mensajes por responder"), atencion: true }] : []),
    { a: "/bandejas?b=sin-desenlace", texto: `${r.por_cerrar} por cerrar`, atencion: false, suave: true },
  ];
  return (
    <nav aria-label="Resumen del día">
      <ul className="flex gap-2 overflow-x-auto pb-1 md:flex-wrap md:overflow-visible">
        {contadores.map((c) => (
          <li key={c.a} className="shrink-0">
            <Link to={c.a} className={cn("inline-block whitespace-nowrap rounded-full border px-3 py-1.5 text-sm font-medium",
              c.atencion ? "border-amber-400 bg-amber-100 text-amber-950" : "suave" in c ? "border-linea bg-zinc-50 text-tinta-suave" : "border-linea bg-papel")}>
              {c.texto}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
