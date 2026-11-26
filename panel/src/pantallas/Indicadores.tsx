import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, ApiError } from "@/api/cliente";
import { useAccion, useProfesionales, useServicios } from "@/api/consultas";
import type { FiltrosIndicadores } from "@/api/tipos";
import { sumarDias } from "@/lib/tiempo";
import { useSesion } from "@/sesion/Sesion";
import { Boton, Entrada, Seleccion, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta, Vacio } from "@/ui/vistas";

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)} %`);
const AZUL = "#3b9fe0", AGUA = "#3fbfb0", LILA = "#b07cf0", DURAZNO = "#e8826b";

function Tarjetita({ titulo, valor, ayuda, detalle }: { titulo: string; valor: string | number; ayuda: string; detalle?: string }) {
  return (
    <Tarjeta className="p-4">
      <p className="text-sm text-tinta-suave" title={ayuda}>{titulo}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{valor}</p>
      {detalle && <p className="text-xs text-tinta-suave">{detalle}</p>}
      <p className="mt-2 text-xs text-tinta-suave">{ayuda}</p>
    </Tarjeta>
  );
}

function Grafica({ titulo, vacio, children }: { titulo: string; vacio: boolean; children: React.ReactNode }) {
  return (
    <Tarjeta className="p-4">
      <h3 className="mb-3 text-sm font-semibold">{titulo}</h3>
      {vacio ? <Vacio titulo="Sin datos en el periodo">Cuando haya citas o cancelaciones en el rango elegido, aparecerán aquí.</Vacio>
        : <div className="h-64" role="img" aria-label={titulo}><ResponsiveContainer width="100%" height="100%">{children as React.ReactElement}</ResponsiveContainer></div>}
    </Tarjeta>
  );
}

const porcentaje = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(1)} %` : "—");

