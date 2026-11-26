import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Info } from "lucide-react";
import { api } from "@/api/cliente";
import { useProfesionales, useServicios } from "@/api/consultas";
import type { FilaDimension, FiltrosIndicadores, Resumen } from "@/api/tipos";
import { fechaLarga, sumarDias } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { useSesion } from "@/sesion/Sesion";
import { Boton, Entrada, Seleccion, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta, Vacio } from "@/ui/vistas";
import { CitasPerdidas, Contador, DiaHora, ListaContador, pct, Recordatorios, TablaDimension } from "./IndicadoresDetalle";
import { estadoCierre } from "./Sistema";

const AZUL = "#3b9fe0";
const SIN_SERVICIO = "No aplica al filtrar por servicio";

/** Diferencia en puntos porcentuales con flecha. El color sale del significado (¿mejoró?), no de la dirección. */
function Delta({ actual, anterior, mejorSiSube }: { actual: number | null; anterior: number | null | undefined; mejorSiSube: boolean }) {
  if (actual === null || anterior === null || anterior === undefined) return <p className="text-xs text-tinta-suave">Sin periodo anterior para comparar</p>;
  const pp = (actual - anterior) * 100;
  const igual = Math.abs(pp) < 0.05;
  const mejora = mejorSiSube === pp > 0;
  const flecha = igual ? "→" : pp > 0 ? "▲" : "▼";
  return (
    <p className={cn("text-xs", igual ? "text-tinta-suave" : mejora ? "text-emerald-700" : "text-rose-700")}>
      <span aria-hidden>{flecha}</span> {igual ? "Igual" : `${pp > 0 ? "+" : "−"}${Math.abs(pp).toFixed(1)} pp`} <span className="text-tinta-suave">vs. {pct(anterior)} antes</span>
    </p>
  );
}

function Ayuda({ children }: { children: ReactNode }) {
  return (
    <details className="group mt-1 text-xs text-tinta-suave">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 [&::-webkit-details-marker]:hidden"><Info className="size-3.5" aria-hidden /><span>¿Cómo se calcula?</span></summary>
      <p className="mt-1">{children}</p>
    </details>
  );
}

function Clave({ titulo, valor, anterior, mejorSiSube, ayuda }: { titulo: string; valor: number | null; anterior: number | null | undefined; mejorSiSube: boolean; ayuda: string }) {
  return (
    <Tarjeta className="p-4">
      <p className="text-sm text-tinta-suave">{titulo}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{pct(valor)}</p>
      <Delta actual={valor} anterior={anterior} mejorSiSube={mejorSiSube} />
      <Ayuda>{ayuda}</Ayuda>
    </Tarjeta>
  );
}

function Cifra({ titulo, valor, detalle, ayuda, aplica = true }: { titulo: string; valor: string | number | null; detalle?: string; ayuda: string; aplica?: boolean }) {
  return (
    <Tarjeta className="p-4">
      <p className="text-sm text-tinta-suave">{titulo}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{aplica && valor !== null ? valor : "—"}</p>
      {!aplica ? <p className="text-xs text-tinta-suave">{SIN_SERVICIO}</p> : detalle && <p className="text-xs text-tinta-suave">{detalle}</p>}
      <Ayuda>{ayuda}</Ayuda>
    </Tarjeta>
  );
}

const PRESETS = ["Últimos 7 días", "Últimos 30 días", "Este mes", "Mes pasado"] as const;
type Preset = (typeof PRESETS)[number];
function rango(p: Preset, hoy: string): [string, string] {
  const primero = `${hoy.slice(0, 8)}01`;
  if (p === "Últimos 7 días") return [sumarDias(hoy, -6), hoy];
  if (p === "Últimos 30 días") return [sumarDias(hoy, -29), hoy];
  if (p === "Este mes") return [primero, hoy];
  const ultimo = sumarDias(primero, -1);
  return [`${ultimo.slice(0, 8)}01`, ultimo];
}

type Pendiente = { fecha: string; sin: number; datos: boolean };

