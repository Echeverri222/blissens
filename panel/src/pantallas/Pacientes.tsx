import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BellOff, Ban } from "lucide-react";
import { api, ApiError } from "@/api/cliente";
import { CADA_MINUTO, useAccion, useAgenda } from "@/api/consultas";
import type { FichaCompleta, Identificacion, MotivoNoContactar, Segmentos } from "@/api/tipos";
import { ESTADOS } from "@/lib/estados";
import { fechaDe, fechaHora, fechaLarga, horaDe, sumarDias } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { useSesion } from "@/sesion/Sesion";
import { AltoValor, Boton, Casilla, Confirmar, Entrada, EtiquetaEstado, Prospecto, Seleccion, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta, Vacio } from "@/ui/vistas";
import { BuscarPaciente } from "./Agendar";
import { useNavigate } from "react-router-dom";

export function Pacientes() {
  const nav = useNavigate();
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-xl font-semibold">Pacientes</h1>
      <Tarjeta className="p-4"><BuscarPaciente conFiltros alElegir={(p) => nav(`/pacientes/${p.id}`)} /></Tarjeta>
      <CitasProximas />
      <ListaPacientes titulo="En riesgo de abandonar el tratamiento" ayuda="Tienen un tratamiento a medias y llevan tiempo sin cita. Agéndalos para que no lo dejen." clave="en-riesgo" fn={api.bandejas.enRiesgo} vacio="Nadie está en riesgo ahora."
        fila={(r) => ({ id: r.tratamiento_id, pacienteId: r.paciente_id, nombre: r.paciente, detalle: `${r.dias_sin_cita} días sin cita`, agendar: true })} />
      <ListaPacientes titulo="Dados de baja de mensajes" ayuda="Pidieron no recibir mensajes automáticos; sus citas se confirman por teléfono." clave="dados-de-baja" fn={api.bandejas.dadosDeBaja} vacio="Ningún paciente con cita próxima está dado de baja."
        fila={(r) => ({ id: r.cita_id, pacienteId: r.paciente_id, nombre: r.paciente, detalle: `Cita ${fechaHora(r.inicio)}` })} />
    </div>
  );
}

const ACTIVAS = new Set(["programada", "confirmada", "no_confirmada"]);

