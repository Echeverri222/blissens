import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/cliente";
import { fechaHora } from "@/lib/tiempo";
import { Tarjeta } from "@/ui/controles";
import { Aviso, Consulta } from "@/ui/vistas";

export function Sistema() {
  const q = useQuery({ queryKey: ["sistema"], queryFn: api.sistema });
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-xl font-semibold">Sistema</h1>
      <Consulta q={q}>
        {(s) => (<>
          <section aria-label="Tareas" className="space-y-2">
            <h2 className="text-sm font-semibold">Tareas fallidas</h2>
            {s.tareas_fallidas.length === 0 ? <Aviso tipo="info">No hay tareas fallidas.</Aviso> : (<>
              <Aviso>{s.tareas_fallidas.length} tareas fallidas: atiende a mano lo que el sistema no pudo hacer.</Aviso>
              <Tarjeta className="divide-y divide-linea">{s.tareas_fallidas.map((t) => (
                <div key={t.id} className="px-4 py-2.5 text-sm"><b>{t.tipo.replace(/_/g, " ")}</b> · {fechaHora(t.ejecutar_en)} · {t.intentos} intentos<p className="text-tinta-suave">{t.error ?? "Sin detalle"}</p></div>))}</Tarjeta></>)}
            <p className="text-sm">Tareas pendientes: <b>{s.tareas_pendientes}</b> · Último cierre diario: <b>{s.ultimo_cierre ?? "nunca"}</b></p>
          </section>
          <section aria-label="Configuración" className="space-y-2">
            <h2 className="text-sm font-semibold">Configuración vigente (solo lectura)</h2>
            <Tarjeta className="divide-y divide-linea">{Object.entries(s.configuracion).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 px-4 py-2 text-sm"><span className="text-tinta-suave">{k}</span><span className="font-medium">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span></div>))}</Tarjeta>
          </section>
        </>)}
      </Consulta>
    </div>
  );
}
