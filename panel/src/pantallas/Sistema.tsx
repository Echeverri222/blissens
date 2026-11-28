import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, CircleHelp } from "lucide-react";
import { api, ApiError } from "@/api/cliente";
import { useAccion } from "@/api/consultas";
import type { Sistema as DatosSistema } from "@/api/tipos";
import { fechaDe, fechaHora, fechaLarga } from "@/lib/tiempo";
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

type Fallida = DatosSistema["tareas_fallidas"][number];

/** Junta las tareas que fallaron por lo mismo (qué no salió y por qué): una alerta con la lista de pacientes afectados. */
export function agruparFallidas(tareas: Fallida[]): { clave: string; titulo: string; causa: string; que_hacer: string; tareas: Fallida[] }[] {
  const grupos = new Map<string, Fallida[]>();
  for (const t of tareas) {
    const clave = `${t.tipo}|${t.causa}`;
    grupos.set(clave, [...(grupos.get(clave) ?? []), t]);
  }
  return [...grupos].map(([clave, ts]) => ({
    clave, tareas: ts, causa: ts[0].causa, que_hacer: ts[0].que_hacer,
    titulo: ts.length === 1 ? ts[0].titulo : `${ts.length} ${ts[0].titulo_varias}`,
  }));
}

function Alerta({ grupo }: { grupo: ReturnType<typeof agruparFallidas>[number] }) {
  return (
    <div className="rounded-[var(--radius-control)] border border-rose-300 bg-rose-50 p-4 text-rose-950">
      <p className="flex items-center gap-2 font-semibold"><AlertTriangle className="size-5 shrink-0" aria-hidden />{grupo.titulo}</p>
      <p className="mt-1 text-sm"><b>Por qué:</b> {grupo.causa}</p>
      <p className="text-sm"><b>Qué hacer:</b> {grupo.que_hacer}</p>
      <ul className="mt-2 divide-y divide-rose-200 rounded-md border border-rose-200 bg-white/70 text-sm">
        {grupo.tareas.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center gap-x-3 px-3 py-2">
            {t.paciente_id ? <Link to={`/pacientes/${t.paciente_id}`} className="font-medium underline">{t.paciente}</Link> : <span className="font-medium">Sin paciente asociado</span>}
            {t.cita_id && t.cita_inicio
              ? <Link to={`/agenda?fecha=${fechaDe(t.cita_inicio)}&cita=${t.cita_id}`} className="text-tinta-suave underline">Cita del {fechaHora(t.cita_inicio)}</Link>
              : <span className="text-tinta-suave">Debía salir el {fechaHora(t.ejecutar_en)}</span>}
          </li>))}
      </ul>
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-rose-900">Detalle técnico (para quien administra el sistema)</summary>
        <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-white/70 p-2">{grupo.tareas[0].error ?? "Sin detalle"}</pre>
      </details>
    </div>
  );
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
          const detenido = s.tareas_atrasadas > 0;
          const estadoDelCierre = estadoCierre(s.ultimo_cierre, hoy);
          const mensajes: { estado: Estado; titulo: string; detalle: string } = detenido
            ? { estado: "mal", titulo: "El envío de mensajes está detenido", detalle: `${s.tareas_atrasadas} ${s.tareas_atrasadas === 1 ? "mensaje debió salir" : "mensajes debieron salir"} hace más de 15 minutos y no ha salido. Avisa a quien administra el sistema y, mientras tanto, confirma por teléfono las citas de hoy y mañana.` }
            : fallidas > 0
              ? { estado: "mal", titulo: `${fallidas} ${fallidas === 1 ? "aviso no salió" : "avisos no salieron"}`, detalle: "Abajo está a quién llamar y por qué." }
              : { estado: "bien", titulo: "Los mensajes automáticos funcionan", detalle: "Recordatorios, seguimientos y correos salen cuando les toca." };
          return (<>
            <section aria-label="Estado" className="grid gap-3 md:grid-cols-2">
              <Semaforo estado={mensajes.estado} titulo={mensajes.titulo}>{mensajes.detalle}</Semaforo>
              <Semaforo estado={estadoDelCierre.estado} titulo={estadoDelCierre.titulo}>{estadoDelCierre.detalle}</Semaforo>
            </section>
            {fallidas > 0 && (
              <section aria-label="Alertas" className="space-y-3">
                <h2 className="text-sm font-semibold">Qué no salió y a quién llamar</h2>
                {agruparFallidas(s.tareas_fallidas).map((g) => <Alerta key={g.clave} grupo={g} />)}
              </section>
            )}
            <section aria-label="Cierre diario" className="space-y-2">
              <Tarjeta className="flex flex-wrap items-center gap-3 p-4">
                <p className="mr-auto text-sm">Último cierre diario: <b>{s.ultimo_cierre ?? "nunca"}</b></p>
                <Confirmar variante="secundario" pequeno deshabilitado={cierre.isPending} etiqueta="Ejecutar cierre ahora" pregunta="Se recalculan los indicadores de los días pendientes. Puede tardar unos segundos." alConfirmar={() => cierre.mutate(undefined)} />
              </Tarjeta>
              {cierre.error instanceof ApiError && <Aviso>{cierre.error.mensaje}</Aviso>}
            </section>
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
