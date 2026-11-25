import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/cliente";
import { CADA_MINUTO, useAccion, useConteoBandejas } from "@/api/consultas";
import type { ConteoBandejas, ResultadoGestion } from "@/api/tipos";
import { digitosWhatsApp, esSolicitudWeb, leerSolicitudWeb } from "@/lib/solicitudes";
import { fechaDe, fechaHora } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { Boton, Confirmar, Tarjeta } from "@/ui/controles";
import { Aviso, Cargando, Consulta, Vacio } from "@/ui/vistas";

const BANDEJAS: { clave: keyof ConteoBandejas; slug: string; texto: string; ayuda: string; vacio: string }[] = [
  { clave: "no_confirmadas", slug: "no-confirmadas", texto: "No confirmadas", ayuda: "Citas próximas sin confirmación, ordenadas por cercanía. Llama primero a las más urgentes.", vacio: "Todas las citas próximas están confirmadas." },
  { clave: "seguimientos", slug: "seguimientos", texto: "Seguimientos", ayuda: "Casos abiertos y escalados. Registra aquí lo que hayas gestionado por teléfono.", vacio: "No hay seguimientos abiertos." },
  { clave: "en_riesgo", slug: "en-riesgo", texto: "Pacientes en riesgo", ayuda: "Tratamientos activos sin cita futura y con más días que el umbral desde la última cita.", vacio: "Ningún paciente con tratamiento a medias está en riesgo." },
  { clave: "cupos_libres", slug: "cupos-libres", texto: "Cupos libres", ayuda: "Espacios liberados por cancelaciones que aún no se han ocupado, y a quién se ofrecieron.", vacio: "No hay cupos liberados pendientes." },
  { clave: "sin_desenlace", slug: "sin-desenlace", texto: "Citas por cerrar", ayuda: "Citas pasadas que quedaron sin desenlace. Ciérralas para no dejar huecos en los datos.", vacio: "No hay citas pasadas sin cerrar." },
  { clave: "sin_interpretar", slug: "sin-interpretar", texto: "Mensajes por responder", ayuda: "Mensajes que el paciente escribió y el sistema no supo interpretar. Respóndele por tu cuenta y márcalo como resuelto.", vacio: "No hay mensajes pendientes." },
  { clave: "contactos", slug: "contactos", texto: "Contactos y solicitudes", ayuda: "Solicitudes de contacto: personas del sitio web que piden información y quienes intentaron agendar con un documento ya registrado pero otro celular (esas se validan por teléfono).", vacio: "No hay solicitudes de contacto." },
  { clave: "dados_de_baja", slug: "dados-de-baja", texto: "Dados de baja", ayuda: "Citas próximas de pacientes que pidieron no recibir mensajes automáticos: confírmalas por teléfono.", vacio: "No hay citas próximas de pacientes dados de baja." },
];

const ENLACE = "font-medium underline";
const verCita = (id: number, inicio: string) => `/agenda?fecha=${fechaDe(inicio)}&cita=${id}`;

const HOY = { slug: "hoy", texto: "Qué hacer hoy", ayuda: "Todo lo que necesita una llamada o un clic de recepción, de lo más urgente a lo menos urgente. Cada fila te lleva a la bandeja donde se resuelve." };
/** Bandejas que cuentan como "pendientes de hoy". Las demás (en riesgo, cupos libres) son informativas. */
const PENDIENTES_HOY: (keyof ConteoBandejas)[] = ["seguimientos", "contactos", "sin_interpretar", "no_confirmadas", "sin_desenlace", "dados_de_baja"];

export function Bandejas() {
  const [params, setParams] = useSearchParams();
  const conteo = useConteoBandejas();
  const hoy = params.get("b") === null || params.get("b") === HOY.slug;
  const actual = BANDEJAS.find((b) => b.slug === params.get("b")) ?? BANDEJAS[0];
  const pendientesHoy = conteo.data ? PENDIENTES_HOY.reduce((n, k) => n + conteo.data[k], 0) : undefined;
  const pestana = (activa: boolean, clase?: string) => cn("flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium", activa ? "border-marca bg-marca text-white" : "border-linea bg-papel hover:bg-zinc-50", clase);
  const insignia = (activa: boolean, n: number | undefined) => <span className={cn("rounded-full px-1.5 text-xs tabular-nums", activa ? "bg-white text-marca" : "bg-zinc-200")}>{n ?? "–"}</span>;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Bandejas de trabajo</h1>
      <div role="tablist" aria-label="Bandejas" className="flex gap-1 overflow-x-auto pb-1">
        <button role="tab" aria-selected={hoy} onClick={() => setParams({})} className={pestana(hoy)}>{HOY.texto}{insignia(hoy, pendientesHoy)}</button>
        {BANDEJAS.map((b) => (
          <button key={b.slug} role="tab" aria-selected={!hoy && b === actual} onClick={() => setParams({ b: b.slug })} className={pestana(!hoy && b === actual)}>
            {b.texto}{insignia(!hoy && b === actual, conteo.data?.[b.clave])}
          </button>
        ))}
      </div>
      {hoy ? (
        <>
          <p className="text-sm text-tinta-suave">{HOY.ayuda}</p>
          <div role="tabpanel" aria-label={HOY.texto}><QueHacerHoy /></div>
        </>
      ) : (
        <>
          <p className="text-sm text-tinta-suave">{actual.ayuda}</p>
          <div role="tabpanel" aria-label={actual.texto}><Contenido slug={actual.slug} vacio={actual.vacio} /></div>
        </>
      )}
    </div>
  );
}

