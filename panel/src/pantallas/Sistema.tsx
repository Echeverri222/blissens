import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleHelp } from "lucide-react";
import { api, ApiError } from "@/api/cliente";
import { useAccion } from "@/api/consultas";
import { fechaHora, fechaLarga } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { useSesion } from "@/sesion/Sesion";
import { Confirmar, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta } from "@/ui/vistas";

type Estado = "bien" | "atencion" | "mal";
const ESTILO: Record<Estado, { clases: string; icono: typeof CheckCircle2 }> = {
  bien: { clases: "border-emerald-300 bg-emerald-50 text-emerald-950", icono: CheckCircle2 },
  atencion: { clases: "border-amber-300 bg-amber-50 text-amber-950", icono: CircleHelp },
  mal: { clases: "border-rose-300 bg-rose-50 text-rose-950", icono: AlertTriangle },
};

function Semaforo({ estado, titulo, children }: { estado: Estado; titulo: string; children: ReactNode }) {
  const { clases, icono: Icono } = ESTILO[estado];
  return (
    <div className={cn("rounded-[var(--radius-control)] border p-4", clases)}>
      <p className="flex items-center gap-2 font-semibold"><Icono className="size-5 shrink-0" aria-hidden />{titulo}</p>
      <p className="mt-1 text-sm">{children}</p>
    </div>
  );
}

const MS_DIA = 86_400_000;
/** Días enteros entre dos fechas AAAA-MM-DD (0 = el mismo día). */
const diasEntre = (desde: string, hasta: string) => Math.round((Date.parse(hasta) - Date.parse(desde)) / MS_DIA);

/** Cómo está el cierre diario respecto a hoy: bien si corrió hoy o ayer; si no, hay que avisar. */
export function estadoCierre(ultimo: string | null, hoy: string): { estado: Estado; titulo: string; detalle: string } {
  if (!ultimo) return { estado: "mal", titulo: "Los indicadores nunca se han actualizado", detalle: "El cierre diario no ha corrido todavía. Avisa a quien administra el sistema." };
  const f = ultimo.slice(0, 10);
  const atraso = diasEntre(f, hoy);
  if (atraso <= 1) return { estado: "bien", titulo: "Indicadores al día", detalle: `Último cierre: ${fechaLarga(f)}.` };
  return { estado: "atencion", titulo: `Indicadores atrasados ${atraso} días`, detalle: `Último cierre: ${fechaLarga(f)}. Si no se actualizan solos, avisa a quien administra el sistema.` };
}

export function Sistema() {
  const { hoy } = useSesion();
  const q = useQuery({ queryKey: ["sistema"], queryFn: api.sistema });
  const cierre = useAccion(api.indicadores.cierre, { ok: (r) => `Cierre ejecutado (${r.dias} días)` });
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-xl font-semibold">Sistema</h1>
      <Consulta q={q}>
        {(s) => {
          const fallidas = s.tareas_fallidas.length;
          const estadoDelCierre = estadoCierre(s.ultimo_cierre, hoy);
          return (<>
            <section aria-label="Estado" className="grid gap-3 md:grid-cols-2">
              <Semaforo estado={fallidas === 0 ? "bien" : "mal"} titulo={fallidas === 0 ? "Los mensajes automáticos funcionan" : `${fallidas} ${fallidas === 1 ? "tarea falló" : "tareas fallaron"}`}>
                {fallidas === 0
                  ? "Recordatorios, seguimientos y correos salen cuando les toca."
                  : "El sistema no pudo enviar algo. Revisa la lista de abajo y atiende a esos pacientes por teléfono."}
              </Semaforo>
              <Semaforo estado={estadoDelCierre.estado} titulo={estadoDelCierre.titulo}>{estadoDelCierre.detalle}</Semaforo>
            </section>
            <section aria-label="Cierre diario" className="space-y-2">
              <Tarjeta className="flex flex-wrap items-center gap-3 p-4">
                <p className="mr-auto text-sm">Último cierre diario: <b>{s.ultimo_cierre ?? "nunca"}</b></p>
                <Confirmar variante="secundario" pequeno deshabilitado={cierre.isPending} etiqueta="Ejecutar cierre ahora" pregunta="Se recalculan los indicadores de los días pendientes. Puede tardar unos segundos." alConfirmar={() => cierre.mutate(undefined)} />
              </Tarjeta>
              {cierre.error instanceof ApiError && <Aviso>{cierre.error.mensaje}</Aviso>}
            </section>
            {fallidas > 0 && (
              <section aria-label="Tareas fallidas" className="space-y-2">
                <h2 className="text-sm font-semibold">Qué no se pudo hacer</h2>
                <Tarjeta className="divide-y divide-linea">{s.tareas_fallidas.map((t) => (
                  <div key={t.id} className="px-4 py-2.5 text-sm"><b>{t.tipo.replace(/_/g, " ")}</b> · {fechaHora(t.ejecutar_en)} · {t.intentos} intentos<p className="text-tinta-suave">{t.error ?? "Sin detalle"}</p></div>))}</Tarjeta>
              </section>
            )}
            <section aria-label="Qué significa" className="space-y-1 text-sm text-tinta-suave">
              <p><b className="text-tinta">Tareas pendientes ({s.tareas_pendientes}):</b> mensajes y avisos programados que el sistema enviará cuando llegue su hora. Un número alto es normal; lo que importa son las fallidas.</p>
              <p><b className="text-tinta">Cierre diario:</b> una vez al día el sistema guarda los indicadores del día anterior y detecta pacientes en riesgo.</p>
            </section>
            <details className="rounded-[var(--radius-control)] border border-linea bg-papel p-4">
              <summary className="cursor-pointer text-sm font-semibold">Avanzado: valores del sistema (solo lectura)</summary>
              <p className="mt-2 text-sm text-tinta-suave">Para quien administra el sistema. Estos valores no se cambian desde aquí.</p>
              <div className="mt-2 divide-y divide-linea">{Object.entries(s.configuracion).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 py-2 text-sm"><span className="text-tinta-suave">{k}</span><span className="font-medium">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span></div>))}</div>
            </details>
          </>);
        }}
      </Consulta>
    </div>
  );
}
