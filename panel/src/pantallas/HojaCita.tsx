import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/cliente";
import { useAccion, useCita, useMotivos } from "@/api/consultas";
import type { CitaDetalle } from "@/api/tipos";
import { fechaDe, fechaHora, fechaLarga, horaDe } from "@/lib/tiempo";
import { ESTADOS } from "@/lib/estados";
import { useSesion } from "@/sesion/Sesion";
import { AreaTexto, Boton, Confirmar, EtiquetaEstado, Hoja, Seleccion } from "@/ui/controles";
import { Aviso, Consulta } from "@/ui/vistas";
import { SelectorEspacios } from "./Espacios";
import { BotonConfirmo, EnlacesContacto } from "./Llamar";

const etiqueta = (e: keyof typeof ESTADOS) => ESTADOS[e].texto;
const ACTOR = { paciente: "Paciente", auxiliar: "Recepción", especialista: "Especialista", sistema: "Sistema" } as const;

export function HojaCita({ id, alCerrar, alMover }: { id: number | null; alCerrar: () => void; alMover: (citaId: number, fecha: string) => void }) {
  const q = useCita(id);
  return (
    <Hoja abierta={id !== null} alCerrar={alCerrar} titulo="Detalle de la cita" descripcion={q.data ? `${q.data.paciente.nombre}` : undefined}>
      <Consulta q={q}>{(c) => <Contenido c={c} alCerrar={alCerrar} alMover={alMover} />}</Consulta>
    </Hoja>
  );
}

function Contenido({ c, alCerrar, alMover }: { c: CitaDetalle; alCerrar: () => void; alMover: (citaId: number, fecha: string) => void }) {
  const { sesion } = useSesion();
  const aux = sesion.rol === "auxiliar";
  const [modo, setModo] = useState<"cancelar" | "fecha" | null>(null);

  const desenlace = useAccion((d: "atendida" | "no_asistio") => api.citas.desenlace(c.id, d), {
    ok: (_, d) => (d === "atendida" ? "Marcada como atendida" : "Marcada como no asistió"),
  });
  const revertir = useAccion((h: number) => api.citas.revertir(h), { ok: "Cambio revertido" });
  const errRev = revertir.error instanceof ApiError ? revertir.error : null;
  const errDes = desenlace.error instanceof ApiError ? desenlace.error : null;

  return (
    <div className="space-y-5">
      <section aria-label="Datos de la cita" className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-xl font-semibold">{c.paciente.nombre}</h3>
            <div className="mt-1"><EnlacesContacto celular={c.paciente.celular} /></div>
          </div>
          <EtiquetaEstado estado={c.estado} />
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-tinta-suave">Servicio</dt><dd>{c.servicio}</dd>
          <dt className="text-tinta-suave">Profesional</dt><dd>{c.profesional}</dd>
          <dt className="text-tinta-suave">Fecha</dt><dd className="first-letter:uppercase">{fechaLarga(c.dia)}</dd>
          <dt className="text-tinta-suave">Hora</dt><dd>{c.inicio && c.fin ? `${horaDe(c.inicio)} – ${horaDe(c.fin)}` : "Sin hora"}</dd>
        </dl>
        {aux && <Link to={`/pacientes/${c.paciente.id}`} className="inline-block text-sm font-medium underline">Ver ficha del paciente</Link>}
      </section>

      {(errDes) && <Aviso tipo="aviso">{errDes.mensaje}</Aviso>}
      {c.acciones.length > 0 && (
        <section aria-label="Acciones" className="space-y-3">
          <h4 className="text-sm font-semibold">Acciones</h4>
          <div className="flex flex-wrap gap-2">
            {c.acciones.includes("desenlace") && (<>
              <Confirmar etiqueta="Atendida" variante="primario" deshabilitado={desenlace.isPending} si="Sí, fue atendida"
                pregunta={<><b className="text-tinta">{c.paciente.nombre}</b> asistió a esta cita. Se cierra como atendida.</>}
                alConfirmar={() => desenlace.mutate("atendida")} />
              <Confirmar etiqueta="No asistió" variante="secundario" deshabilitado={desenlace.isPending}
                pregunta="Se abrirá un seguimiento y el paciente recibirá un mensaje para reagendar."
                alConfirmar={() => desenlace.mutate("no_asistio")} />
            </>)}
            {c.acciones.includes("confirmar") && <BotonConfirmo citaId={c.id} paciente={c.paciente.nombre} inicio={c.inicio} pequeno={false} />}
            {c.acciones.includes("cambiar_fecha") && <Boton variante="secundario" onClick={() => setModo(modo === "fecha" ? null : "fecha")}>Cambiar fecha</Boton>}
            {c.acciones.includes("cancelar") && <Boton variante="secundario" onClick={() => setModo(modo === "cancelar" ? null : "cancelar")}>Cancelar cita</Boton>}
          </div>
          {modo === "cancelar" && <FormCancelar id={c.id} alListo={() => { setModo(null); }} />}
          {modo === "fecha" && <FormFecha c={c} alListo={(nueva, fecha) => { setModo(null); alMover(nueva, fecha); }} />}
        </section>
      )}

      <section aria-label="Historial" className="space-y-2">
        <h4 className="text-sm font-semibold">Historial</h4>
        {errRev && <Aviso tipo="aviso">{errRev.mensaje}</Aviso>}
        <ol className="space-y-2">
          {[...c.historial].reverse().map((h) => (
            <li key={h.id} className="rounded-lg border border-linea px-3 py-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  {h.estado_anterior ? `${etiqueta(h.estado_anterior)} → ${etiqueta(h.estado_nuevo)}` : `Creada como ${etiqueta(h.estado_nuevo).toLowerCase()}`}
                </span>
                {h.reversible && (
                  <Confirmar etiqueta="Revertir" pequeno pregunta="Se compensará este cambio con un movimiento nuevo; el historial nunca se borra."
                    alConfirmar={() => revertir.mutate(h.id)} deshabilitado={revertir.isPending} />
                )}
              </div>
              <p className="text-tinta-suave">{fechaHora(h.momento)} · {h.usuario ?? ACTOR[h.actor]}{h.usuario ? ` (${ACTOR[h.actor].toLowerCase()})` : ""}</p>
              {h.detalle && <p>{h.detalle}</p>}
              {h.revertido && <p className="text-xs text-tinta-suave">Este cambio fue revertido.</p>}
            </li>
          ))}
        </ol>
      </section>
      <Boton variante="fantasma" className="w-full" onClick={alCerrar}>Cerrar</Boton>
    </div>
  );
}