type Pendiente = { id: string; urgencia: number; orden: string; etiqueta: string; slug: string; pacienteId?: number; texto: ReactNode };

function pendientes(d: {
  seguimientos?: Awaited<ReturnType<typeof api.bandejas.seguimientos>>; contactos?: Awaited<ReturnType<typeof api.bandejas.contactos>>;
  mensajes?: Awaited<ReturnType<typeof api.bandejas.sinInterpretar>>; noConfirmadas?: Awaited<ReturnType<typeof api.bandejas.noConfirmadas>>;
  sinDesenlace?: Awaited<ReturnType<typeof api.bandejas.sinDesenlace>>; dadosDeBaja?: Awaited<ReturnType<typeof api.bandejas.dadosDeBaja>>;
}): Pendiente[] {
  const f: Pendiente[] = [];
  for (const r of d.seguimientos ?? []) f.push({ id: `seg-${r.id}`, urgencia: r.escalado ? 0 : 5, orden: r.abierto_en, etiqueta: r.escalado ? "Escalado" : "Seguimiento", slug: "seguimientos", pacienteId: r.paciente_id,
    texto: <><b>{r.paciente}</b>: {r.escalado ? "el sistema ya no pudo contactarle; llámale tú" : `seguimiento abierto de ${limpio(r.tipo)}`} ({r.intentos} intentos).</> });
  for (const r of d.contactos ?? []) f.push({ id: `con-${r.id}`, urgencia: 1, orden: r.momento, etiqueta: esSolicitudWeb(r) ? "Solicitud web" : "Validar", slug: "contactos",
    texto: esSolicitudWeb(r) ? resumenWeb(r) : <>El documento <b>{r.documento}</b> intentó agendar desde otro celular ({r.celular}). Llama para validar.</> });
  for (const r of d.mensajes ?? []) f.push({ id: `msj-${r.id}`, urgencia: 2, orden: r.momento, etiqueta: "Mensaje", slug: "sin-interpretar", pacienteId: r.paciente_id,
    texto: <><b>{r.paciente}</b> escribió algo que el sistema no entendió: “{r.texto}”.</> });
  for (const r of d.noConfirmadas ?? []) f.push({ id: `nc-${r.cita_id}`, urgencia: 3, orden: r.inicio, etiqueta: "Sin confirmar", slug: "no-confirmadas", pacienteId: r.paciente_id,
    texto: <>Llama a <b>{r.paciente}</b>: su cita del {fechaHora(r.inicio)} sigue sin confirmar.</> });
  for (const r of d.sinDesenlace ?? []) f.push({ id: `sd-${r.cita_id}`, urgencia: 4, orden: r.inicio, etiqueta: "Por cerrar", slug: "sin-desenlace", pacienteId: r.paciente_id,
    texto: <>Cierra la cita de <b>{r.paciente}</b> del {fechaHora(r.inicio)}: ¿asistió o no?</> });
  for (const r of d.dadosDeBaja ?? []) f.push({ id: `baja-${r.cita_id}`, urgencia: 6, orden: r.inicio, etiqueta: "Sin mensajes", slug: "dados-de-baja", pacienteId: r.paciente_id,
    texto: <>Confirma por teléfono a <b>{r.paciente}</b> su cita del {fechaHora(r.inicio)}: pidió no recibir mensajes.</> });
  return f.sort((a, b) => a.urgencia - b.urgencia || a.orden.localeCompare(b.orden));
}

const MAXIMO_HOY = 15;

type FilaContacto = { documento: string; celular: string; nota: string };

function resumenWeb(r: FilaContacto): ReactNode {
  const w = leerSolicitudWeb(r.nota);
  return <><b>{w.nombre ?? "Sin nombre"}</b> escribió desde el sitio web: {w.tipo}{w.paquete ? ` · ${w.paquete}` : ""}. Contáctale por {w.correo && !r.celular ? "correo" : "teléfono o WhatsApp"}.</>;
}

