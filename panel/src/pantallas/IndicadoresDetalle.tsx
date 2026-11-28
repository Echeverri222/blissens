// Lo que hay detrás de las cifras de Indicadores: listas de personas y citas, tablas por profesional y servicio,
// recordatorios y el mapa día × hora. Todo en HTML plano (sin librería de gráficas).
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/cliente";
import type { CeldaDiaHora, CitaPerdida, FaltaRepetida, FilaDimension, FiltrosIndicadores } from "@/api/tipos";
import { pesos } from "@/lib/dinero";
import { ESTADOS } from "@/lib/estados";
import { fechaDe, fechaHora, fechaLarga } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { Hoja, Tarjeta } from "@/ui/controles";
import { Consulta, Vacio } from "@/ui/vistas";
import { EnlacesContacto } from "./Llamar";

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)} %`);
const MUESTRA_MINIMA = 10;

// ---------------------------------------------------------------- contadores con lista

type Contador = "riesgo" | "faltas";

function FilaPersona({ id, nombre, detalle, celular }: { id: number; nombre: string; detalle: ReactNode; celular?: string | null }) {
  return (
    <li className="space-y-1 py-3">
      <div className="flex items-start justify-between gap-3">
        <Link to={`/pacientes/${id}`} className="font-medium underline">{nombre}</Link>
        <Link to={`/pacientes/${id}`} className="shrink-0 text-sm text-tinta-suave underline">Abrir ficha</Link>
      </div>
      <p className="text-sm text-tinta-suave">{detalle}</p>
      <EnlacesContacto celular={celular} />
    </li>
  );
}

function ListaRiesgo({ f }: { f: FiltrosIndicadores }) {
  const q = useQuery({ queryKey: ["ind", "riesgo", f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.bandejas.enRiesgoFiltrado(f) });
  return <Consulta q={q}>{(d) => d.length === 0 ? <Vacio titulo="Nadie tiene un tratamiento a medias">Con los filtros elegidos no hay tratamientos activos sin próxima cita.</Vacio> : (
    <ul className="divide-y divide-linea">{d.map((r) => (
      <FilaPersona key={r.tratamiento_id} id={r.paciente_id} nombre={r.paciente} celular={r.celular}
        detalle={<>{r.servicio ?? "Tratamiento"} · hace {r.dias_sin_cita} días (última cita {r.ultima_cita})</>} />))}</ul>)}</Consulta>;
}

function ListaFaltas({ f }: { f: FiltrosIndicadores }) {
  const q = useQuery({ queryKey: ["ind", "faltas", f.desde, f.hasta, f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.indicadores.faltasRepetidas(f) });
  return <Consulta q={q}>{(d: FaltaRepetida[]) => d.length === 0 ? <Vacio titulo="Nadie faltó dos veces o más">En el periodo elegido ningún paciente acumula 2 inasistencias.</Vacio> : (
    <ul className="divide-y divide-linea">{d.map((r) => (
      <FilaPersona key={r.paciente_id} id={r.paciente_id} nombre={r.paciente} celular={r.celular}
        detalle={<>{r.faltas} inasistencias · última el {r.ultima_falta} · {r.tiene_cita_futura ? "ya tiene una cita próxima" : "sin cita próxima"}</>} />))}</ul>)}</Consulta>;
}

export function ListaContador({ cual, alCerrar, f }: { cual: Contador | null; alCerrar: () => void; f: FiltrosIndicadores }) {
  const titulo = cual === "riesgo" ? "Tratamientos sin próxima cita" : "Pacientes que faltaron 2+ veces";
  return (
    <Hoja abierta={cual !== null} alCerrar={alCerrar} titulo={titulo} ancho="md:max-w-xl"
      descripcion={cual === "riesgo" ? "Tratamientos activos que llevan tiempo sin cita y no tienen una próxima." : "Pacientes con 2 o más inasistencias en el periodo elegido."}>
      {cual === "riesgo" && <ListaRiesgo f={f} />}
      {cual === "faltas" && <ListaFaltas f={f} />}
    </Hoja>
  );
}

export function Contador({ numero, etiqueta, alAbrir, cargando }: { numero: number | undefined; etiqueta: string; alAbrir: () => void; cargando?: boolean }) {
  return (
    <button type="button" onClick={alAbrir} className="flex flex-col items-start justify-start rounded-[var(--radius-tarjeta)] border border-linea bg-papel p-3 text-left hover:bg-zinc-50 sm:p-4">
      <span className="block text-xl font-semibold tabular-nums sm:text-2xl">{cargando || numero === undefined ? "–" : numero}</span>
      <span className="block text-xs leading-snug text-tinta-suave sm:text-sm">{etiqueta}</span>
    </button>
  );
}

// ---------------------------------------------------------------- tablas por profesional y servicio

// En el celular se ocultan Citas, Atendidas y Canceladas para que el % y lo perdido queden a la vista sin desplazar.
const SECUNDARIA = new Set(["Citas", "Atendidas", "Canceladas"]);
type Orden = "inasistencia" | "perdido";
const porNombre = (a: FilaDimension, b: FilaDimension) => a.nombre.localeCompare(b.nombre);
const ORDENES: Record<Orden, (a: FilaDimension, b: FilaDimension) => number> = {
  inasistencia: (a, b) => (b.inasistencia ?? -1) - (a.inasistencia ?? -1) || porNombre(a, b),
  perdido: (a, b) => b.valor_perdido - a.valor_perdido || porNombre(a, b),
};

export function TablaDimension({ titulo, columna, filas, alAbrir }: { titulo: string; columna: string; filas: FilaDimension[]; alAbrir: (f: FilaDimension) => void }) {
  const [orden, setOrden] = useState<Orden>("inasistencia");
  return (
    <Tarjeta className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4">
        <h3 className="text-sm font-semibold">{titulo}</h3>
        {filas.length > 1 && (
          <label className="flex items-center gap-1 text-xs text-tinta-suave">Ordenar por
            <select value={orden} onChange={(e) => setOrden(e.target.value as Orden)} aria-label={`Ordenar ${titulo.toLowerCase()} por`}
              className="rounded-[var(--radius-control)] border border-zinc-300 bg-papel px-1.5 py-1 text-xs text-tinta">
              <option value="inasistencia">% inasistencia</option><option value="perdido">Perdido</option>
            </select>
          </label>)}
      </div>
      {filas.length === 0 ? <Vacio titulo="Sin datos en el periodo" /> : (
        <div className="overflow-x-auto">
          <table className="mt-2 w-full text-sm">
            <caption className="sr-only">{titulo}</caption>
            <thead><tr className="border-b border-linea text-left text-xs text-tinta-suave">
              <th scope="col" className="px-4 py-2 font-medium">{columna}</th>
              {(["Citas", "Atendidas", "No asistió", "Canceladas", "% inasistencia", "Perdido"] as const).map((c) => (
                <th key={c} scope="col" className={cn("px-3 py-2 text-right font-medium", SECUNDARIA.has(c) && "hidden sm:table-cell")}>{c}</th>))}
            </tr></thead>
            <tbody>{[...filas].sort(ORDENES[orden]).map((r) => {
              const pequena = r.atendidas + r.no_asistio < MUESTRA_MINIMA;
              return (
                <tr key={r.id} onClick={() => alAbrir(r)} className="cursor-pointer border-b border-linea last:border-0 hover:bg-zinc-50">
                  <th scope="row" className="px-4 py-2 text-left font-medium">
                    <button type="button" className="text-left underline" onClick={(e) => { e.stopPropagation(); alAbrir(r); }} aria-label={`Ver citas perdidas de ${r.nombre}`}>{r.nombre}</button>
                  </th>
                  <td className="hidden px-3 py-2 text-right tabular-nums sm:table-cell">{r.citas}</td>
                  <td className="hidden px-3 py-2 text-right tabular-nums sm:table-cell">{r.atendidas}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.no_asistio}</td>
                  <td className="hidden px-3 py-2 text-right tabular-nums sm:table-cell">{r.canceladas}</td>
                  <td className={cn("px-3 py-2 text-right tabular-nums", pequena && "text-zinc-400")}>
                    {pct(r.inasistencia)}{pequena && <span className="block text-xs font-normal">muestra pequeña</span>}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{pesos(r.valor_perdido)}</td>
                </tr>);
            })}</tbody>
          </table>
        </div>)}
    </Tarjeta>
  );
}

function FilaPerdida({ c }: { c: CitaPerdida }) {
  const estado = ESTADOS[c.estado as keyof typeof ESTADOS];
  return (
    <li className="py-3 text-sm">
      <Link to={`/agenda?fecha=${c.inicio ? fechaDe(c.inicio) : c.dia}&cita=${c.cita_id}`} className="font-medium underline">{c.paciente}</Link>
      <span className="text-tinta-suave"> · {c.inicio ? fechaHora(c.inicio) : c.dia}</span>
      <p className="text-tinta-suave">{c.servicio} · {c.profesional}</p>
      <p className="flex flex-wrap items-center gap-x-2">
        <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", estado?.clases.replace("line-through", ""))}>{c.estado === "cancelada" ? "Canceló tarde" : estado?.texto ?? c.estado}</span>
        {c.motivo && <span className="text-tinta-suave">Motivo: {c.motivo}</span>}
        <span className={c.reagendada ? "text-emerald-800" : "text-rose-800"}>{c.reagendada ? "Ya volvió a agendar" : "No ha vuelto a agendar"}</span>
      </p>
    </li>
  );
}

export function CitasPerdidas({ fila, dimension, f, alCerrar }: { fila: FilaDimension | null; dimension: "profesional" | "servicio"; f: FiltrosIndicadores; alCerrar: () => void }) {
  const filtro: FiltrosIndicadores = { ...f, ...(dimension === "profesional" ? { profesional_id: fila?.id } : { servicio_id: fila?.id }) };
  const q = useQuery({ queryKey: ["ind", "perdidas", dimension, fila?.id ?? null, f.desde, f.hasta, f.profesional_id ?? null, f.servicio_id ?? null],
    queryFn: () => api.indicadores.citasPerdidas(filtro), enabled: fila !== null });
  return (
    <Hoja abierta={fila !== null} alCerrar={alCerrar} titulo={`Citas perdidas: ${fila?.nombre ?? ""}`} ancho="md:max-w-xl"
      descripcion="Inasistencias y cancelaciones tardías del periodo elegido.">
      <Consulta q={q}>{(d) => d.length === 0 ? <Vacio titulo="Sin citas perdidas">En el periodo no hay inasistencias ni cancelaciones tardías.</Vacio>
        : <ul className="divide-y divide-linea">{d.map((c) => <FilaPerdida key={c.cita_id} c={c} />)}</ul>}</Consulta>
    </Hoja>
  );
}

// ---------------------------------------------------------------- ¿el equipo cierra sus pendientes?

/** "3 h" o "2 días": las horas hasta 2 días, después días. */
const duracion = (h: number | null) => (h === null ? "—" : h < 48 ? `${h < 1 ? "<1" : Math.round(h)} h` : `${Math.round(h / 24)} días`);
const PENDIENTES = [["cierre_citas", "Desenlace de citas"], ["mensajes", "Mensajes atendidos"], ["seguimientos", "Seguimientos cerrados"]] as const;

export function Pendientes({ f }: { f: FiltrosIndicadores }) {
  const q = useQuery({ queryKey: ["ind", "pendientes", f.desde, f.hasta, f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.indicadores.pendientes(f) });
  return (
    <Tarjeta className="space-y-3 p-4">
      <h3 className="text-sm font-semibold">¿El equipo cierra sus pendientes?</h3>
      <Consulta q={q}>{(d) => (<>
        <table className="w-full text-sm">
          <caption className="sr-only">Pendientes resueltos por el equipo</caption>
          <thead><tr className="border-b border-linea text-left text-xs text-tinta-suave">
            <th scope="col" className="py-1.5 pr-2 font-medium">Pendiente</th>
            <th scope="col" className="px-2 py-1.5 text-right font-medium">Resueltos</th>
            <th scope="col" className="px-2 py-1.5 text-right font-medium">Tiempo típico</th>
            <th scope="col" className="py-1.5 pl-2 text-right font-medium">Vencidos ahora</th>
          </tr></thead>
          <tbody>{PENDIENTES.map(([k, t]) => (
            <tr key={k} className="border-b border-linea last:border-0">
              <th scope="row" className="py-2 pr-2 text-left font-medium">{t}</th>
              <td className="px-2 py-2 text-right tabular-nums">{d[k].resueltos}</td>
              <td className="px-2 py-2 text-right tabular-nums">{duracion(d[k].mediana_horas)}</td>
              <td className={cn("py-2 pl-2 text-right tabular-nums", d[k].vencidos > 0 && "font-medium text-rose-700")}>{d[k].vencidos}<span className="font-normal text-tinta-suave"> de {d[k].abiertos_hoy}</span></td>
            </tr>))}</tbody>
        </table>
        {d.por_usuario.length > 0 && (
          <ul className="space-y-0.5 text-sm" aria-label="Pendientes resueltos por persona">{d.por_usuario.map((u) => (
            <li key={u.usuario_id ?? "ninguno"} className="flex justify-between gap-3"><span className={cn(u.usuario === null && "text-tinta-suave")}>{u.usuario ?? "Sin registrar"}</span>
              <span className="tabular-nums">{u.resueltos} <span className="text-tinta-suave">· {duracion(u.mediana_horas)}</span></span></li>))}</ul>)}
        <p className="text-xs text-tinta-suave">Tiempo típico: la mediana entre que el pendiente nació y alguien lo resolvió, en el periodo elegido. Vencidos: abiertos hoy con más de 48 h (7 días los seguimientos).
          {" "}Antes del {fechaLarga(d.registro_desde)} no se registraba quién resolvía; esas filas aparecen como Sin registrar.</p>
      </>)}</Consulta>
    </Tarjeta>
  );
}

// ---------------------------------------------------------------- de cancelar a volver a agendar

const TRAMOS = [["mismo_dia", "Mismo día", "bg-sky-700"], ["1_3", "1–3 días", "bg-sky-500"], ["4_14", "4–14 días", "bg-sky-300"], ["15_60", "15–60 días", "bg-sky-200"], ["no_reagendo", "No reagendó", "bg-zinc-300"]] as const;

export function Reagendamiento({ f }: { f: FiltrosIndicadores }) {
  const q = useQuery({ queryKey: ["ind", "reagendamiento", f.desde, f.hasta, f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.indicadores.reagendamiento(f) });
  return (
    <Tarjeta className="space-y-3 p-4">
      <h3 className="text-sm font-semibold">Después de cancelar, ¿cuánto tardan en volver?</h3>
      <Consulta q={q}>{(d) => {
        if (d.total === 0) return <Vacio titulo="Sin cancelaciones en el periodo" />;
        const dias = d.mediana_dias === null ? null : Math.round(d.mediana_dias);
        return (<>
          <p className="text-sm">{dias === null ? "Nadie ha vuelto a agendar" : <>La mitad reagenda {dias === 0 ? "el mismo día" : <>en <b>{dias} {dias === 1 ? "día" : "días"}</b></>}</>}
            <span className="text-tinta-suave"> · {d.total - d.buckets.no_reagendo} de {d.total} cancelaciones</span></p>
          <div className="flex h-3 overflow-hidden rounded bg-zinc-100" role="img" aria-label="Cancelaciones según cuánto tardó el paciente en volver a agendar">
            {TRAMOS.map(([k, t, color]) => d.buckets[k] > 0 && <div key={k} title={`${t}: ${d.buckets[k]}`} className={color} style={{ width: `${(d.buckets[k] / d.total) * 100}%` }} />)}
          </div>
          <ul className="grid grid-cols-5 gap-1 text-center" aria-label="Cancelaciones por tiempo hasta volver a agendar">{TRAMOS.map(([k, t, color]) => (
            <li key={k} className="min-w-0"><span className="block text-lg font-semibold tabular-nums">{d.buckets[k]}</span>
              <span className="flex items-center justify-center gap-1 text-[11px] leading-tight text-tinta-suave"><span className={cn("size-2 shrink-0 rounded-full", color)} aria-hidden />{t}</span></li>))}</ul>
          <p className="text-xs text-tinta-suave">Cancelaciones hechas en el periodo (por la fecha en que se cancelaron, no la de la cita). Cuenta cualquier cita nueva con el mismo profesional o servicio en los 60 días siguientes.</p>
        </>);
      }}</Consulta>
    </Tarjeta>
  );
}

/** Planes de tratamiento entregados en el periodo y cuántos tienen siguiente paso a los 15 días (R14). */
export function Planes({ f }: { f: FiltrosIndicadores }) {
  const q = useQuery({ queryKey: ["ind", "planes", f.desde, f.hasta, f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.indicadores.planes(f) });
  return (
    <Tarjeta className="space-y-2 p-4">
      <h3 className="text-sm font-semibold">Planes</h3>
      <Consulta q={q}>{(d) => d.entregados === 0 ? <Vacio titulo="Sin planes entregados en el periodo" /> : (<>
        <p className="text-sm"><b className="text-lg tabular-nums">{d.entregados}</b> {d.entregados === 1 ? "plan entregado" : "planes entregados"}
          <span className="text-tinta-suave"> · {pct(d.conversion_pct === null ? null : d.conversion_pct / 100)} con cita o abono en los 15 días siguientes ({d.con_siguiente_paso} de {d.entregados})</span></p>
        {d.valor_sin_siguiente_paso !== null && <p className="text-sm">Valor de los planes sin siguiente paso: <b className="tabular-nums">{pesos(d.valor_sin_siguiente_paso)}</b></p>}
        <p className="text-xs text-tinta-suave">Cuenta los planes por la fecha en que se entregaron. El siguiente paso es una cita con el mismo profesional o un abono.</p>
      </>)}</Consulta>
    </Tarjeta>
  );
}

// ---------------------------------------------------------------- recordatorios

export function Recordatorios({ f, fallidos }: { f: FiltrosIndicadores; fallidos: number }) {
  const q = useQuery({ queryKey: ["ind", "recordatorios", f.desde, f.hasta, f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.indicadores.recordatorios(f) });
  return (
    <Tarjeta className="space-y-4 p-4">
      <h3 className="text-sm font-semibold">¿Funcionan los recordatorios?</h3>
      <Consulta q={q}>{(d) => {
        const e = d.embudo;
        const pasos: [string, number][] = [["Citas del periodo", e.citas], ["Con recordatorio enviado", e.con_recordatorio], ["Confirmadas por el paciente", e.confirmadas], ["Atendidas", e.atendidas]];
        return (<>
          <div className="grid grid-cols-2 gap-3">
            {([["Con recordatorio", d.con_recordatorio], ["Sin recordatorio", d.sin_recordatorio]] as const).map(([t, g]) => (
              <div key={t}><p className="text-xs text-tinta-suave">Inasistencia {t.toLowerCase()}</p><p className="text-xl font-semibold tabular-nums">{pct(g.inasistencia)}</p><p className="text-xs text-tinta-suave">{g.no_asistio} de {g.n} citas</p></div>))}
          </div>
          <p className="text-xs text-tinta-suave">Porcentaje sobre el total de citas del periodo.</p>
          <ol className="space-y-1 text-sm" aria-label="Embudo de recordatorios">{pasos.map(([t, n], i) => (
            <li key={t} className="flex justify-between gap-3"><span>{t}</span>
              <span className="tabular-nums">{n}{i > 0 && <span className="text-tinta-suave"> · {pct(pasos[0][1] ? n / pasos[0][1] : null)}</span>}</span></li>))}</ol>
        </>);
      }}</Consulta>
      {fallidos > 0 && <p className="text-xs text-tinta-suave">{fallidos} {fallidos === 1 ? "recordatorio falló" : "recordatorios fallaron"} al enviarse. <Link to="/sistema" className="underline">Ver en Sistema</Link></p>}
    </Tarjeta>
  );
}

// ---------------------------------------------------------------- día × hora

const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const MUESTRA_CELDA = 5;

export function DiaHora({ f }: { f: FiltrosIndicadores }) {
  const q = useQuery({ queryKey: ["ind", "dia-hora", f.desde, f.hasta, f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.indicadores.diaHora(f) });
  const [sel, setSel] = useState<(CeldaDiaHora & { etiqueta?: string }) | null>(null);
  return (
    <Tarjeta className="space-y-3 p-4">
      <h3 className="text-sm font-semibold">¿Cuándo faltan los pacientes?</h3>
      <Consulta q={q}>{(d) => {
        if (d.length === 0) return <Vacio titulo="Sin datos en el periodo">Aparecerán cuando haya citas atendidas o con inasistencia.</Vacio>;
        const horas = Array.from({ length: Math.max(...d.map((c) => c.hora)) - Math.min(...d.map((c) => c.hora)) + 1 }, (_, i) => Math.min(...d.map((c) => c.hora)) + i);
        const dias = DIAS.map((_, i) => i).filter((i) => i < 6 || d.some((c) => c.dia_semana === 6));
        const celda = (di: number, h: number) => d.find((c) => c.dia_semana === di && c.hora === h);
        // Totales por día y por hora: con periodos cortos casi ninguna celda llega a la muestra mínima, pero los totales sí.
        const suma = (cs: CeldaDiaHora[]) => ({ no: cs.reduce((a, c) => a + c.no_asistio, 0), n: cs.reduce((a, c) => a + c.atendidas + c.no_asistio, 0) });
        const porDia = new Map(dias.map((di) => [di, suma(d.filter((c) => c.dia_semana === di))]));
        const porHora = new Map(horas.map((h) => [h, suma(d.filter((c) => c.hora === h))]));
        const peor = <K,>(m: Map<K, { no: number; n: number }>) => [...m].filter(([, t]) => t.n >= MUESTRA_CELDA).sort(([, a], [, b]) => b.no / b.n - a.no / a.n)[0];
        const [peorDia, peorHora] = [peor(porDia), peor(porHora)];
        const casilla = (no: number, n: number, etiqueta: string, alTocar?: () => void, total?: boolean) => {
          const p = n >= MUESTRA_CELDA ? no / n : null;
          return (
            <button type="button" onClick={alTocar ?? (() => setSel({ dia_semana: -1, hora: -1, atendidas: n - no, no_asistio: no, etiqueta }))}
              title={`${no} de ${n}`} aria-label={`${etiqueta}, ${no} de ${n} no asistieron`}
              style={p === null ? undefined : { backgroundColor: `rgba(225, 29, 72, ${Math.min(0.75, p * 1.5).toFixed(2)})` }}
              className={cn("block h-8 w-12 rounded tabular-nums", p === null ? "bg-zinc-100 text-zinc-400" : "text-tinta", total && "font-semibold ring-1 ring-linea")}>
              {p === null ? "·" : `${Math.round(p * 100)}%`}</button>);
        };
        return (<>
          {(peorDia || peorHora) && <p className="text-sm">Más inasistencia{peorDia && <> los <b>{DIAS[peorDia[0]].toLowerCase()}</b> ({Math.round(peorDia[1].no / peorDia[1].n * 100)} %)</>}
            {peorDia && peorHora && " y"}{peorHora && <> a las <b>{String(peorHora[0]).padStart(2, "0")}:00</b> ({Math.round(peorHora[1].no / peorHora[1].n * 100)} %)</>}.</p>}
          <div className="overflow-x-auto">
            <table className="text-xs">
              <caption className="sr-only">Porcentaje de inasistencia por día de la semana y hora</caption>
              <thead><tr><td /><th scope="col" className="px-1 pb-1 pr-2 font-semibold">Total</th>
                {horas.map((h) => <th key={h} scope="col" className="px-1 pb-1 font-medium text-tinta-suave">{String(h).padStart(2, "0")}:00</th>)}</tr></thead>
              <tbody>{dias.map((di) => (
                <tr key={di}><th scope="row" className="whitespace-nowrap pr-2 text-left font-medium">{DIAS[di].slice(0, 3)}</th>
                  <td className="p-0.5 pr-2">{casilla(porDia.get(di)!.no, porDia.get(di)!.n, `Todos los ${DIAS[di].toLowerCase()}`, undefined, true)}</td>
                  {horas.map((h) => {
                    const c = celda(di, h);
                    const n = c ? c.atendidas + c.no_asistio : 0;
                    return (
                      <td key={h} className="p-0.5">
                        {c ? casilla(c.no_asistio, n, `${DIAS[di]} ${h}:00`, () => setSel(c)) : <span className="block h-8 w-12 rounded bg-zinc-50" />}
                      </td>);
                  })}</tr>))}
                <tr><th scope="row" className="pr-2 text-left font-semibold">Total</th><td />
                  {horas.map((h) => <td key={h} className="p-0.5">{casilla(porHora.get(h)!.no, porHora.get(h)!.n, `Todas las citas de las ${h}:00`, undefined, true)}</td>)}</tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-tinta-suave" aria-live="polite">{sel
            ? `${sel.etiqueta ?? `${DIAS[sel.dia_semana]} ${sel.hora}:00`} — ${sel.no_asistio} de ${sel.atendidas + sel.no_asistio} no asistieron.`
            : `Toca una celda para ver cuántas citas fueron. Las celdas con menos de ${MUESTRA_CELDA} citas se muestran sin color (·).`}</p>
        </>);
      }}</Consulta>
    </Tarjeta>
  );
}
