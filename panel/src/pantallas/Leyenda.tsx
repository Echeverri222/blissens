import { useEffect, useRef, useState } from "react";
import { CircleHelp } from "lucide-react";
import type { Estado } from "@/api/tipos";
import { ESTADOS } from "@/lib/estados";
import { cn } from "@/lib/utils";
import { Boton, IconoEstado } from "@/ui/controles";

/** Qué significa cada color de la agenda: los mismos estados, con su color, su icono y su texto. */
export function Leyenda() {
  const [abierta, setAbierta] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierta) return;
    const fuera = (e: MouseEvent) => { if (!caja.current?.contains(e.target as Node)) setAbierta(false); };
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") setAbierta(false); };
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", tecla);
    return () => { document.removeEventListener("mousedown", fuera); document.removeEventListener("keydown", tecla); };
  }, [abierta]);
  return (
    <div ref={caja} className="relative">
      <Boton variante="secundario" pequeno aria-expanded={abierta} aria-haspopup="true" onClick={() => setAbierta((v) => !v)}>
        <CircleHelp className="size-4" aria-hidden /> ¿Qué significan los colores?
      </Boton>
      {abierta && (
        <div role="group" aria-label="Significado de los colores" className="absolute left-0 top-full z-30 mt-1 w-64 space-y-1.5 rounded-xl border border-linea bg-papel p-3 shadow-lg">
          {(Object.keys(ESTADOS) as Estado[]).map((e) => (
            <p key={e} className="flex items-center gap-2 text-sm">
              <span className={cn("inline-flex size-6 items-center justify-center rounded-md border", ESTADOS[e].clases, ESTADOS[e].borde)}><IconoEstado estado={e} /></span>
              {ESTADOS[e].texto}
            </p>
          ))}
          <p className="flex items-center gap-2 border-t border-linea pt-1.5 text-sm">
            <span className="inline-flex size-6 items-center justify-center rounded-md border border-zinc-300 bg-zinc-100 text-zinc-700" />
            Pasada y por cerrar
          </p>
        </div>
      )}
    </div>
  );
}
