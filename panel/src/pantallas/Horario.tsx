import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/cliente";
import { nombreDia } from "@/lib/tiempo";
import { useSesion } from "@/sesion/Sesion";
import { Tarjeta } from "@/ui/controles";
import { Consulta, Vacio } from "@/ui/vistas";
import { FormularioBloqueo, ListaBloqueos } from "./Bloqueos";

const LUNES = "2026-11-16"; // solo para nombrar los días de la semana (0 = lunes)
const nombreDeDia = (n: number) => nombreDia(new Date(Date.parse(`${LUNES}T12:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10));

export function MiHorario() {
  const { sesion } = useSesion();
  const id = sesion.profesional_id!;
  const q = useQuery({ queryKey: ["horario", id], queryFn: () => api.agenda.horario(id) });
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <h1 className="text-xl font-semibold">Mi horario</h1>
      <section aria-label="Horario semanal" className="space-y-2">
        <h2 className="text-sm font-semibold">Horario semanal de atención</h2>
        <Tarjeta className="p-4">
          <Consulta q={q}>
            {(h) => h.franjas.length === 0 ? <Vacio titulo="Sin horario configurado">Pide a recepción que configure tu horario de atención.</Vacio> : (
              <dl className="grid grid-cols-[8rem_1fr] gap-y-1.5 text-sm">
                {[0, 1, 2, 3, 4, 5, 6].map((d) => {
                  const f = h.franjas.filter((x) => x.dia_semana === d);
                  return (
                    <div key={d} className="contents">
                      <dt className="capitalize text-tinta-suave">{nombreDeDia(d)}</dt>
                      <dd>{f.length ? f.map((x) => `${x.desde.slice(0, 5)} – ${x.hasta.slice(0, 5)}`).join(" · ") : <span className="text-tinta-suave">No atiendes</span>}</dd>
                    </div>
                  );
                })}
              </dl>
            )}
          </Consulta>
        </Tarjeta>
      </section>
      <div className="grid gap-6 md:grid-cols-[1fr_20rem]">
        <section aria-label="Mis bloqueos" className="space-y-2">
          <h2 className="text-sm font-semibold">Mis bloqueos (próximas seis semanas)</h2>
          <ListaBloqueos />
        </section>
        <section aria-label="Nuevo bloqueo" className="space-y-2">
          <h2 className="text-sm font-semibold">Bloquear tiempo</h2>
          <Tarjeta className="p-4"><FormularioBloqueo profesionalId={id} /></Tarjeta>
        </section>
      </div>
    </div>
  );
}
