import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Plus, ShieldBan } from "lucide-react";
import { useAgenda, useProfesionales } from "@/api/consultas";
import type { Profesional } from "@/api/tipos";
import { diasDeSemana, diaCorto, etiquetaDia, fechaLarga, lunesDe, numeroDia, sumarDias } from "@/lib/tiempo";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { cn } from "@/lib/utils";
import { useSesion } from "@/sesion/Sesion";
import { Boton, Entrada, Hoja, Seleccion } from "@/ui/controles";
import { Cargando, ErrorVista } from "@/ui/vistas";
import { PanelBloqueos } from "./Bloqueos";
import { HojaCita } from "./HojaCita";
import { Leyenda } from "./Leyenda";
import { calcularColumnas, ListaDelDia, ListasAparte, Rejilla, SemanaTodos, type Col } from "./Rejilla";
import { ResumenDia } from "./ResumenDia";

const FECHA = /^\d{4}-\d{2}-\d{2}$/;

export function Agenda() {
  const { sesion, hoy, ahora } = useSesion();
  const [params, setParams] = useSearchParams();
  const movil = useMediaQuery("(max-width: 767px)");
  const esp = sesion.rol === "especialista";
  const [bloquear, setBloquear] = useState(false);
  const profs = useProfesionales();

  const fecha = FECHA.test(params.get("fecha") ?? "") ? params.get("fecha")! : hoy;
  const vista = params.get("vista") === "semana" ? "semana" : "dia";
  const citaAbierta = Number(params.get("cita")) || null;
  const activos = useMemo<Profesional[]>(() => profs.data ?? [], [profs.data]);
  const proParam = Number(params.get("pro")) || null;
  // La auxiliar ve a todos los profesionales salvo que elija uno; el especialista siempre el suyo.
  const proFiltro = esp ? sesion.profesional_id : proParam;

  const desde = vista === "semana" ? lunesDe(fecha) : fecha;
  const hasta = vista === "semana" ? sumarDias(desde, 6) : fecha;
  const q = useAgenda(desde, hasta, proFiltro ?? undefined);

  function ir(cambios: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) { if (v === null) p.delete(k); else p.set(k, v); }
    setParams(p);
  }
  const mover = (dias: number) => ir({ fecha: sumarDias(fecha, vista === "semana" ? dias * 7 : dias) });

  const cols: Col[] = useMemo(() => {
    if (vista === "semana") {
      return diasDeSemana(fecha).map((d) => ({ clave: d, titulo: diaCorto(d), subtitulo: numeroDia(d), fecha: d, profesionalId: proFiltro, hoy: d === hoy }));
    }
    const lista = esp ? [{ id: sesion.profesional_id!, nombre: sesion.profesional ?? "Mi agenda" }] : proFiltro ? activos.filter((p) => p.id === proFiltro) : activos;
    return lista.map((p) => ({ clave: String(p.id), titulo: p.nombre, fecha, profesionalId: p.id, hoy: fecha === hoy }));
  }, [vista, fecha, hoy, proFiltro, esp, sesion.profesional_id, sesion.profesional, activos]);

  const titulo = vista === "semana" ? `${etiquetaDia(desde)} – ${etiquetaDia(hasta)}` : fechaLarga(fecha);
  const [diaMovil, setDiaMovil] = useState<string | null>(null);
  const diaElegido = diaMovil && diasDeSemana(fecha).includes(diaMovil) ? diaMovil : diasDeSemana(fecha).includes(hoy) ? hoy : desde;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold capitalize">{esp ? "Mi agenda" : "Agenda"} <span className="block text-sm font-normal normal-case text-tinta-suave sm:inline sm:pl-2">{titulo}</span></h1>
        <Boton variante="secundario" pequeno onClick={() => setBloquear(true)}><ShieldBan className="size-4" aria-hidden /> Bloquear tiempo</Boton>
        {!esp && <Link to="/agendar" className="inline-flex items-center gap-2 rounded-[var(--radius-control)] bg-marca px-3 py-1.5 text-sm font-medium text-white"><Plus className="size-4" aria-hidden /> Agendar cita</Link>}
      </div>

      {!esp && <ResumenDia />}

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex items-center gap-1">
          <Boton variante="secundario" pequeno aria-label={vista === "semana" ? "Semana anterior" : "Día anterior"} onClick={() => mover(-1)}><ChevronLeft className="size-4" /></Boton>
          <Boton variante="secundario" pequeno onClick={() => ir({ fecha: null })}>Hoy</Boton>
          <Boton variante="secundario" pequeno aria-label={vista === "semana" ? "Semana siguiente" : "Día siguiente"} onClick={() => mover(1)}><ChevronRight className="size-4" /></Boton>
        </div>
        <Entrada etiqueta="Ir a la fecha" type="date" value={fecha} onChange={(e) => FECHA.test(e.target.value) && ir({ fecha: e.target.value })} className="w-40" />
        <div role="group" aria-label="Vista" className="flex overflow-hidden rounded-[var(--radius-control)] border border-zinc-300">
          {(["dia", "semana"] as const).map((v) => (
            <button key={v} aria-pressed={vista === v} onClick={() => ir({ vista: v === "dia" ? null : v })}
              className={cn("px-3 py-2 text-sm font-medium", vista === v ? "bg-marca text-white" : "bg-papel hover:bg-zinc-50")}>{v === "dia" ? "Día" : "Semana"}</button>
          ))}
        </div>
        <Leyenda />
        {!esp && (
          <Seleccion etiqueta="Profesional" value={proFiltro ?? ""} className="w-52" onChange={(e) => ir({ pro: e.target.value || null })}>
            <option value="">Todos</option>
            {activos.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </Seleccion>
        )}
      </div>

      {q.isPending || (profs.isPending && !esp) ? <Cargando /> : q.error ? <ErrorVista error={q.error} reintentar={() => void q.refetch()} /> : (() => {
        const a = q.data!;
        const columnas = calcularColumnas(cols, a);
        const hayCitas = columnas.some((c) => c.datos.citas.length > 0 || c.datos.sinHora.length > 0);
        return (
          <>
            <ListasAparte columnas={columnas.map((c) => ({ titulo: c.titulo, datos: c.datos }))} alAbrir={(id) => ir({ cita: String(id) })} />
            {!movil ? (vista === "semana" && proFiltro === null
              ? <SemanaTodos cols={cols} a={a} ahora={ahora} alAbrir={(id) => ir({ cita: String(id) })} />
              : <Rejilla cols={cols} a={a} ahora={ahora} desplazar={vista === "dia" && fecha === hoy} alAbrir={(id) => ir({ cita: String(id) })} />) : (
              <div className="space-y-3">
                {vista === "semana" && (
                  <div role="group" aria-label="Día de la semana" className="flex gap-1 overflow-x-auto">
                    {diasDeSemana(fecha).map((d) => (
                      <button key={d} aria-pressed={d === diaElegido} onClick={() => setDiaMovil(d)}
                        className={cn("flex min-w-12 flex-col items-center rounded-xl border px-2 py-1.5 text-xs", d === diaElegido ? "border-marca bg-marca text-white" : "border-linea bg-papel")}>
                        <span className="capitalize">{diaCorto(d)}</span><b className="text-base">{numeroDia(d)}</b></button>
                    ))}
                  </div>
                )}
                {columnas.filter((c) => vista === "dia" || c.fecha === diaElegido).map((c) => (
                  <ListaDelDia key={c.clave} d={c.datos} ahora={ahora} conProfesional={proFiltro === null && vista === "semana"} titulo={vista === "dia" && columnas.length > 1 ? c.titulo : undefined} alAbrir={(id) => ir({ cita: String(id) })} />
                ))}
              </div>
            )}
            {!hayCitas && !movil && <p className="text-center text-sm text-tinta-suave">No hay citas en {vista === "semana" ? "esta semana" : "este día"}. Los espacios en blanco son horario de atención libre.</p>}
          </>
        );
      })()}

      <HojaCita id={citaAbierta} alCerrar={() => ir({ cita: null })} alMover={(id, f) => ir({ cita: String(id), fecha: f })} />
      <Hoja abierta={bloquear} alCerrar={() => setBloquear(false)} titulo="Bloquear tiempo"
        descripcion="Las citas vivas nunca se cancelan solas: si hay choque, te las mostramos.">
        <PanelBloqueos profesionalId={esp ? sesion.profesional_id : proFiltro}
          alAbrirCita={(id, f) => { setBloquear(false); ir({ cita: String(id), fecha: f }); }} />
      </Hoja>
    </div>
  );
}
