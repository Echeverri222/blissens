import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/api/cliente";
import { useAccion, useBloqueos, useProfesionales } from "@/api/consultas";
import { aIso, fechaDe, fechaHora, horaDe, sumarDias } from "@/lib/tiempo";
import { comportamientoDe } from "@/lib/errores";
import { useSesion } from "@/sesion/Sesion";
import { Boton, Casilla, Confirmar, Entrada, Seleccion } from "@/ui/controles";
import { Aviso, Consulta, Vacio } from "@/ui/vistas";

/** Formulario de bloqueo, usado por ambos roles. La auxiliar elige el profesional; el especialista usa el suyo. */
export function FormularioBloqueo({ profesionalId, alCrear, alAbrirCita }: {
  profesionalId?: number | null; alCrear?: () => void; alAbrirCita?: (citaId: number, fecha: string) => void;
}) {
  const { sesion, hoy } = useSesion();
  const aux = sesion.rol === "auxiliar";
  const profs = useProfesionales();
  const [pro, setPro] = useState<string>(profesionalId ? String(profesionalId) : "");
  const [fecha, setFecha] = useState(hoy);
  const [varios, setVarios] = useState(false);
  const [hasta, setHasta] = useState(hoy);
  const [completo, setCompleto] = useState(false);
  const [ini, setIni] = useState("09:00");
  const [fin, setFin] = useState("10:00");
  const [motivo, setMotivo] = useState("");

  const m = useAccion(api.bloqueos.crear, { ok: "Bloqueo creado", alExito: () => { setMotivo(""); alCrear?.(); } });

  function enviar(e: FormEvent) {
    e.preventDefault();
    const ultimo = varios ? hasta : fecha;
    const inicio = completo ? aIso(fecha, "00:00") : aIso(fecha, ini);
    const final = completo ? aIso(sumarDias(ultimo, 1), "00:00") : aIso(ultimo, fin);
    m.mutate({ profesional_id: aux ? Number(pro) || null : null, inicio, fin: final, motivo });
  }
  const err = m.error instanceof ApiError ? m.error : null;
  const conflicto = err && comportamientoDe(err.codigo) === "conflicto_bloqueo";
  return (
    <form onSubmit={enviar} className="space-y-3" aria-label="Bloquear tiempo">
      {aux && (
        <Seleccion etiqueta="Profesional" value={pro} onChange={(e) => setPro(e.target.value)} required>
          <option value="">Elige un profesional</option>
          {profs.data?.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
        </Seleccion>
      )}
      <Entrada etiqueta={varios ? "Desde el día" : "Día"} type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} required />
      <Casilla etiqueta="Varios días" checked={varios} onChange={(e) => setVarios(e.target.checked)} />
      {varios && <Entrada etiqueta="Hasta el día" type="date" value={hasta} min={fecha} onChange={(e) => setHasta(e.target.value)} required />}
      <Casilla etiqueta="Día completo" checked={completo} onChange={(e) => setCompleto(e.target.checked)} />
      {!completo && (
        <div className="grid grid-cols-2 gap-3">
          <Entrada etiqueta="Hora de inicio" type="time" value={ini} onChange={(e) => setIni(e.target.value)} required />
          <Entrada etiqueta="Hora de fin" type="time" value={fin} onChange={(e) => setFin(e.target.value)} required />
        </div>
      )}
      <Entrada etiqueta="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej.: capacitación, vacaciones" maxLength={120} />
      {err && !conflicto && <Aviso>{err.mensaje}</Aviso>}
      {err && conflicto && (
        <Aviso tipo="aviso">
          <p className="font-medium">{err.mensaje}</p>
          <ul className="mt-2 space-y-1">
            {err.citas?.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2">
                <span>{fechaHora(c.inicio)} · {c.paciente} · {c.servicio}</span>
                {aux && alAbrirCita && <Boton pequeno variante="secundario" onClick={() => alAbrirCita(c.id, fechaDe(c.inicio))}>Abrir cita</Boton>}
              </li>
            ))}
          </ul>
          {!aux && <p className="mt-2">Pide a recepción que las mueva y vuelve a intentarlo.</p>}
        </Aviso>
      )}
      <Boton type="submit" className="w-full" disabled={m.isPending || (aux && !pro)}>Crear bloqueo</Boton>
    </form>
  );
}

/** Bloqueos de las próximas seis semanas de un profesional (ninguno si la auxiliar no eligió profesional). */
export function ListaBloqueos({ profesionalId }: { profesionalId?: number }) {
  const { hoy } = useSesion();
  const q = useBloqueos(hoy, sumarDias(hoy, 41), profesionalId);
  const eliminar = useAccion((id: number) => api.bloqueos.eliminar(id), { ok: "Bloqueo eliminado" });
  return (
    <Consulta q={q}>
      {(lista) => lista.length === 0
        ? <Vacio titulo="No hay bloqueos en las próximas seis semanas">Cuando bloquees tiempo (vacaciones, reuniones) aparecerá aquí y dejará de ofrecerse a los pacientes.</Vacio>
        : (
          <ul className="divide-y divide-linea rounded-xl border border-linea bg-papel">
            {lista.map((b) => (
              <li key={b.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{fechaHora(b.inicio)} → {fechaDe(b.inicio) === fechaDe(b.fin) ? horaDe(b.fin) : fechaHora(b.fin)}</p>
                  <p className="truncate text-tinta-suave">{b.motivo || "Sin motivo"}{b.creado_por ? ` · ${b.creado_por}` : ""}</p>
                </div>
                <Confirmar etiqueta="Eliminar" pequeno variante="fantasma" pregunta="El tiempo volverá a ofrecerse a los pacientes." alConfirmar={() => eliminar.mutate(b.id)} />
              </li>
            ))}
          </ul>
        )}
    </Consulta>
  );
}

/** Para la auxiliar: formulario y lista del profesional elegido. */
export function PanelBloqueos({ profesionalId, alAbrirCita }: { profesionalId?: number | null; alAbrirCita?: (citaId: number, fecha: string) => void }) {
  const { sesion } = useSesion();
  const [listado, setListado] = useState<number | undefined>(profesionalId ?? undefined);
  return (
    <div className="space-y-6">
      <FormularioBloqueo profesionalId={profesionalId} alAbrirCita={alAbrirCita} />
      {sesion.rol === "especialista" && <ListaBloqueos />}
      {sesion.rol === "auxiliar" && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Bloqueos vigentes</h3>
          <ProfesionalDeLista valor={listado} alCambiar={setListado} />
          {listado !== undefined && <ListaBloqueos profesionalId={listado} />}
        </div>
      )}
    </div>
  );
}

function ProfesionalDeLista({ valor, alCambiar }: { valor?: number; alCambiar: (v?: number) => void }) {
  const profs = useProfesionales();
  return (
    <Seleccion etiqueta="Ver bloqueos de" value={valor ?? ""} onChange={(e) => alCambiar(e.target.value ? Number(e.target.value) : undefined)}>
      <option value="">Elige un profesional</option>
      {profs.data?.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
    </Seleccion>
  );
}