export function Indicadores() {
  const { hoy } = useSesion();
  const [desde, setDesde] = useState(rango("Últimos 30 días", hoy)[0]);
  const [hasta, setHasta] = useState(hoy);
  const [pro, setPro] = useState("");
  const [srv, setSrv] = useState("");
  const [verFiltros, setVerFiltros] = useState(false);
  const [lista, setLista] = useState<"riesgo" | "faltas" | null>(null);
  const [fila, setFila] = useState<{ dim: "profesional" | "servicio"; fila: FilaDimension } | null>(null);
  const profs = useProfesionales();
  const servs = useServicios();
  const f: FiltrosIndicadores = { desde, hasta, profesional_id: pro ? Number(pro) : undefined, servicio_id: srv ? Number(srv) : undefined };
  const clave = [desde, hasta, pro, srv];
  const activos = (pro ? 1 : 0) + (srv ? 1 : 0);
  const resumen = useQuery({ queryKey: ["ind", "resumen", ...clave], queryFn: () => api.indicadores.resumen(f, true) });
  const tendencia = useQuery({ queryKey: ["ind", "tendencia", ...clave], queryFn: () => api.indicadores.tendencia(f, "semana") });
  const porPro = useQuery({ queryKey: ["ind", "pro", ...clave], queryFn: () => api.indicadores.porProfesional(f) });
  const porSrv = useQuery({ queryKey: ["ind", "srv", ...clave], queryFn: () => api.indicadores.porServicio(f) });
  const motivos = useQuery({ queryKey: ["ind", "motivos", ...clave], queryFn: () => api.indicadores.motivos(f) });
  const tiempo = useQuery({ queryKey: ["ind", "tiempo", ...clave], queryFn: () => api.indicadores.tiempoEntreCitas(f) });
  const faltas = useQuery({ queryKey: ["ind", "faltas", desde, hasta, f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.indicadores.faltasRepetidas(f) });
  const riesgo = useQuery({ queryKey: ["ind", "riesgo", f.profesional_id ?? null, f.servicio_id ?? null], queryFn: () => api.bandejas.enRiesgoFiltrado(f) });
  const sistema = useQuery({ queryKey: ["sistema"], queryFn: api.sistema });
  const fallidos = sistema.data?.tareas_fallidas.filter((t) => t.tipo.startsWith("recordatorio")).length ?? 0;
  const cierre = sistema.data ? estadoCierre(sistema.data.ultimo_cierre, hoy) : null;
  const elegir = (p: Preset) => { const [d, h] = rango(p, hoy); setDesde(d); setHasta(h); };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="mr-auto text-xl font-semibold">Indicadores</h1>
        {sistema.data && <p className="text-xs text-tinta-suave">{sistema.data.ultimo_cierre ? `Datos al ${fechaLarga(sistema.data.ultimo_cierre.slice(0, 10))}` : "Los datos aún no se han consolidado"}{cierre && cierre.estado !== "bien" && " · atrasados: avisa a quien administra el sistema"}</p>}
      </div>

      <Tarjeta className="space-y-3 p-4" role="search" aria-label="Filtros">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Periodos">
          {PRESETS.map((p) => {
            const [d, h] = rango(p, hoy);
            return <Boton key={p} pequeno variante={d === desde && h === hasta ? "primario" : "secundario"} onClick={() => elegir(p)}>{p}</Boton>;
          })}
          <Boton pequeno variante="secundario" className="ml-auto sm:hidden" aria-expanded={verFiltros} onClick={() => setVerFiltros((v) => !v)}>Filtros{activos > 0 && ` (${activos})`}</Boton>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Entrada etiqueta="Desde" type="date" value={desde} max={hasta} onChange={(e) => e.target.value && setDesde(e.target.value)} />
          <Entrada etiqueta="Hasta" type="date" value={hasta} min={desde} onChange={(e) => e.target.value && setHasta(e.target.value)} />
          <Seleccion className={cn(!verFiltros && "hidden sm:block")} etiqueta="Profesional" value={pro} onChange={(e) => setPro(e.target.value)}>
            <option value="">Todos</option>{profs.data?.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}</Seleccion>
          <Seleccion className={cn(!verFiltros && "hidden sm:block")} etiqueta="Servicio" value={srv} onChange={(e) => setSrv(e.target.value)}>
            <option value="">Todos</option>{servs.data?.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}</Seleccion>
        </div>
      </Tarjeta>

      <Consulta q={resumen}>
        {(s: Resumen) => (<>
          {s.sin_desenlace > 0 && (
            <Aviso tipo="aviso">Hay {s.sin_desenlace} citas pasadas sin desenlace en este periodo; las cifras de esos días están incompletas.{" "}
              <Link to="/bandejas?b=sin-desenlace" className="font-medium underline">Cerrarlas</Link></Aviso>)}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 [&>*:last-child]:col-span-2 lg:[&>*:last-child]:col-span-1">
            <Clave titulo="Inasistencia" valor={s.inasistencia} anterior={s.anterior?.inasistencia} mejorSiSube={false} ayuda="No asistió ÷ (atendidas + no asistió). Menos es mejor." />
            <Clave titulo="Asistencia" valor={s.asistencia} anterior={s.anterior?.asistencia} mejorSiSube ayuda="Atendidas ÷ (atendidas + no asistió + canceladas). No cuenta las reprogramadas ni las que aún no tienen desenlace." />
            <Clave titulo="Confirmación" valor={s.confirmacion} anterior={s.anterior?.confirmacion} mejorSiSube ayuda="Citas que el paciente confirmó ÷ citas con recordatorio enviado." />
          </div>
          {s.desde_anterior && <p className="-mt-3 text-xs text-tinta-suave">Comparado con el periodo anterior: {s.desde_anterior} a {s.hasta_anterior}.</p>}

          <section aria-label="Qué requiere acción" className="grid grid-cols-3 gap-2 sm:gap-3">
            <Contador numero={riesgo.data?.length} cargando={riesgo.isPending} etiqueta="Tratamientos sin próxima cita" alAbrir={() => setLista("riesgo")} />
            <Contador numero={faltas.data?.length} cargando={faltas.isPending} etiqueta="Pacientes que faltaron 2+ veces" alAbrir={() => setLista("faltas")} />
            <Link to="/bandejas?b=sin-desenlace" className="rounded-[var(--radius-tarjeta)] border border-linea bg-papel p-3 hover:bg-zinc-50 sm:p-4">
              <span className="block text-xl font-semibold tabular-nums sm:text-2xl">{s.sin_desenlace}</span>
              <span className="block text-xs leading-snug text-tinta-suave sm:text-sm">Citas sin desenlace</span>
            </Link>
          </section>

          <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2 [&>*]:min-w-0">
            <Consulta q={porPro}>{(d) => <TablaDimension titulo="Por profesional" columna="Profesional" filas={d} alAbrir={(r) => setFila({ dim: "profesional", fila: r })} />}</Consulta>
            <Consulta q={porSrv}>{(d) => <TablaDimension titulo="Por servicio" columna="Servicio" filas={d} alAbrir={(r) => setFila({ dim: "servicio", fila: r })} />}</Consulta>
          </div>
          <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2 [&>*]:min-w-0">
            <Recordatorios f={f} fallidos={fallidos} />
            <DiaHora f={f} />
          </div>

          <details className="rounded-[var(--radius-tarjeta)] border border-linea bg-papel p-4">
            <summary className="cursor-pointer text-sm font-semibold">Más indicadores</summary>
            <div className="mt-4 space-y-4">
              <Consulta q={tendencia}>{(d) => {
                const pend: Pendiente[] = d.filter((p) => p.sin_desenlace > 0).map((p) => ({ fecha: p.fecha, sin: p.sin_desenlace, datos: p.atendidas + p.no_asistio > 0 }));
                return (
                  <Tarjeta className="p-4">
                    <h3 className="mb-3 text-sm font-semibold">Inasistencia por semana</h3>
                    {d.length === 0 ? <Vacio titulo="Sin datos en el periodo" /> : (
                      <div className="h-56" role="img" aria-label="Inasistencia por semana"><ResponsiveContainer width="100%" height="100%">
                        <LineChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="fecha" /><YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                          <Tooltip formatter={(v: unknown) => (typeof v === "number" ? pct(v) : "sin datos")} /><Line type="monotone" dataKey="inasistencia" name="Inasistencia" stroke={AZUL} strokeWidth={2} dot /></LineChart>
                      </ResponsiveContainer></div>)}
                    {pend.length > 0 && <ul className="mt-2 space-y-0.5 text-xs text-tinta-suave">{pend.map((p) => (
                      <li key={p.fecha}>Semana del {p.fecha}: {p.datos ? "cifra incompleta" : "sin datos"} ({p.sin} {p.sin === 1 ? "cita" : "citas"} sin desenlace)</li>))}</ul>}
                  </Tarjeta>);
              }}</Consulta>

              <Consulta q={motivos}>{(d) => (
                <Tarjeta className="p-4">
                  <h3 className="mb-3 text-sm font-semibold">Motivos de cancelación</h3>
                  {d.length === 0 ? <Vacio titulo="Sin cancelaciones en el periodo" /> : (
                    <ul className="space-y-2">{d.map((m) => (
                      <li key={m.motivo} className="text-sm">
                        <div className="flex justify-between gap-3"><span>{m.motivo}</span><span className="tabular-nums">{m.cancelaciones}{m.tardias > 0 && <span className="text-tinta-suave"> · {m.tardias} tardías</span>}</span></div>
                        <div className="mt-1 h-2 rounded bg-zinc-100"><div className="h-2 rounded bg-sky-500" style={{ width: `${(m.cancelaciones / d[0].cancelaciones) * 100}%` }} /></div>
                      </li>))}</ul>)}
                </Tarjeta>)}</Consulta>

              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                <Cifra titulo="Ocupación" valor={pct(s.ocupacion)} aplica={s.capacidad_aplica} ayuda="Minutos atendidos ÷ minutos de horario sin bloqueos." />
                <Cifra titulo="Cancelaciones" valor={s.cancelaciones} detalle={`${s.cancelaciones_tardias} tardías`} ayuda="Citas canceladas en el periodo." />
                <Cifra titulo="Canceladas que se reagendaron" valor={pct(s.recuperacion)} ayuda="Cancelaciones que terminaron en una cita nueva ÷ total de cancelaciones." />
                <Cifra titulo="Cupos liberados por cancelaciones" valor={s.cupos_liberados} aplica={s.capacidad_aplica} ayuda="Espacios que quedaron libres cuando se canceló una cita." />
                <Cifra titulo="…tomados por otro paciente" valor={s.cupos_ocupados_oferta} aplica={s.capacidad_aplica} detalle={`${s.cupos_ocupados_agendamiento} por agendamiento`} ayuda="Cupos liberados que otro paciente tomó al adelantar su cita desde la lista de espera." />
                <Cifra titulo="…quedaron vacíos" valor={s.cupos_vacios} aplica={s.capacidad_aplica} ayuda="Cupos liberados que nadie ocupó." />
              </div>

              <Consulta q={tiempo}>{(d) => (
                <Tarjeta className="space-y-2 p-4">
                  <h3 className="text-sm font-semibold">Días entre citas atendidas</h3>
                  {d.por_servicio.length === 0 ? <p className="text-sm text-tinta-suave">Sin datos en el periodo.</p> : (
                    <ul className="text-sm">{d.por_servicio.map((x) => <li key={x.servicio} className="flex justify-between gap-3"><span>{x.servicio}</span><span className="tabular-nums">{x.dias.toFixed(1)} días <span className="text-tinta-suave">({x.pares})</span></span></li>)}</ul>)}
                  <p className="text-sm text-tinta-suave">Promedio por paciente: <b>{d.por_paciente_dias === null ? "—" : `${d.por_paciente_dias.toFixed(1)} días`}</b></p>
                </Tarjeta>)}</Consulta>
            </div>
          </details>
        </>)}
      </Consulta>

      <ListaContador cual={lista} alCerrar={() => setLista(null)} f={f} />
      <CitasPerdidas fila={fila?.fila ?? null} dimension={fila?.dim ?? "profesional"} f={f} alCerrar={() => setFila(null)} />
    </div>
  );
}