function DetalleWeb({ r }: { r: FilaContacto }) {
  const w = leerSolicitudWeb(r.nota);
  const wa = digitosWhatsApp(r.celular);
  return (
    <div className="min-w-48 flex-1 space-y-0.5">
      <p><span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-950">Solicitud web</span> <b>{w.tipo}</b>{w.paquete ? ` · ${w.paquete}` : ""}{w.idioma ? ` · ${w.idioma.toUpperCase()}` : ""}</p>
      <p><b>{w.nombre ?? "Sin nombre"}</b>{w.pais ? ` · ${w.pais}` : ""}</p>
      <p className="flex flex-wrap gap-x-3">
        {r.celular && <><a className={ENLACE} href={`tel:${r.celular.replace(/[^\d+]/g, "")}`}>Llamar {r.celular}</a>{wa && <a className={ENLACE} href={`https://wa.me/${wa}`} target="_blank" rel="noopener noreferrer">WhatsApp</a>}</>}
        {w.correo && <a className={ENLACE} href={`mailto:${w.correo}`}>{w.correo}</a>}
      </p>
      {w.mensaje && <p className="whitespace-pre-wrap text-tinta-suave">“{w.mensaje}”</p>}
    </div>
  );
}

function QueHacerHoy() {
  const [, setParams] = useSearchParams();
  const consultas = useQueries({ queries: [
    { queryKey: ["bandeja", "seguimientos"], queryFn: api.bandejas.seguimientos, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "contactos"], queryFn: api.bandejas.contactos, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "sin-interpretar"], queryFn: api.bandejas.sinInterpretar, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "no-confirmadas"], queryFn: api.bandejas.noConfirmadas, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "sin-desenlace"], queryFn: api.bandejas.sinDesenlace, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "dados-de-baja"], queryFn: api.bandejas.dadosDeBaja, refetchInterval: CADA_MINUTO },
  ] });
  const [seguimientos, contactos, mensajes, noConfirmadas, sinDesenlace, dadosDeBaja] = consultas;
  const fallo = consultas.find((c) => c.error);
  if (fallo) return <Aviso>No pudimos cargar todo. <button className="underline" onClick={() => consultas.forEach((c) => void c.refetch())}>Reintentar</button></Aviso>;
  if (consultas.some((c) => c.isPending)) return <Cargando />;
  const filas = pendientes({ seguimientos: seguimientos.data, contactos: contactos.data, mensajes: mensajes.data, noConfirmadas: noConfirmadas.data, sinDesenlace: sinDesenlace.data, dadosDeBaja: dadosDeBaja.data });
  if (filas.length === 0) return <Tarjeta><Vacio titulo="Todo al día">No hay nada urgente. Revisa las demás pestañas si quieres ver cupos libres o pacientes en riesgo.</Vacio></Tarjeta>;
  return (
    <div className="space-y-2">
      <Tarjeta className="divide-y divide-linea">
        {filas.slice(0, MAXIMO_HOY).map((f) => (
          <Fila key={f.id}>
            <span className={cn("w-28 shrink-0 rounded-full px-2 py-0.5 text-center text-xs font-medium", f.urgencia === 0 ? "bg-rose-100 text-rose-900" : f.urgencia <= 3 ? "bg-amber-100 text-amber-950" : "bg-zinc-200 text-zinc-900")}>{f.etiqueta}</span>
            <span className="min-w-48 flex-1">{f.texto}</span>
            {f.pacienteId !== undefined && <Link className={ENLACE} to={`/pacientes/${f.pacienteId}`}>Ver paciente</Link>}
            <Boton pequeno variante="secundario" onClick={() => setParams({ b: f.slug })}>Resolver</Boton>
          </Fila>
        ))}
      </Tarjeta>
      {filas.length > MAXIMO_HOY && <p className="text-sm text-tinta-suave">Y {filas.length - MAXIMO_HOY} más. Al resolver estas, aparecerán las siguientes.</p>}
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
        <Fila key={r.id}>
          {esSolicitudWeb(r) ? <DetalleWeb r={r} /> : <><span className="w-32 font-medium">{r.documento}</span><span className="w-32">{r.celular}</span><span className="flex-1 text-tinta-suave">{r.nota}</span></>}
          <span className="text-tinta-suave">{fechaHora(r.momento)}</span><Boton pequeno variante="secundario" onClick={() => contacto.mutate(r.id)}>Gestionada</Boton></Fila>)} />;
    default:
      return <Lista clave={slug} fn={api.bandejas.dadosDeBaja} vacio={vacio} fila={(r) => (
        <Fila key={r.cita_id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><Paciente id={r.paciente_id} nombre={r.paciente} celular={r.celular} />
          <Link className={ENLACE} to={verCita(r.cita_id, r.inicio)}>Abrir cita</Link></Fila>)} />;
  }
}
