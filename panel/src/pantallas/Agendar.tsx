import { useCallback, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/cliente";
import { useAccion, useProfesionales, useServicios } from "@/api/consultas";
import type { ColorSemaforo, PacienteResumen, Segmento } from "@/api/tipos";
import { COLORES_SEMAFORO, SEMAFOROS } from "@/lib/estados";
import { fechaDe, fechaHora } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { AltoValor, Boton, Casilla, Entrada, Prospecto, Seleccion, Semaforo, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta, Vacio } from "@/ui/vistas";
import { SelectorEspacios } from "./Espacios";

/** Flujo de tres pasos: paciente → servicio y profesional → día y hora. */
export function Agendar() {
  const [params] = useSearchParams();
  const pacienteInicial = Number(params.get("paciente")) || null;
  const [paciente, setPaciente] = useState<{ id: number; nombre: string } | null>(null);
  const [servicio, setServicio] = useState("");
  const [pro, setPro] = useState("");
  const [inicio, setInicio] = useState<string | null>(null);
  const [creada, setCreada] = useState<{ id: number; inicio: string } | null>(null);
  const servicios = useServicios();
  const profs = useProfesionales();
  const ficha = useQuery({ queryKey: ["paciente-min", pacienteInicial], queryFn: () => api.pacientes.ficha(pacienteInicial!), enabled: pacienteInicial !== null && !paciente });
  const elegido = paciente ?? (ficha.data ? { id: ficha.data.paciente.id, nombre: `${ficha.data.paciente.nombres} ${ficha.data.paciente.apellidos}`.trim() } : null);

  const agendar = useAccion((d: { paciente_id: number; profesional_id: number; servicio_id: number; inicio: string }) => api.citas.agendar(d), {
    ok: "Cita agendada", alExito: (r, d) => setCreada({ id: r.cita_id, inicio: d.inicio }),
  });
  const alElegir = useCallback((i: string | null) => setInicio(i), []);

  if (creada) {
    return (
      <Tarjeta className="mx-auto max-w-lg space-y-3 p-6 text-center">
        <h1 className="text-xl font-semibold">Cita agendada</h1>
        <p className="text-sm text-tinta-suave">{elegido?.nombre} · {fechaHora(creada.inicio)}. La confirmación se envió por WhatsApp.</p>
        <div className="flex justify-center gap-2">
          <Link className="rounded-[var(--radius-control)] bg-marca px-4 py-2 text-sm font-medium text-white" to={`/agenda?fecha=${fechaDe(creada.inicio)}&cita=${creada.id}`}>Ir a la cita</Link>
          <Boton variante="secundario" onClick={() => { setCreada(null); setInicio(null); setPaciente(null); setServicio(""); setPro(""); }}>Agendar otra</Boton>
        </div>
      </Tarjeta>
    );
  }
  const err = agendar.error instanceof ApiError ? agendar.error : null;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-xl font-semibold">Agendar una cita</h1>
      <Paso n={1} titulo="Paciente">
        {elegido
          ? <div className="flex items-center justify-between gap-3"><p className="font-medium">{elegido.nombre}</p><Boton variante="secundario" pequeno onClick={() => { setPaciente(null); setInicio(null); if (pacienteInicial) window.history.replaceState(null, "", "/panel/agendar"); }}>Cambiar</Boton></div>
          : <BuscarPaciente alElegir={(p) => setPaciente(p)} />}
      </Paso>
      <Paso n={2} titulo="Servicio y profesional" deshabilitado={!elegido}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Seleccion etiqueta="Servicio" value={servicio} onChange={(e) => { setServicio(e.target.value); setInicio(null); }}>
            <option value="">Elige un servicio</option>
            {servicios.data?.map((s) => <option key={s.id} value={s.id}>{s.nombre} ({s.duracion_min} min)</option>)}
          </Seleccion>
          <Seleccion etiqueta="Profesional" value={pro} onChange={(e) => { setPro(e.target.value); setInicio(null); }}>
            <option value="">Elige un profesional</option>
            {profs.data?.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </Seleccion>
        </div>
      </Paso>
      <Paso n={3} titulo="Día y hora" deshabilitado={!elegido || !servicio || !pro}>
        {err && <div className="mb-3"><Aviso tipo={err.codigo === "espacio_ocupado" ? "aviso" : "error"}>{err.mensaje}{err.codigo === "espacio_ocupado" && " Estos son los espacios actualizados."}</Aviso></div>}
        <SelectorEspacios profesionalId={pro ? Number(pro) : null} servicioId={servicio ? Number(servicio) : null} valor={inicio} alCambiar={alElegir} />
        <Boton className="mt-4" disabled={!elegido || !inicio || agendar.isPending}
          onClick={() => elegido && inicio && agendar.mutate({ paciente_id: elegido.id, profesional_id: Number(pro), servicio_id: Number(servicio), inicio })}>
          Agendar cita{inicio ? ` · ${fechaHora(inicio)}` : ""}
        </Boton>
      </Paso>
    </div>
  );
}

function Paso({ n, titulo, deshabilitado, children }: { n: number; titulo: string; deshabilitado?: boolean; children: React.ReactNode }) {
  return (
    <Tarjeta className={`p-4 ${deshabilitado ? "opacity-50" : ""}`} aria-disabled={deshabilitado}>
      <h2 className="mb-3 flex items-center gap-2 text-base font-semibold"><span className="flex size-6 items-center justify-center rounded-full bg-marca text-xs text-white">{n}</span>{titulo}</h2>
      <div inert={deshabilitado}>{children}</div>
    </Tarjeta>
  );
}

/** El texto de búsqueda vive solo en memoria: puede ser un documento o un celular y no va en la dirección. */
const FILTROS: { valor: Segmento | null; texto: string }[] = [
  { valor: null, texto: "Todos" }, { valor: "internacional", texto: "Internacionales" }, { valor: "deportista", texto: "Deportistas" }];
const TOPE_BUSQUEDA = 50;

/** Con `conFiltros`, la recepción puede quedarse con los internacionales o los deportistas; sin texto, los lista a todos. */
type DatosIniciales = { nombres?: string; apellidos?: string; celular?: string };

/** `inicial` precarga la búsqueda (y la hace) y el formulario de paciente nuevo, p. ej. desde una solicitud del sitio. */
export function BuscarPaciente({ alElegir, conFiltros = false, inicial }: {
  alElegir: (p: { id: number; nombre: string }) => void; conFiltros?: boolean; inicial?: { texto: string; paciente?: DatosIniciales };
}) {
  const [texto, setTexto] = useState(inicial?.texto ?? "");
  const [buscado, setBuscado] = useState(inicial?.texto.trim() ?? "");
  const [segmento, setSegmento] = useState<Segmento | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const [fallecidos, setFallecidos] = useState(false);
  const [color, setColor] = useState<ColorSemaforo | null>(null);
  const activo = buscado.length > 0 || segmento !== null;
  const q = useQuery({ queryKey: ["pacientes", "buscar", buscado, segmento, fallecidos, color], queryFn: () => api.pacientes.buscar(buscado, segmento ?? undefined, fallecidos, color ?? undefined), enabled: activo });
  const nombre = (p: PacienteResumen) => `${p.nombres} ${p.apellidos}`.trim();
  return (
    <div className="space-y-3">
      <form role="search" className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); setBuscado(texto.trim()); }}>
        <Entrada etiqueta="Buscar por nombre, documento, celular o correo" value={texto} onChange={(e) => setTexto(e.target.value)} className="flex-1" />
        <Boton type="submit">Buscar</Boton>
      </form>
      {conFiltros && (
        <div role="group" aria-label="Filtrar por segmento" className="flex flex-wrap gap-1.5">
          {FILTROS.map((f) => (
            <button key={f.texto} type="button" aria-pressed={segmento === f.valor} onClick={() => setSegmento(f.valor)}
              className={cn("rounded-full border px-3 py-1 text-sm font-medium", segmento === f.valor ? "border-marca bg-marca text-white" : "border-linea bg-papel hover:bg-zinc-50")}>{f.texto}</button>
          ))}
          <Seleccion etiqueta="Estado" value={color ?? ""} onChange={(e) => setColor((e.target.value || null) as ColorSemaforo | null)}>
            <option value="">Todos los estados</option>
            {COLORES_SEMAFORO.map((c) => <option key={c} value={c}>{SEMAFOROS[c].texto}</option>)}
          </Seleccion>
          <Casilla etiqueta="Incluir fallecidos" checked={fallecidos} onChange={(e) => setFallecidos(e.target.checked)} />
        </div>
      )}
      {activo && (
        <Consulta q={q}>
          {(lista) => lista.length === 0
            ? <Vacio titulo="No encontramos pacientes">{segmento && !buscado ? "Nadie tiene esa marca todavía. Se marca desde la ficha del paciente." : "Revisa el texto o crea el paciente nuevo."}</Vacio>
            : <>
              <ul className="divide-y divide-linea rounded-xl border border-linea">{lista.map((p) => (
                <li key={p.id}><button className="flex w-full flex-wrap items-center justify-between gap-x-3 gap-y-1 px-3 py-2.5 text-left text-sm hover:bg-zinc-50" onClick={() => alElegir({ id: p.id, nombre: nombre(p) })}>
                  <span className="flex flex-wrap items-center gap-2 font-medium">{nombre(p)}<Prospecto etapa={p.etapa} /><Semaforo semaforo={p.etapa === "prospecto" ? null : p.semaforo} noContactar={p.no_contactar} /><AltoValor internacional={p.internacional} deportista={p.deportista} /></span>
                  <span className="text-tinta-suave">{p.documento ?? "sin documento"} · {p.celular ?? "sin celular"}</span></button></li>
              ))}</ul>
              {lista.length >= TOPE_BUSQUEDA && <p className="text-sm text-tinta-suave">Se muestran los primeros {TOPE_BUSQUEDA}. Escribe un nombre para afinar.</p>}
            </>}
        </Consulta>
      )}
      <div>
        {!nuevo ? <Boton variante="fantasma" pequeno onClick={() => setNuevo(true)}>¿No está? Crear paciente nuevo</Boton>
          : <FormularioPaciente alCrear={alElegir} alCancelar={() => setNuevo(false)} inicial={inicial?.paciente} />}
      </div>
    </div>
  );
}

