import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/cliente";
import { CADA_MINUTO, useAccion, useConteoBandejas } from "@/api/consultas";
import type { ConteoBandejas, ResultadoGestion } from "@/api/tipos";
import { fechaDe, fechaHora } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { Boton, Confirmar, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta, Vacio } from "@/ui/vistas";

const BANDEJAS: { clave: keyof ConteoBandejas; slug: string; texto: string; ayuda: string; vacio: string }[] = [
  { clave: "no_confirmadas", slug: "no-confirmadas", texto: "No confirmadas", ayuda: "Citas próximas sin confirmación, ordenadas por cercanía. Llama primero a las más urgentes.", vacio: "Todas las citas próximas están confirmadas." },
  { clave: "seguimientos", slug: "seguimientos", texto: "Seguimientos", ayuda: "Casos abiertos y escalados. Registra aquí lo que hayas gestionado por teléfono.", vacio: "No hay seguimientos abiertos." },
  { clave: "en_riesgo", slug: "en-riesgo", texto: "Pacientes en riesgo", ayuda: "Tratamientos activos sin cita futura y con más días que el umbral desde la última cita.", vacio: "Ningún paciente con tratamiento a medias está en riesgo." },
  { clave: "cupos_libres", slug: "cupos-libres", texto: "Cupos libres", ayuda: "Espacios liberados por cancelaciones que aún no se han ocupado, y a quién se ofrecieron.", vacio: "No hay cupos liberados pendientes." },
  { clave: "sin_desenlace", slug: "sin-desenlace", texto: "Sin desenlace", ayuda: "Citas pasadas que quedaron sin desenlace. Ciérralas para no dejar huecos en los datos.", vacio: "No hay citas pasadas sin cerrar." },
  { clave: "sin_interpretar", slug: "sin-interpretar", texto: "Mensajes sin interpretar", ayuda: "Mensajes que el paciente escribió y el sistema no supo interpretar. Respóndele por tu cuenta y márcalo como resuelto.", vacio: "No hay mensajes pendientes." },
  { clave: "contactos", slug: "contactos", texto: "Contactos", ayuda: "Alguien intentó agendar con un documento ya registrado pero otro celular. Llámalo para validar.", vacio: "No hay solicitudes de contacto." },
  { clave: "dados_de_baja", slug: "dados-de-baja", texto: "Dados de baja", ayuda: "Citas próximas de pacientes que pidieron no recibir mensajes automáticos: confírmalas por teléfono.", vacio: "No hay citas próximas de pacientes dados de baja." },
];

const ENLACE = "font-medium underline";
const verCita = (id: number, inicio: string) => `/agenda?fecha=${fechaDe(inicio)}&cita=${id}`;

export function Bandejas() {
  const [params, setParams] = useSearchParams();
  const conteo = useConteoBandejas();
  const actual = BANDEJAS.find((b) => b.slug === params.get("b")) ?? BANDEJAS[0];
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Bandejas de trabajo</h1>
      <div role="tablist" aria-label="Bandejas" className="flex gap-1 overflow-x-auto pb-1">
        {BANDEJAS.map((b) => (
          <button key={b.slug} role="tab" aria-selected={b === actual} onClick={() => setParams({ b: b.slug })}
            className={cn("flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium", b === actual ? "border-marca bg-marca text-white" : "border-linea bg-papel hover:bg-zinc-50")}>
            {b.texto}<span className={cn("rounded-full px-1.5 text-xs tabular-nums", b === actual ? "bg-white text-marca" : "bg-zinc-200")}>{conteo.data?.[b.clave] ?? "–"}</span>
          </button>
        ))}
      </div>
      <p className="text-sm text-tinta-suave">{actual.ayuda}</p>
      <div role="tabpanel" aria-label={actual.texto}><Contenido slug={actual.slug} vacio={actual.vacio} /></div>
    </div>
  );
}

function Lista<T extends object>({ clave, fn, vacio, fila }: { clave: string; fn: () => Promise<T[]>; vacio: string; fila: (x: T) => ReactNode }) {
  const q = useQuery({ queryKey: ["bandeja", clave], queryFn: fn, refetchInterval: CADA_MINUTO });
  return (
    <Consulta q={q}>
      {(l) => l.length === 0 ? <Tarjeta><Vacio titulo={vacio} /></Tarjeta> : <Tarjeta className="divide-y divide-linea">{l.map(fila)}</Tarjeta>}
    </Consulta>
  );
}

const Fila = ({ children }: { children: ReactNode }) => <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-sm">{children}</div>;
const Paciente = ({ id, nombre, celular }: { id: number; nombre: string; celular?: string | null }) => (
  <div className="min-w-40 flex-1"><Link className={ENLACE} to={`/pacientes/${id}`}>{nombre}</Link>{celular && <p className="text-tinta-suave">{celular}</p>}</div>
);
const limpio = (s: string) => s.replace(/_/g, " ");