function CitasProximas() {
  const { hoy } = useSesion();
  const manana = sumarDias(hoy, 1);
  const q = useAgenda(hoy, manana);
  return (
    <section aria-label="Citas de hoy y mañana" className="space-y-2">
      <h2 className="text-sm font-semibold">Con cita hoy y mañana</h2>
      <Consulta q={q}>
        {(a) => {
          const citas = a.citas.filter((c) => ACTIVAS.has(c.estado) || c.estado === "atendida").sort((x, y) => (x.inicio ?? "").localeCompare(y.inicio ?? ""));
          if (citas.length === 0) return <Tarjeta><Vacio titulo="Sin citas hoy ni mañana" /></Tarjeta>;
          return (
            <Tarjeta className="divide-y divide-linea">{citas.map((c) => (
              <Link key={c.id} to={`/pacientes/${c.paciente_id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm hover:bg-zinc-50">
                <span className="w-28 shrink-0 text-tinta-suave">{c.dia === hoy ? "Hoy" : "Mañana"}{c.inicio ? ` · ${horaDe(c.inicio)}` : ""}</span>
                <span className="min-w-0 flex-1"><b>{c.paciente}</b><br /><span className="text-tinta-suave">{c.servicio} · {c.profesional}</span></span>
                <EtiquetaEstado estado={c.estado} /></Link>))}</Tarjeta>
          );
        }}
      </Consulta>
    </section>
  );
}

function ListaPacientes<T extends object>({ titulo, ayuda, clave, fn, vacio, fila }: {
  titulo: string; ayuda: string; clave: string; fn: () => Promise<T[]>; vacio: string;
  fila: (x: T) => { id: number; pacienteId: number; nombre: string; detalle: string; agendar?: boolean };
}) {
  const q = useQuery({ queryKey: ["bandeja", clave], queryFn: fn, refetchInterval: CADA_MINUTO });
  return (
    <section aria-label={titulo} className="space-y-2">
      <div><h2 className="text-sm font-semibold">{titulo}</h2><p className="text-sm text-tinta-suave">{ayuda}</p></div>
      <Consulta q={q}>
        {(l) => l.length === 0 ? <Tarjeta><Vacio titulo={vacio} /></Tarjeta> : (
          <Tarjeta className="divide-y divide-linea">{l.map((x) => {
            const f = fila(x);
            return (
              <div key={f.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
                <Link to={`/pacientes/${f.pacienteId}`} className="min-w-40 flex-1 font-medium underline">{f.nombre}</Link>
                <span className="text-tinta-suave">{f.detalle}</span>
                {f.agendar && <Link to={`/agendar?paciente=${f.pacienteId}`} className="font-medium underline">Agendar</Link>}
              </div>);
          })}</Tarjeta>)}
      </Consulta>
    </section>
  );
}

const PARENTESCOS: Record<string, string> = { hijo: "hijo o hija", pareja: "pareja", padre: "madre o padre", otro: "otro familiar" };

/** Quién gestiona las citas de este paciente desde su enlace y de quiénes las gestiona él (docs/prd-familia.md). */
function Familia({ f }: { f: FichaCompleta }) {
  const { responsable, familiares, menor } = f.familia;
  if (!responsable && familiares.length === 0 && !menor) return null;
  return (
    <div className="mt-1 space-y-0.5 text-sm text-tinta-suave">
      {menor && <p><span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-tinta">Menor de edad</span></p>}
      {responsable && (
        <p>Sus citas las gestiona <Link to={`/pacientes/${responsable.id}`} className="font-medium text-tinta underline">{responsable.nombre}</Link>
          {responsable.parentesco ? ` · parentesco: ${PARENTESCOS[responsable.parentesco] ?? responsable.parentesco}` : ""}</p>
      )}
      {familiares.length > 0 && (
        <p>Gestiona las citas de {familiares.map((x, i) => (
          <span key={x.id}>{i > 0 && ", "}<Link to={`/pacientes/${x.id}`} className="font-medium text-tinta underline">{x.nombre}</Link>
            {x.parentesco ? ` (${PARENTESCOS[x.parentesco] ?? x.parentesco}${x.menor ? ", menor" : ""})` : ""}</span>
        ))}</p>
      )}
    </div>
  );
}

const APARTADOS = ["Citas e historial", "Seguimientos", "Mensajes", "Se pueden deshacer"] as const;

export function Ficha() {
  const id = Number(useParams().id);
  const q = useQuery({ queryKey: ["ficha", id], queryFn: () => api.pacientes.ficha(id), enabled: Number.isFinite(id) });
  const [apartado, setApartado] = useState<(typeof APARTADOS)[number]>("Citas e historial");
  const porResponder = q.data ? mensajesPorResponder(q.data).length : 0;
  return (
    <Consulta q={q}>
      {(f) => (
        <div className="space-y-4">
          <Link to="/pacientes" className="text-sm underline">← Buscar otro paciente</Link>
          <Tarjeta className="flex flex-wrap items-start justify-between gap-3 p-4">
            <div>
              <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">{f.paciente.nombres} {f.paciente.apellidos}
                <Prospecto etapa={f.paciente.etapa} /><AltoValor internacional={f.paciente.internacional} deportista={f.paciente.deportista} /></h1>
              <p className="text-sm text-tinta-suave">Documento {f.paciente.documento ?? "—"} · {f.paciente.celular ?? "sin celular"}{f.paciente.correo ? ` · ${f.paciente.correo}` : ""}</p>
              <Familia f={f} />
              <MarcasAltoValor f={f} />
              <NoContactar f={f} />
              {!f.paciente.acepta_mensajes && (
                <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-sm font-medium text-amber-950"><BellOff className="size-4" aria-hidden />Dado de baja de mensajes automáticos</p>
              )}
            </div>
            {f.paciente.etapa === "paciente" && (
              <Link to={`/agendar?paciente=${f.paciente.id}`} className="rounded-[var(--radius-control)] bg-marca px-4 py-2 text-sm font-medium text-white">Agendar cita</Link>
            )}
          </Tarjeta>
          {f.paciente.etapa === "prospecto" && <PasarAPaciente f={f} />}
          <div role="tablist" aria-label="Apartados de la ficha" className="flex gap-1 overflow-x-auto">
            {APARTADOS.map((a) => (
              <button key={a} role="tab" aria-selected={a === apartado} onClick={() => setApartado(a)}
                className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium", a === apartado ? "border-marca bg-marca text-white" : "border-linea bg-papel hover:bg-zinc-50")}>
                {a}
                {a === "Mensajes" && porResponder > 0 && (
                  <span aria-label={`${porResponder} por responder`} className="rounded-full bg-red-600 px-1.5 text-xs font-semibold tabular-nums text-white">{porResponder}</span>
                )}
              </button>
            ))}
          </div>
          <div role="tabpanel" aria-label={apartado}>
            {apartado === "Citas e historial" && <CitasEHistorial f={f} />}
            {apartado === "Seguimientos" && <Seguimientos f={f} />}
            {apartado === "Mensajes" && <Mensajes f={f} />}
            {apartado === "Se pueden deshacer" && <Reversibles f={f} />}
          </div>
        </div>
      )}
    </Consulta>
  );
}

/** Un prospecto pasa a paciente cuando llega a la clínica y la recepción le registra el documento. */
function PasarAPaciente({ f }: { f: FichaCompleta }) {
  const [documento, setDocumento] = useState("");
  const [celular, setCelular] = useState("");
  const m = useAccion((d: Identificacion) => api.pacientes.identificar(f.paciente.id, d), { ok: "Documento registrado: ya es paciente" });
  return (
    <form aria-label="Registrar documento" className="space-y-3 rounded-xl border border-linea bg-zinc-50 p-4"
      onSubmit={(e) => { e.preventDefault(); m.mutate({ documento, celular: celular.trim() || null }); }}>
      <div><h2 className="text-sm font-semibold">Prospecto: aún sin documento</h2>
        <p className="text-sm text-tinta-suave">Escribió desde el sitio web. Cuando llegue a la clínica, registra su documento para poder agendarle citas presenciales.</p></div>
      {m.error instanceof ApiError && <Aviso>{m.error.mensaje}</Aviso>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Entrada etiqueta="Documento" inputMode="numeric" value={documento} onChange={(e) => setDocumento(e.target.value)} required />
        <Entrada etiqueta={f.paciente.celular ? "Celular (opcional, para corregirlo)" : "Celular"} inputMode="tel" value={celular} onChange={(e) => setCelular(e.target.value)} required={!f.paciente.celular} />
      </div>
      <Boton type="submit" disabled={m.isPending}>Registrar documento</Boton>
    </form>
  );
}

export const MOTIVOS_NO_CONTACTAR: Record<MotivoNoContactar, string> = {
  queja: "Queja activa", cobro: "Cobro jurídico", fallecido: "Fallecido", otro: "Otro motivo",
};

/** «No contactar» (R6): la clínica deja de escribirle y de llamarle. Se marca y se quita con confirmación y queda en el registro. */
function NoContactar({ f }: { f: FichaCompleta }) {
  const p = f.paciente;
  const [motivo, setMotivo] = useState<MotivoNoContactar>("queja");
  const [nota, setNota] = useState("");
  const marcar = useAccion(() => api.pacientes.marcarNoContactar(p.id, { motivo, nota: nota.trim() || null }), { ok: "Marcado como «No contactar»", alExito: () => setNota("") });
  const quitar = useAccion(() => api.pacientes.quitarNoContactar(p.id), { ok: "Ya se le puede contactar" });
  if (p.no_contactar) {
    return (
      <div className="mt-2 space-y-1 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-950" role="status">
        <p className="inline-flex items-center gap-1.5 font-semibold"><Ban className="size-4" aria-hidden />No contactar: {MOTIVOS_NO_CONTACTAR[p.no_contactar]}</p>
        <p>{p.no_contactar === "fallecido" ? "No recibe ningún mensaje y no aparece al agendar." : "No se le escribe ni se le llama por iniciativa de la clínica; solo se le responde si él escribe."}
          {p.no_contactar_nota ? ` Nota: ${p.no_contactar_nota}` : ""}</p>
        <Confirmar etiqueta="Quitar la marca" pequeno titulo="¿Quitar «No contactar»?" si="Sí, quitar" deshabilitado={quitar.isPending}
          pregunta="Volverá a recibir mensajes y a aparecer en las listas de trabajo." alConfirmar={() => quitar.mutate(undefined)} />
      </div>
    );
  }
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer font-medium underline">No contactar</summary>
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        <Seleccion etiqueta="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value as MotivoNoContactar)}>
          {(Object.keys(MOTIVOS_NO_CONTACTAR) as MotivoNoContactar[]).map((m) => <option key={m} value={m}>{MOTIVOS_NO_CONTACTAR[m]}</option>)}
        </Seleccion>
        <Entrada etiqueta="Nota corta (sin datos clínicos)" maxLength={200} value={nota} onChange={(e) => setNota(e.target.value)} />
      </div>
      <div className="mt-2">
        <Confirmar etiqueta="Marcar «No contactar»" pequeno variante="peligro" titulo="¿Marcar «No contactar»?" si="Sí, marcar" deshabilitado={marcar.isPending}
          pregunta={<>La clínica dejará de escribirle y de llamarle ({MOTIVOS_NO_CONTACTAR[motivo].toLowerCase()}); se cerrarán sus seguimientos abiertos{motivo === "fallecido" ? " y dejará de aparecer al agendar" : ""}. Podrás quitar la marca después.</>}
          alConfirmar={() => marcar.mutate(undefined)} />
      </div>
    </details>
  );
}

const ORIGEN_MARCA = {
  sitio_en: "Marcado como internacional porque se registró en el sitio en inglés. Revísalo.",
  importacion: "Marcado desde el software de la clínica.",
  sitio_web: "Marcado como internacional porque escribió desde el sitio web.",
  recepcion: null,
} as const;

/** Internacional y deportista de alto nivel: los segmentos que la clínica quiere atender primero. Se guardan al marcar. */
function MarcasAltoValor({ f }: { f: FichaCompleta }) {
  const p = f.paciente;
  // Lo último que se guardó manda mientras la ficha siga siendo la de antes de guardar: así marcar una casilla tras
  // otra no deshace la primera. En cuanto llega la ficha nueva, manda ella.
  const desdeFicha = { internacional: p.internacional, deportista: p.deportista };
  const [guardado, setGuardado] = useState<{ valor: Segmentos; antes: Segmentos } | null>(null);
  const m = useAccion((s: Segmentos) => api.pacientes.segmentos(p.id, s), {
    ok: "Marca guardada",
    alExito: (d) => setGuardado({ valor: { internacional: d.internacional, deportista: d.deportista }, antes: desdeFicha }),
  });
  const fichaVieja = guardado && guardado.antes.internacional === desdeFicha.internacional && guardado.antes.deportista === desdeFicha.deportista;
  const vigente = m.isPending ? m.variables! : fichaVieja ? guardado.valor : desdeFicha;
  const cambiar = (s: Partial<Segmentos>) => m.mutate({ ...vigente, ...s });
  const nota = p.segmento_origen ? ORIGEN_MARCA[p.segmento_origen] : null;
  return (
    <fieldset className="mt-2 text-sm" disabled={m.isPending}>
      <legend className="sr-only">Paciente de alto valor</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <Casilla etiqueta="Internacional" checked={vigente.internacional} onChange={(e) => cambiar({ internacional: e.target.checked })} />
        <Casilla etiqueta="Deportista de alto nivel" checked={vigente.deportista} onChange={(e) => cambiar({ deportista: e.target.checked })} />
      </div>
      {nota && (vigente.internacional || vigente.deportista) && <p className="text-tinta-suave">{nota}</p>}
    </fieldset>
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
        <p className="font-medium">{c.tipo.replace(/_/g, " ")} · {c.estado}{c.escalado && " · necesita llamada"}</p>
        <p className="text-tinta-suave">Abierto {fechaHora(c.abierto_en)}{c.cerrado_en ? ` · cerrado ${fechaHora(c.cerrado_en)}` : ""}</p>
        {c.intentos.length > 0 && <ul className="mt-2 list-inside list-disc">{c.intentos.map((i) => <li key={i.numero}>Intento {i.numero} por {i.canal}: {(i.resultado ?? "pendiente").replace(/_/g, " ")} ({fechaHora(i.momento)})</li>)}</ul>}
      </Tarjeta>))}</div>
  );
}

/** Mensajes del paciente que nadie ha respondido ni descartado: los mismos que cuenta la bandeja «Mensajes». */
function mensajesPorResponder(f: FichaCompleta) {
  return f.mensajes.filter((m) => m.direccion === "entrante" && !m.gestionado);
}

function Mensajes({ f }: { f: FichaCompleta }) {
  const gestionar = useAccion((id: number) => api.bandejas.gestionarMensaje(id), { ok: "Mensaje marcado como respondido" });
  if (f.mensajes.length === 0) return <Tarjeta><Vacio titulo="Sin mensajes">Aún no hay conversación con este paciente.</Vacio></Tarjeta>;
  const pendientes = mensajesPorResponder(f).length;
  return (
    <div className="space-y-3">
    {pendientes > 0 && (
      <Aviso tipo="aviso">{pendientes === 1 ? "Hay 1 mensaje del paciente por responder." : `Hay ${pendientes} mensajes del paciente por responder.`} Respóndele por WhatsApp o por teléfono y márcalo como respondido.</Aviso>
    )}
    <Tarjeta className="space-y-2 bg-zinc-50 p-4">
      {f.mensajes.map((m) => (
        <div key={m.id} className={cn("flex", m.direccion === "saliente" ? "justify-start" : "justify-end")}>
          <div className={cn("max-w-[80%] rounded-2xl px-3 py-2 text-sm", m.direccion === "saliente" ? "bg-papel border border-linea" : "bg-marca text-white")}>
            <p className="mb-0.5 text-xs opacity-70">{m.direccion === "saliente" ? "Clínica" : "Paciente"} · {fechaHora(m.momento)}</p>
            <p className="whitespace-pre-wrap">{m.texto}</p>
            {m.botones.length > 0 && <p className="mt-1 text-xs opacity-70">Botones: {m.botones.map((b) => (b as { title?: string }).title).filter(Boolean).join(", ")}</p>}
            {m.direccion === "entrante" && !m.gestionado && (
              <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-white/20 pt-2">
                <span className="rounded-full bg-red-600 px-2 py-0.5 text-xs font-semibold">Por responder</span>
                <Confirmar etiqueta="Marcar como respondido" pequeno pregunta="¿Ya le respondiste? El mensaje sale de los pendientes."
                  alConfirmar={() => gestionar.mutate(m.id)} deshabilitado={gestionar.isPending} />
              </div>
            )}
          </div>
        </div>))}
    </Tarjeta>
    </div>
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