function FormCancelar({ id, alListo }: { id: number; alListo: () => void }) {
  const motivos = useMotivos();
  const [motivo, setMotivo] = useState("");
  const [texto, setTexto] = useState("");
  const m = useAccion((v: { motivo: number; texto: string }) => api.citas.cancelar(id, v.motivo, v.texto), { ok: "Cita cancelada", alExito: alListo });
  return (
    <div className="space-y-3 rounded-xl border border-linea bg-zinc-50 p-3">
      {m.error instanceof ApiError && <Aviso>{m.error.mensaje}</Aviso>}
      <Seleccion etiqueta="Motivo de la cancelación" value={motivo} onChange={(e) => setMotivo(e.target.value)}>
        <option value="">Elige un motivo</option>
        {motivos.data?.map((x) => <option key={x.id} value={x.id}>{x.etiqueta}</option>)}
      </Seleccion>
      <AreaTexto etiqueta="Detalle (opcional)" value={texto} onChange={(e) => setTexto(e.target.value)} />
      <Confirmar etiqueta="Cancelar la cita" variante="peligro" deshabilitado={!motivo || m.isPending}
        pregunta="El cupo se libera y el paciente recibirá un mensaje para reagendar."
        alConfirmar={() => m.mutate({ motivo: Number(motivo), texto })} />
    </div>
  );
}

function FormFecha({ c, alListo }: { c: CitaDetalle; alListo: (nuevaId: number, fecha: string) => void }) {
  const [inicio, setInicio] = useState<string | null>(null);
  const m = useAccion((i: string) => api.citas.cambiarFecha(c.id, i), {
    ok: "Fecha cambiada", alExito: (r, i) => alListo(r.cita_id, fechaDe(i)),
  });
  return (
    <div className="space-y-3 rounded-xl border border-linea bg-zinc-50 p-3">
      {m.error instanceof ApiError && <Aviso>{m.error.mensaje}</Aviso>}
      <p className="text-sm text-tinta-suave">Espacios disponibles de {c.servicio} con {c.profesional}.</p>
      <SelectorEspacios profesionalId={c.profesional_id} servicioId={c.servicio_id} valor={inicio} alCambiar={setInicio} />
      <Boton disabled={!inicio || m.isPending} onClick={() => inicio && m.mutate(inicio)}>Cambiar a este espacio</Boton>
    </div>
  );
}