export function Indicadores() {
  const { hoy } = useSesion();
  const [desde, setDesde] = useState(sumarDias(hoy, -60));
  const [hasta, setHasta] = useState(hoy);
  const [pro, setPro] = useState("");
  const [srv, setSrv] = useState("");
  const profs = useProfesionales();
  const servs = useServicios();
  const f: FiltrosIndicadores = { desde, hasta, profesional_id: pro ? Number(pro) : undefined, servicio_id: srv ? Number(srv) : undefined };
  const clave = [desde, hasta, pro, srv];
  const resumen = useQuery({ queryKey: ["ind", "resumen", ...clave], queryFn: () => api.indicadores.resumen(f) });
  const tendencia = useQuery({ queryKey: ["ind", "tendencia", ...clave], queryFn: () => api.indicadores.tendencia(f, "semana") });
  const porPro = useQuery({ queryKey: ["ind", "pro", ...clave], queryFn: () => api.indicadores.porProfesional(f) });
  const porSrv = useQuery({ queryKey: ["ind", "srv", ...clave], queryFn: () => api.indicadores.porServicio(f) });
  const motivos = useQuery({ queryKey: ["ind", "motivos", ...clave], queryFn: () => api.indicadores.motivos(f) });
  const tiempo = useQuery({ queryKey: ["ind", "tiempo", ...clave], queryFn: () => api.indicadores.tiempoEntreCitas(f) });
  const sistema = useQuery({ queryKey: ["sistema"], queryFn: api.sistema });
  const cierre = useAccion(api.indicadores.cierre, { ok: (r) => `Cierre ejecutado (${r.dias} días)` });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Indicadores</h1>
        <p className="text-sm text-tinta-suave">Último cierre diario: <b>{sistema.data?.ultimo_cierre ?? "nunca"}</b></p>
        <Boton variante="secundario" pequeno disabled={cierre.isPending} onClick={() => cierre.mutate(undefined)}>Ejecutar cierre ahora</Boton>
      </div>
      {cierre.error instanceof ApiError && <Aviso>{cierre.error.mensaje}</Aviso>}
      <Tarjeta className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4" role="search" aria-label="Filtros">
        <Entrada etiqueta="Desde" type="date" value={desde} max={hasta} onChange={(e) => e.target.value && setDesde(e.target.value)} />
        <Entrada etiqueta="Hasta" type="date" value={hasta} min={desde} onChange={(e) => e.target.value && setHasta(e.target.value)} />
        <Seleccion etiqueta="Profesional" value={pro} onChange={(e) => setPro(e.target.value)}>
          <option value="">Todos</option>{profs.data?.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}</Seleccion>
        <Seleccion etiqueta="Servicio" value={srv} onChange={(e) => setSrv(e.target.value)}>
          <option value="">Todos</option>{servs.data?.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}</Seleccion>
      </Tarjeta>

      <Consulta q={resumen}>
        {(s) => (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tarjetita titulo="Atención efectiva" valor={pct(s.atencion_efectiva)} ayuda="Citas atendidas ÷ total de citas del periodo" />
            <Tarjetita titulo="Inasistencia" valor={pct(s.inasistencia)} ayuda="No asistió ÷ (atendida + no asistió)" />
            <Tarjetita titulo="Recuperación de cancelaciones" valor={pct(s.recuperacion)} ayuda="Cancelaciones que terminaron en cita nueva ÷ total" />
            <Tarjetita titulo="Confirmación" valor={pct(s.confirmacion)} ayuda="Confirmadas explícitamente ÷ citas con recordatorio enviado" />
            <Tarjetita titulo="Ocupación" valor={pct(s.ocupacion)} ayuda="Minutos atendidos ÷ minutos de horario sin bloqueos" />
            <Tarjetita titulo="Cancelaciones" valor={s.cancelaciones} detalle={`${s.cancelaciones_tardias} tardías`} ayuda="Citas canceladas en el periodo" />
            <Tarjetita titulo="Cupos liberados" valor={s.cupos_liberados} ayuda="Espacios que quedaron libres por cancelaciones" />
            <Tarjetita titulo="Cupos llenados con la lista de espera" valor={s.cupos_ocupados_oferta} detalle={`${s.cupos_ocupados_agendamiento} por agendamiento · ${s.cupos_vacios} vacíos`} ayuda="Cupos que otro paciente tomó al adelantar su cita" />
          </div>
        )}
      </Consulta>

      <div className="grid gap-4 lg:grid-cols-2">
        <Consulta q={tendencia}>{(d) => (
          <div className="lg:col-span-2"><Grafica titulo="Inasistencia por semana" vacio={d.length === 0}>
            <LineChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="fecha" /><YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} /><Tooltip formatter={porcentaje} />
              <Line type="monotone" dataKey="inasistencia" name="Inasistencia" stroke={AZUL} strokeWidth={2} dot /></LineChart></Grafica></div>)}</Consulta>
        <Consulta q={porPro}>{(d) => (
          <Grafica titulo="Inasistencia por profesional" vacio={d.length === 0}><BarChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="nombre" /><YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} />
            <Tooltip formatter={porcentaje} /><Bar dataKey="inasistencia" name="Inasistencia" fill={AGUA} /></BarChart></Grafica>)}</Consulta>
        <Consulta q={porSrv}>{(d) => (
          <Grafica titulo="Inasistencia por servicio" vacio={d.length === 0}><BarChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="nombre" /><YAxis tickFormatter={(v) => `${Math.round(v * 100)}%`} />
            <Tooltip formatter={porcentaje} /><Bar dataKey="inasistencia" name="Inasistencia" fill={LILA} /></BarChart></Grafica>)}</Consulta>
        <Consulta q={motivos}>{(d) => (
          <Grafica titulo="Motivos de cancelación (y cuántas fueron tardías)" vacio={d.length === 0}><BarChart data={d}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="motivo" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
            <Bar dataKey="cancelaciones" name="Cancelaciones" fill={AZUL} /><Bar dataKey="tardias" name="Tardías" fill={DURAZNO} /></BarChart></Grafica>)}</Consulta>
        <Consulta q={tiempo}>{(d) => (<>
          <Grafica titulo="Días promedio entre citas por servicio" vacio={d.por_servicio.length === 0}><BarChart data={d.por_servicio}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="servicio" /><YAxis /><Tooltip />
            <Bar dataKey="dias" name="Días" fill={AGUA} /></BarChart></Grafica>
          <p className="text-sm text-tinta-suave lg:col-span-2">Tiempo promedio entre citas atendidas consecutivas por paciente: <b>{d.por_paciente_dias === null ? "—" : `${d.por_paciente_dias.toFixed(1)} días`}</b></p></>)}</Consulta>
      </div>
    </div>
  );
}
