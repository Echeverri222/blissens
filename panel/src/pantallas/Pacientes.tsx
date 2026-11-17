import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BellOff } from "lucide-react";
import { api, ApiError } from "@/api/cliente";
import { useAccion } from "@/api/consultas";
import type { FichaCompleta } from "@/api/tipos";
import { ESTADOS } from "@/lib/estados";
import { fechaDe, fechaHora, fechaLarga, horaDe } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { Confirmar, EtiquetaEstado, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta, Vacio } from "@/ui/vistas";
import { BuscarPaciente } from "./Agendar";
import { useNavigate } from "react-router-dom";

export function Pacientes() {
  const nav = useNavigate();
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-xl font-semibold">Pacientes</h1>
      <Tarjeta className="p-4"><BuscarPaciente alElegir={(p) => nav(`/pacientes/${p.id}`)} /></Tarjeta>
    </div>
  );
}

const APARTADOS = ["Citas e historial", "Seguimientos", "Mensajes", "Reversibles"] as const;

export function Ficha() {
  const id = Number(useParams().id);
  const q = useQuery({ queryKey: ["ficha", id], queryFn: () => api.pacientes.ficha(id), enabled: Number.isFinite(id) });
  const [apartado, setApartado] = useState<(typeof APARTADOS)[number]>("Citas e historial");
  return (
    <Consulta q={q}>
      {(f) => (
        <div className="space-y-4">
          <Link to="/pacientes" className="text-sm underline">← Buscar otro paciente</Link>
          <Tarjeta className="flex flex-wrap items-start justify-between gap-3 p-4">
            <div>
              <h1 className="text-xl font-semibold">{f.paciente.nombres} {f.paciente.apellidos}</h1>
              <p className="text-sm text-tinta-suave">Documento {f.paciente.documento ?? "—"} · {f.paciente.celular ?? "sin celular"}{f.paciente.correo ? ` · ${f.paciente.correo}` : ""}</p>
              {!f.paciente.acepta_mensajes && (
                <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-sm font-medium text-amber-950"><BellOff className="size-4" aria-hidden />Dado de baja de mensajes automáticos</p>
              )}
            </div>
            <Link to={`/agendar?paciente=${f.paciente.id}`} className="rounded-[var(--radius-control)] bg-marca px-4 py-2 text-sm font-medium text-white">Agendar cita</Link>
          </Tarjeta>
          <div role="tablist" aria-label="Apartados de la ficha" className="flex gap-1 overflow-x-auto">
            {APARTADOS.map((a) => (
              <button key={a} role="tab" aria-selected={a === apartado} onClick={() => setApartado(a)}
                className={cn("shrink-0 rounded-full border px-3 py-1.5 text-sm font-medium", a === apartado ? "border-marca bg-marca text-white" : "border-linea bg-papel hover:bg-zinc-50")}>{a}</button>
            ))}
          </div>
          <div role="tabpanel" aria-label={apartado}>
            {apartado === "Citas e historial" && <CitasEHistorial f={f} />}
            {apartado === "Seguimientos" && <Seguimientos f={f} />}
            {apartado === "Mensajes" && <Mensajes f={f} />}
            {apartado === "Reversibles" && <Reversibles f={f} />}
          </div>
        </div>
      )}
    </Consulta>
  );
}

function CitasEHistorial({ f }: { f: FichaCompleta }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section aria-label="Citas" className="space-y-2">
        <h2 className="text-sm font-semibold">Citas</h2>
        {f.citas.length === 0 ? <Tarjeta><Vacio titulo="Sin citas">Este paciente aún no tiene citas registradas.</Vacio></Tarjeta> : (
          <Tarjeta className="divide-y divide-linea">{f.citas.map((c) => (
            <Link key={c.id} to={`/agenda?fecha=${c.dia}&cita=${c.id}`} className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-zinc-50">
              <span className="min-w-0 flex-1"><b className="capitalize">{fechaLarga(c.dia)}</b>{c.inicio ? ` · ${horaDe(c.inicio)}` : " · sin hora"}<br /><span className="text-tinta-suave">{c.servicio} · {c.profesional}</span></span>
              <EtiquetaEstado estado={c.estado} /></Link>))}</Tarjeta>)}
      </section>
      <section aria-label="Historial de cambios" className="space-y-2">
        <h2 className="text-sm font-semibold">Historial de cambios</h2>
        {f.historial.length === 0 ? <Tarjeta><Vacio titulo="Sin movimientos" /></Tarjeta> : (
          <Tarjeta className="divide-y divide-linea">{f.historial.map((h) => (
            <div key={h.id} className="px-4 py-2.5 text-sm">
              <p className="font-medium">Cita {h.cita_id}: {h.estado_anterior ? `${ESTADOS[h.estado_anterior].texto} → ` : "Creada: "}{ESTADOS[h.estado_nuevo].texto}</p>
              <p className="text-tinta-suave">{fechaHora(h.momento)} · {h.usuario ?? h.actor}{h.revertido && " · revertido"}</p>
            </div>))}</Tarjeta>)}
      </section>
    </div>
  );
}