function Contenido({ slug, vacio }: { slug: string; vacio: string }) {
  const resultado = useAccion((v: { id: number; r: ResultadoGestion; detalle: string }) => api.bandejas.gestionSeguimiento(v.id, v.r, v.detalle), { ok: "Registrado" });
  const desenlace = useAccion((v: { id: number; d: "atendida" | "no_asistio" }) => api.citas.desenlace(v.id, v.d), { ok: (_, v) => (v.d === "atendida" ? "Marcada como atendida" : "Marcada como no asistió") });
  const mensaje = useAccion((id: number) => api.bandejas.gestionarMensaje(id), { ok: "Mensaje resuelto" });
  const contacto = useAccion((id: number) => api.bandejas.gestionarContacto(id), { ok: "Solicitud gestionada" });
  const errores = [resultado.error, desenlace.error].find((e) => e instanceof ApiError) as ApiError | undefined;
  const aviso = errores && <Aviso tipo="aviso">{errores.mensaje}</Aviso>;
  switch (slug) {
    case "no-confirmadas":
      return <Lista clave={slug} fn={api.bandejas.noConfirmadas} vacio={vacio} fila={(r) => (
        <Fila key={r.cita_id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><Paciente id={r.paciente_id} nombre={r.paciente} celular={r.celular} />
          <span className="text-tinta-suave">{r.profesional}</span><Link className={ENLACE} to={verCita(r.cita_id, r.inicio)}>Abrir cita</Link></Fila>)} />;
    case "seguimientos":
      return <>{aviso}<Lista clave={slug} fn={api.bandejas.seguimientos} vacio={vacio} fila={(r) => (
        <Fila key={r.id}><Paciente id={r.paciente_id} nombre={r.paciente} celular={r.celular ?? "sin celular"} />
          <span>{limpio(r.tipo)}{r.escalado && <b className="ml-1 rounded bg-rose-100 px-1.5 text-xs text-rose-900">ESCALADO</b>}</span>
          <span className="text-tinta-suave">{r.intentos} intentos · último: {limpio(r.ultimo ?? "pendiente")}</span>
          <div className="ml-auto flex gap-1.5">
            <Boton pequeno variante="secundario" onClick={() => resultado.mutate({ id: r.id, r: "acepto", detalle: "Gestión telefónica" })}>Aceptó</Boton>
            <Boton pequeno variante="secundario" onClick={() => resultado.mutate({ id: r.id, r: "rechazo", detalle: "Gestión telefónica" })}>Rechazó</Boton>
            <Boton pequeno variante="secundario" onClick={() => resultado.mutate({ id: r.id, r: "sin_respuesta", detalle: "Llamada sin respuesta" })}>Sin respuesta</Boton>
          </div></Fila>)} /></>;
    case "en-riesgo":
      return <Lista clave={slug} fn={api.bandejas.enRiesgo} vacio={vacio} fila={(r) => (
        <Fila key={r.tratamiento_id}><Paciente id={r.paciente_id} nombre={r.paciente} /><span>Última cita: {r.ultima_cita}</span>
          <span>{r.dias_sin_cita} días sin cita</span><span className="text-tinta-suave">Mensaje de recuperación: {r.caso_id ? "enviado" : "aún no"}</span>
          <Link className={cn(ENLACE, "ml-auto")} to={`/agendar?paciente=${r.paciente_id}`}>Agendar</Link></Fila>)} />;
    case "cupos-libres":
      return <Lista clave={slug} fn={api.bandejas.cuposLibres} vacio={vacio} fila={(r) => (
        <Fila key={r.id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><span>{r.profesional}</span>
          <span className="text-tinta-suave">{limpio(r.estado)} · {limpio(r.causa)}</span><span className="text-tinta-suave">Ofertado a: {r.ofrecido_a ?? "—"}</span></Fila>)} />;
    case "sin-desenlace":
      return <>{aviso}<Lista clave={slug} fn={api.bandejas.sinDesenlace} vacio={vacio} fila={(r) => (
        <Fila key={r.cita_id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><Paciente id={r.paciente_id} nombre={r.paciente} />
          <span className="text-tinta-suave">{r.profesional}</span><Link className={ENLACE} to={verCita(r.cita_id, r.inicio)}>Abrir cita</Link>
          <div className="ml-auto flex gap-1.5">
            <Boton pequeno variante="secundario" onClick={() => desenlace.mutate({ id: r.cita_id, d: "atendida" })}>Atendida</Boton>
            <Confirmar etiqueta="No asistió" pequeno pregunta="Se abrirá un seguimiento y el paciente recibirá un mensaje para reagendar." alConfirmar={() => desenlace.mutate({ id: r.cita_id, d: "no_asistio" })} />
          </div></Fila>)} /></>;
    case "sin-interpretar":
      return <Lista clave={slug} fn={api.bandejas.sinInterpretar} vacio={vacio} fila={(r) => (
        <Fila key={r.id}><Paciente id={r.paciente_id} nombre={r.paciente} /><span className="flex-[2] italic">“{r.texto}”</span>
          <span className="text-tinta-suave">{fechaHora(r.momento)}</span><Boton pequeno variante="secundario" onClick={() => mensaje.mutate(r.id)}>Resuelto</Boton></Fila>)} />;
    case "contactos":
      return <Lista clave={slug} fn={api.bandejas.contactos} vacio={vacio} fila={(r) => (
        <Fila key={r.id}><span className="w-32 font-medium">{r.documento}</span><span className="w-32">{r.celular}</span><span className="flex-1 text-tinta-suave">{r.nota}</span>
          <span className="text-tinta-suave">{fechaHora(r.momento)}</span><Boton pequeno variante="secundario" onClick={() => contacto.mutate(r.id)}>Gestionada</Boton></Fila>)} />;
    default:
      return <Lista clave={slug} fn={api.bandejas.dadosDeBaja} vacio={vacio} fila={(r) => (
        <Fila key={r.cita_id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><Paciente id={r.paciente_id} nombre={r.paciente} celular={r.celular} />
          <Link className={ENLACE} to={verCita(r.cita_id, r.inicio)}>Abrir cita</Link></Fila>)} />;
  }
}