/** También lo usa la tarjeta del asistente: el documento, el celular y la autorización se escriben aquí, nunca en el chat. */
export function FormularioPaciente({ alCrear, alCancelar, inicial, boton = "Crear y elegir", cancelar = "Cancelar" }: {
  alCrear: (p: { id: number; nombre: string }) => void; alCancelar: () => void; inicial?: DatosIniciales; boton?: string; cancelar?: string;
}) {
  const [v, setV] = useState({ nombres: "", apellidos: "", documento: "", celular: "", consentimiento: false, ...inicial });
  const m = useAccion(api.pacientes.crear, { ok: "Paciente creado", alExito: (r, d) => alCrear({ id: r.paciente_id, nombre: `${d.nombres} ${d.apellidos}`.trim() }) });
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) => setV({ ...v, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const enviar = (e: FormEvent) => { e.preventDefault(); m.mutate(v); };
  const celularMalo = m.error instanceof ApiError && m.error.mensaje === "Celular no válido";
  return (
    <form onSubmit={enviar} className="space-y-3 rounded-xl border border-linea bg-zinc-50 p-3" aria-label="Paciente nuevo">
      <h3 className="text-sm font-semibold">Paciente nuevo</h3>
      {m.error instanceof ApiError && !celularMalo && <Aviso>{m.error.mensaje}</Aviso>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Entrada etiqueta="Nombres" value={v.nombres} onChange={set("nombres")} required />
        <Entrada etiqueta="Apellidos" value={v.apellidos} onChange={set("apellidos")} />
        <Entrada etiqueta="Documento" inputMode="numeric" value={v.documento} onChange={set("documento")} required />
        <div>
          <Entrada etiqueta="Celular" inputMode="tel" value={v.celular} onChange={set("celular")} required aria-invalid={celularMalo} />
          {celularMalo && <p role="alert" className="mt-1 text-sm text-rose-800">Celular no válido</p>}
        </div>
      </div>
      <Casilla etiqueta="El paciente autoriza el tratamiento de sus datos y recibir mensajes de la clínica" checked={v.consentimiento} onChange={set("consentimiento")} />
      <div className="flex gap-2"><Boton type="submit" disabled={m.isPending}>{boton}</Boton><Boton variante="secundario" onClick={alCancelar}>{cancelar}</Boton></div>
    </form>
  );
}