function Seguimientos({ f }: { f: FichaCompleta }) {
  if (f.casos.length === 0) return <Tarjeta><Vacio titulo="Sin seguimientos">No hay casos de seguimiento (cancelaciones, inasistencias o recuperación) para este paciente.</Vacio></Tarjeta>;
  return (
    <div className="space-y-3">{f.casos.map((c) => (
      <Tarjeta key={c.id} className="p-4 text-sm">
        <p className="font-medium">{c.tipo.replace(/_/g, " ")} · {c.estado}{c.escalado && " · escalado"}</p>
        <p className="text-tinta-suave">Abierto {fechaHora(c.abierto_en)}{c.cerrado_en ? ` · cerrado ${fechaHora(c.cerrado_en)}` : ""}</p>
        {c.intentos.length > 0 && <ul className="mt-2 list-inside list-disc">{c.intentos.map((i) => <li key={i.numero}>Intento {i.numero} por {i.canal}: {(i.resultado ?? "pendiente").replace(/_/g, " ")} ({fechaHora(i.momento)})</li>)}</ul>}
      </Tarjeta>))}</div>
  );
}

function Mensajes({ f }: { f: FichaCompleta }) {
  if (f.mensajes.length === 0) return <Tarjeta><Vacio titulo="Sin mensajes">Aún no hay conversación con este paciente.</Vacio></Tarjeta>;
  return (
    <Tarjeta className="space-y-2 bg-zinc-50 p-4">
      {f.mensajes.map((m) => (
        <div key={m.id} className={cn("flex", m.direccion === "saliente" ? "justify-start" : "justify-end")}>
          <div className={cn("max-w-[80%] rounded-2xl px-3 py-2 text-sm", m.direccion === "saliente" ? "bg-papel border border-linea" : "bg-marca text-white")}>
            <p className="mb-0.5 text-xs opacity-70">{m.direccion === "saliente" ? "Clínica" : "Paciente"} · {fechaHora(m.momento)}</p>
            <p className="whitespace-pre-wrap">{m.texto}</p>
            {m.botones.length > 0 && <p className="mt-1 text-xs opacity-70">Botones: {m.botones.map((b) => (b as { title?: string }).title).filter(Boolean).join(", ")}</p>}
          </div>
        </div>))}
    </Tarjeta>
  );
}

function Reversibles({ f }: { f: FichaCompleta }) {
  const m = useAccion((h: number) => api.citas.revertir(h), { ok: "Cambio revertido" });
  const lista = f.historial.filter((h) => h.reversible);
  return (
    <div className="space-y-3">
      <p className="text-sm text-tinta-suave">Revertir compensa el cambio con un evento nuevo; nunca borra historial. Solo procede si el rango original sigue libre.</p>
      {m.error instanceof ApiError && <Aviso tipo="aviso">{m.error.mensaje}</Aviso>}
      {lista.length === 0 ? <Tarjeta><Vacio titulo="Nada para revertir">Solo se puede revertir el último movimiento de una cita cuando el sistema lo permite.</Vacio></Tarjeta> : (
        <Tarjeta className="divide-y divide-linea">{lista.map((h) => (
          <div key={h.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
            <span className="flex-1">Cita {h.cita_id}: {h.estado_anterior ? ESTADOS[h.estado_anterior].texto : ""} → <b>{ESTADOS[h.estado_nuevo].texto}</b><br />
              <span className="text-tinta-suave">{fechaHora(h.momento)} · {h.usuario ?? h.actor} · <Link className="underline" to={`/agenda?fecha=${fechaDe(h.momento)}&cita=${h.cita_id}`}>Abrir cita</Link></span></span>
            <Confirmar etiqueta="Revertir" pequeno pregunta="Se compensará este cambio con un movimiento nuevo." alConfirmar={() => m.mutate(h.id)} deshabilitado={m.isPending} />
          </div>))}</Tarjeta>)}
    </div>
  );
}
