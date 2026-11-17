import { useEffect } from "react";
import { useEspacios } from "@/api/consultas";
import { etiquetaDia, fechaDe, horaDe, nombreDia } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { Consulta, Vacio } from "@/ui/vistas";

/** Espacios disponibles que entrega la API, agrupados por día. El panel no decide qué está libre. */
export function SelectorEspacios({ profesionalId, servicioId, valor, alCambiar }: {
  profesionalId: number | null; servicioId: number | null; valor: string | null; alCambiar: (inicio: string | null) => void;
}) {
  const q = useEspacios(profesionalId, servicioId);
  const horas = q.data?.dias.flatMap((d) => d.horas) ?? [];
  const sigue = valor === null || horas.includes(valor);
  useEffect(() => { if (q.data && !sigue) alCambiar(null); }, [q.data, sigue, alCambiar]);
  if (profesionalId === null || servicioId === null) return <p className="text-sm text-tinta-suave">Elige servicio y profesional para ver los espacios.</p>;
  return (
    <Consulta q={q}>
      {(d) => d.dias.length === 0
        ? <Vacio titulo="No hay espacios disponibles">Este profesional no tiene espacios libres para el servicio en los próximos días.</Vacio>
        : (
          <div className="max-h-80 space-y-3 overflow-y-auto pr-1" role="group" aria-label="Espacios disponibles">
            {d.dias.map((dia) => (
              <div key={dia.fecha}>
                <p className="mb-1 text-sm font-medium capitalize">{nombreDia(dia.fecha)} <span className="font-normal text-tinta-suave">{etiquetaDia(dia.fecha)}</span></p>
                <div className="flex flex-wrap gap-1.5">
                  {dia.horas.map((h) => (
                    <button key={h} type="button" aria-pressed={valor === h} onClick={() => alCambiar(h)}
                      aria-label={`${etiquetaDia(fechaDe(h))} ${horaDe(h)}`}
                      className={cn("rounded-lg border px-2.5 py-1 text-sm", valor === h ? "border-marca bg-marca text-white" : "border-linea bg-papel hover:bg-zinc-50")}>
                      {horaDe(h)}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
    </Consulta>
  );
}
