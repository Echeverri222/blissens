import { CalendarOff } from "lucide-react";
import type { Agenda, CitaAgenda } from "@/api/tipos";
import { columnaDia, posicion, rangoVisible, type ColumnaDia } from "@/lib/calendario";
import { CLASES_POR_CERRAR, ESTADOS, porCerrar } from "@/lib/estados";
import { nombreCorto, profesionalCorto } from "@/lib/nombres";
import { hhmm, horaDe, minutosDelDia } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { EtiquetaEstado, IconoEstado } from "@/ui/controles";

export interface Col { clave: string; titulo: string; subtitulo?: string; fecha: string; profesionalId: number | null; hoy?: boolean }
const PX_HORA = 60;

export function calcularColumnas(cols: Col[], a: Agenda) {
  return cols.map((c) => ({ ...c, datos: columnaDia(c.fecha, c.profesionalId, a) }));
}

/** Rejilla de horas (escritorio): una columna por profesional (día) o por día (semana). */
export function Rejilla({ cols, a, ahora, alAbrir }: { cols: Col[]; a: Agenda; ahora: Date; alAbrir: (id: number) => void }) {
  const columnas = calcularColumnas(cols, a);
  // Sin desplazamiento automático: la página abre arriba para que el resumen del día y los controles queden a la vista.
  // La línea roja marca la hora actual.
  const visible = rangoVisible(columnas.map((c) => c.datos));
  const alto = ((visible.hasta - visible.desde) / 60) * PX_HORA;
  const horas = Array.from({ length: (visible.hasta - visible.desde) / 60 + 1 }, (_, i) => visible.desde + i * 60);
  const minAhora = minutosDelDia(ahora);
  return (
    <div className="overflow-x-auto rounded-[var(--radius-tarjeta)] border border-linea bg-papel" role="region" aria-label="Calendario">
      <div className="grid min-w-[40rem]" style={{ gridTemplateColumns: `3.5rem repeat(${columnas.length}, minmax(9rem, 1fr))` }}>
        <div className="sticky top-0 z-10 border-b border-linea bg-papel" />
        {columnas.map((c) => (
          <div key={c.clave} className={cn("sticky top-0 z-10 border-b border-l border-linea bg-papel px-2 py-2 text-center", c.hoy && "bg-sky-50")}>
            <p className="text-sm font-semibold capitalize">{c.titulo}</p>
            {c.subtitulo && <p className="text-xs text-tinta-suave">{c.subtitulo}</p>}
          </div>
        ))}
        <div className="relative" style={{ height: alto }} aria-hidden>
          {horas.slice(0, -1).map((h) => (
            <span key={h} className="absolute right-2 -translate-y-1/2 text-xs text-tinta-suave" style={{ top: ((h - visible.desde) / 60) * PX_HORA, ...(h === visible.desde && { transform: "none" }) }}>{hhmm(h)}</span>
          ))}
        </div>
        {columnas.map((c) => (
          <div key={c.clave} className="relative border-l border-linea bg-zinc-200/70" style={{ height: alto }}>
            <Fondo d={c.datos} visible={visible} />
            {c.datos.cupos.map(({ cupo, ...t }) => {
              const p = posicion(t, visible);
              return p && (
                <div key={`cupo-${cupo.id}`} className="absolute inset-x-1 rounded-md border-2 border-dashed border-teal-600 bg-teal-50/80 px-1.5 py-0.5 text-xs text-teal-950"
                  style={{ top: `${p.arriba}%`, height: `${p.alto}%` }}>
                  Cupo {cupo.estado === "en_oferta" ? "en oferta" : "liberado"}
                </div>
              );
            })}
            {c.datos.citas.map(({ cita, ...t }) => {
              const p = posicion(t, visible);
              return p && <CajaDeCita key={cita.id} cita={cita} ahora={ahora} estilo={{ top: `${p.arriba}%`, height: `${p.alto}%` }} alAbrir={alAbrir} compacta={(p.alto / 100) * alto < 44} />;
            })}
            {c.hoy && minAhora >= visible.desde && minAhora <= visible.hasta && (
              <div role="img" aria-label={`Hora actual del sistema ${horaDe(ahora)}`} className="pointer-events-none absolute inset-x-0 z-10 border-t-2 border-rose-600"
                style={{ top: ((minAhora - visible.desde) / 60) * PX_HORA }}><span className="absolute -left-1 -top-1.5 size-2.5 rounded-full bg-rose-600" /></div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Fondo({ d, visible }: { d: ColumnaDia; visible: { desde: number; hasta: number } }) {
  return (
    <>
      {d.franjas.map((f, i) => {
        const p = posicion(f, visible);
        return p && <div key={`f${i}`} className="absolute inset-x-0 bg-papel" style={{ top: `${p.arriba}%`, height: `${p.alto}%` }} />;
      })}
      {d.bloqueos.map((b) => {
        const p = posicion(b, visible);
        return p && (
          <div key={`b${b.ids.join("-")}`} className="absolute inset-x-0 z-[1] overflow-hidden border-y border-zinc-500 px-1.5 py-1 text-xs font-medium text-zinc-900"
            style={{ top: `${p.arriba}%`, height: `${p.alto}%`, background: "repeating-linear-gradient(45deg,#d4d4d8,#d4d4d8 6px,#e4e4e7 6px,#e4e4e7 12px)" }}>
            <span className="inline-flex items-center gap-1 rounded bg-white/80 px-1"><CalendarOff className="size-3" aria-hidden /> Bloqueado{b.motivos.length ? `: ${b.motivos.join(" · ")}` : ""}</span>
          </div>
        );
      })}
    </>
  );
}

function CajaDeCita({ cita, ahora, estilo, alAbrir, compacta }: { cita: CitaAgenda; ahora: Date; estilo: React.CSSProperties; alAbrir: (id: number) => void; compacta?: boolean }) {
  const e = ESTADOS[cita.estado];
  const cerrar = porCerrar(cita, ahora);
  return (
    <button type="button" onClick={() => alAbrir(cita.id)} style={estilo} title={cita.paciente}
      aria-label={`${horaDe(cita.inicio!)} ${cita.paciente}, ${cita.servicio}, ${e.texto}${cerrar ? ", por cerrar" : ""}`}
      className={cn("absolute inset-x-1 z-[2] overflow-hidden rounded-md border-l-4 px-1.5 py-0.5 text-left text-xs shadow-sm hover:brightness-95", cerrar ? CLASES_POR_CERRAR : e.clases, e.borde)}>
      <span className="flex items-center gap-1 font-semibold"><span className="tabular-nums">{horaDe(cita.inicio!)}</span><IconoEstado estado={cita.estado} />
        {compacta && <span className="min-w-0 truncate">{nombreCorto(cita.paciente)}</span>}
        {cerrar && <EtiquetaPorCerrar />}</span>
      {!compacta && <span className="block font-semibold leading-tight">{nombreCorto(cita.paciente)}</span>}
      {!compacta && <span className="block truncate">{cita.servicio}</span>}
      {!compacta && !cerrar && <EtiquetaEstado estado={cita.estado} className="mt-0.5 !bg-white/60" />}
    </button>
  );
}

/** Cita pasada que sigue viva: la tarjeta (que abre la hoja de la cita) es donde se registra el desenlace. */
function EtiquetaPorCerrar() {
  return <span className="ml-auto shrink-0 rounded-full border border-zinc-500 bg-white px-1.5 text-xs font-medium text-zinc-900">Por cerrar</span>;
}

/** Semana de todos los profesionales: una columna por día y las citas apiladas por hora (no caben en una rejilla de horas sin pisarse). */
export function SemanaTodos({ cols, a, ahora, alAbrir }: { cols: Col[]; a: Agenda; ahora: Date; alAbrir: (id: number) => void }) {
  const columnas = calcularColumnas(cols, a);
  return (
    <div className="overflow-x-auto rounded-[var(--radius-tarjeta)] border border-linea bg-papel" role="region" aria-label="Calendario de la semana">
      <div className="grid min-w-[56rem]" style={{ gridTemplateColumns: `repeat(${columnas.length}, minmax(8rem, 1fr))` }}>
        {columnas.map((c) => (
          <div key={c.clave} aria-label={`${c.titulo} ${c.subtitulo ?? ""}`} className={cn("min-h-40 border-l border-linea first:border-l-0", c.hoy && "bg-sky-50")}>
            <p className="border-b border-linea px-2 py-2 text-center text-sm font-semibold capitalize">{c.titulo} <span className="font-normal text-tinta-suave">{c.subtitulo}</span></p>
            <ul className="space-y-1 p-1">
              {c.datos.citas.length === 0 && <li className="px-1 py-2 text-center text-xs text-tinta-suave">Sin citas</li>}
              {c.datos.citas.map(({ cita }) => {
                const e = ESTADOS[cita.estado];
                const cerrar = porCerrar(cita, ahora);
                return (
                  <li key={cita.id}>
                    <button type="button" onClick={() => alAbrir(cita.id)} title={cita.paciente}
                      aria-label={`${horaDe(cita.inicio!)} ${cita.paciente}, ${cita.servicio}, ${profesionalCorto(cita.profesional)}, ${e.texto}${cerrar ? ", por cerrar" : ""}`}
                      className={cn("w-full rounded-md border-l-4 px-1.5 py-1 text-left text-xs shadow-sm hover:brightness-95", cerrar ? CLASES_POR_CERRAR : e.clases, e.borde)}>
                      <span className="flex items-center gap-1 font-semibold"><span className="tabular-nums">{horaDe(cita.inicio!)}</span><IconoEstado estado={cita.estado} />{cerrar && <EtiquetaPorCerrar />}</span>
                      <span className="block font-semibold leading-tight">{nombreCorto(cita.paciente)}</span>
                      <span className="block leading-tight">{profesionalCorto(cita.profesional)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Lista cronológica de un día (celular, y el modo de lectura simple). */
export function ListaDelDia({ d, titulo, ahora, conProfesional, alAbrir }: { d: ColumnaDia; titulo?: string; ahora: Date; conProfesional?: boolean; alAbrir: (id: number) => void }) {
  const items = [
    ...d.citas.map((c) => ({ desde: c.desde, nodo: <FilaCita key={`c${c.cita.id}`} cita={c.cita} ahora={ahora} conProfesional={conProfesional} alAbrir={alAbrir} /> })),
    ...d.bloqueos.map((b) => ({ desde: b.desde, nodo: (
      <li key={`b${b.ids.join("-")}`} className="flex items-center gap-2 rounded-xl border border-zinc-300 bg-zinc-100 px-3 py-2 text-sm">
        <CalendarOff className="size-4 shrink-0" aria-hidden />
        <span><b>{hhmm(b.desde)}–{hhmm(b.hasta === 1440 ? 1439 : b.hasta)}</b> Bloqueado{b.motivos.length ? `: ${b.motivos.join(" · ")}` : ""}</span>
      </li>) })),
    ...d.cupos.map(({ cupo, ...t }) => ({ desde: t.desde, nodo: (
      <li key={`u${cupo.id}`} className="rounded-xl border-2 border-dashed border-teal-600 bg-teal-50 px-3 py-2 text-sm text-teal-950">
        <b>{hhmm(t.desde)}–{hhmm(t.hasta)}</b> Cupo {cupo.estado === "en_oferta" ? "en oferta" : "liberado"}</li>) })),
  ].sort((a, b) => a.desde - b.desde);
  return (
    <section aria-label={titulo ?? "Citas del día"} className="space-y-2">
      {titulo && <h3 className="text-sm font-semibold capitalize">{titulo}</h3>}
      {items.length === 0
        ? <p className="rounded-xl border border-dashed border-zinc-300 px-3 py-4 text-center text-sm text-tinta-suave">No hay citas este día.</p>
        : <ul className="space-y-2">{items.map((i) => i.nodo)}</ul>}
    </section>
  );
}

function FilaCita({ cita, ahora, conProfesional, alAbrir }: { cita: CitaAgenda; ahora: Date; conProfesional?: boolean; alAbrir: (id: number) => void }) {
  const e = ESTADOS[cita.estado];
  const cerrar = porCerrar(cita, ahora);
  return (
    <li>
      <button type="button" onClick={() => alAbrir(cita.id)} className={cn("flex w-full items-center gap-3 rounded-xl border-l-4 px-3 py-2.5 text-left text-sm shadow-sm", cerrar ? CLASES_POR_CERRAR : e.clases, e.borde)}
        aria-label={`${horaDe(cita.inicio!)} ${cita.paciente}, ${cita.servicio}, ${e.texto}${cerrar ? ", por cerrar" : ""}`}>
        <span className="w-12 shrink-0 font-semibold tabular-nums">{horaDe(cita.inicio!)}</span>
        <span className="min-w-0 flex-1"><span className="block truncate font-medium">{cita.paciente}</span>
          <span className="block truncate text-xs">{cita.servicio}{conProfesional ? ` · ${profesionalCorto(cita.profesional)}` : ""}</span></span>
        {cerrar ? <EtiquetaPorCerrar /> : <EtiquetaEstado estado={cita.estado} className="!bg-white/60" />}
      </button>
    </li>
  );
}

/** Citas importadas sin hora (encima del día) y canceladas (plegadas, bajo el día). */
export function ListasAparte({ columnas, alAbrir }: { columnas: { titulo: string; datos: ColumnaDia }[]; alAbrir: (id: number) => void }) {
  const sinHora = columnas.flatMap((c) => c.datos.sinHora.map((x) => ({ ...x, col: c.titulo })));
  const canceladas = columnas.flatMap((c) => c.datos.canceladas.map((x) => ({ ...x, col: c.titulo })));
  return (
    <>
      {sinHora.length > 0 && (
        <section aria-label="Citas sin hora" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm">
          <h3 className="font-semibold text-amber-950">Citas sin hora ({sinHora.length})</h3>
          <p className="mb-2 text-xs text-amber-900">Vienen de una importación y no tienen hora asignada.</p>
          <ul className="space-y-1">{sinHora.map((c) => (
            <li key={c.id}><button className="underline" onClick={() => alAbrir(c.id)}>{c.paciente} · {c.servicio} · {c.profesional}</button></li>
          ))}</ul>
        </section>
      )}
      {canceladas.length > 0 && (
        <details className="rounded-xl border border-linea bg-papel p-3 text-sm">
          <summary className="cursor-pointer font-medium">Citas canceladas ({canceladas.length})</summary>
          <ul className="mt-2 space-y-1">{canceladas.map((c) => (
            <li key={c.id}><button className="text-left underline" onClick={() => alAbrir(c.id)}>{horaDe(c.inicio!)} · {c.paciente} · {c.servicio} · {c.profesional}</button></li>
          ))}</ul>
        </details>
      )}
    </>
  );
}
