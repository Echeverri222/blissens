import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/cliente";
import { CADA_MINUTO, useAccion, useConteoBandejas } from "@/api/consultas";
import type { CelularPorRevisar, Contacto, Semaforo as TipoSemaforo, ConteoBandejas, ResultadoGestion } from "@/api/tipos";
import { totalLlamadas } from "@/lib/pendientes";
import { digitosWhatsApp, esSolicitudWeb, separarNombre, tamanoLegible, tipoDeSolicitud } from "@/lib/solicitudes";
import { fechaDe, fechaHora } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { AltoValor, Boton, Confirmar, Entrada, Hoja, Semaforo, Tarjeta } from "@/ui/controles";
import { BuscarPaciente } from "./Agendar";
import { BotonConfirmo, EnlacesContacto } from "./Llamar";
import { Aviso, Cargando, Consulta, Vacio } from "@/ui/vistas";

type Grupo = "Llamar" | "Revisar";
const BANDEJAS: { clave: keyof ConteoBandejas; slug: string; texto: string; grupo: Grupo; ayuda: string; vacio: string }[] = [
  { clave: "no_confirmadas", slug: "no-confirmadas", texto: "No confirmadas", grupo: "Llamar", ayuda: "Citas próximas sin confirmación, ordenadas por cercanía: las que no respondieron y, hasta el fin de mañana, las que aún no contestan el recordatorio. Llama primero a las más urgentes.", vacio: "Todas las citas próximas están confirmadas." },
  { clave: "seguimientos", slug: "seguimientos", texto: "Seguimientos", grupo: "Llamar", ayuda: "Casos abiertos y que necesitan llamada, primero los pacientes de alto valor (internacionales y deportistas). Registra aquí lo que hayas gestionado por teléfono.", vacio: "No hay seguimientos abiertos." },
  { clave: "sin_interpretar", slug: "sin-interpretar", texto: "Mensajes por responder", grupo: "Llamar", ayuda: "Mensajes que el paciente escribió y el sistema no supo interpretar. Respóndele por tu cuenta y márcalo como resuelto.", vacio: "No hay mensajes pendientes." },
  { clave: "contactos", slug: "contactos", texto: "Contactos y solicitudes", grupo: "Llamar", ayuda: "Solicitudes de contacto: personas del sitio web que piden información y quienes intentaron agendar con un documento ya registrado pero otro celular (esas se validan por teléfono).", vacio: "No hay solicitudes de contacto." },
  { clave: "dados_de_baja", slug: "dados-de-baja", texto: "Dados de baja", grupo: "Llamar", ayuda: "Citas próximas de pacientes que pidieron no recibir mensajes automáticos: confírmalas por teléfono.", vacio: "No hay citas próximas de pacientes dados de baja." },
  { clave: "celulares_por_revisar", slug: "celulares-por-revisar", texto: "Celulares por revisar", grupo: "Llamar", ayuda: "Pacientes con cita próxima o seguimiento abierto cuyo celular falta, no es válido o no tiene WhatsApp: el sistema no les puede escribir. Corrige el número o contacta a su responsable.", vacio: "Todos los celulares están en orden." },
  { clave: "sin_desenlace", slug: "sin-desenlace", texto: "Citas por cerrar", grupo: "Revisar", ayuda: "Citas pasadas que quedaron sin desenlace. Ciérralas para no dejar huecos en los datos.", vacio: "No hay citas pasadas sin cerrar." },
  { clave: "cupos_libres", slug: "cupos-libres", texto: "Cupos libres", grupo: "Revisar", ayuda: "Espacios liberados por cancelaciones que aún no se han ocupado, y a quién se ofrecieron.", vacio: "No hay cupos liberados pendientes." },
  { clave: "en_riesgo", slug: "en-riesgo", texto: "Pacientes en riesgo", grupo: "Revisar", ayuda: "Tratamientos activos sin cita futura y con más días que el umbral desde la última cita. Primero los pacientes de alto valor (internacionales y deportistas), después los de más días sin cita.", vacio: "Ningún paciente con tratamiento a medias está en riesgo." },
];

const ENLACE = "font-medium underline";
const verCita = (id: number, inicio: string) => `/agenda?fecha=${fechaDe(inicio)}&cita=${id}`;

const HOY = { slug: "hoy", texto: "Qué hacer hoy", ayuda: "Lo que necesita una llamada o un clic de recepción, de lo más urgente a lo menos urgente. Los trámites (citas por cerrar) van aparte." };

export function Bandejas() {
  const [params, setParams] = useSearchParams();
  const conteo = useConteoBandejas();
  const hoy = params.get("b") === null || params.get("b") === HOY.slug;
  const actual = BANDEJAS.find((b) => b.slug === params.get("b")) ?? BANDEJAS[0];
  const llamadas = conteo.data ? totalLlamadas(conteo.data) : undefined;
  const pestana = (activa: boolean) => cn("flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium", activa ? "border-marca bg-marca text-white" : "border-linea bg-papel hover:bg-zinc-50");
  const insignia = (activa: boolean, n: number | undefined) => <span className={cn("rounded-full px-1.5 text-xs tabular-nums", activa ? "bg-white text-marca" : "bg-zinc-200")}>{n ?? "–"}</span>;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Pendientes</h1>
      <div role="tablist" aria-label="Pendientes" className="space-y-2">
        {(["Llamar", "Revisar"] as const).map((g) => (
          <div key={g} role="group" aria-label={g} className="flex flex-wrap items-center gap-1">
            <span className="w-16 text-xs font-semibold uppercase tracking-wide text-tinta-suave">{g}</span>
            {g === "Llamar" && <button role="tab" aria-selected={hoy} onClick={() => setParams({})} className={pestana(hoy)}>{HOY.texto}{insignia(hoy, llamadas)}</button>}
            {BANDEJAS.filter((b) => b.grupo === g).map((b) => (
              <button key={b.slug} role="tab" aria-selected={!hoy && b === actual} onClick={() => setParams({ b: b.slug })} className={pestana(!hoy && b === actual)}>
                {b.texto}{insignia(!hoy && b === actual, conteo.data?.[b.clave])}
              </button>
            ))}
          </div>
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

type Pendiente = { id: string; urgencia: number; altoValor?: boolean; orden: string; etiqueta: string; slug: string; pacienteId?: number; celular?: string | null; semaforo?: TipoSemaforo | null; texto: ReactNode; acciones: ReactNode };

/** Las llamadas de hoy, de lo más urgente a lo menos: necesita llamada, mensajes, contactos, sin confirmar, seguimientos y, al final, los dados de baja.
 *  Con la misma urgencia, primero los pacientes de alto valor (internacionales y deportistas). */
function pendientes(d: {
  seguimientos?: Awaited<ReturnType<typeof api.bandejas.seguimientos>>; contactos?: Awaited<ReturnType<typeof api.bandejas.contactos>>;
  mensajes?: Awaited<ReturnType<typeof api.bandejas.sinInterpretar>>; noConfirmadas?: Awaited<ReturnType<typeof api.bandejas.noConfirmadas>>;
  dadosDeBaja?: Awaited<ReturnType<typeof api.bandejas.dadosDeBaja>>; celulares?: Awaited<ReturnType<typeof api.bandejas.celularesPorRevisar>>;
}): Pendiente[] {
  const f: Pendiente[] = [];
  for (const r of d.seguimientos ?? []) f.push({ id: `seg-${r.id}`, urgencia: r.escalado ? 0 : 4, altoValor: r.internacional || r.deportista, orden: r.abierto_en, etiqueta: r.escalado ? "Necesita llamada" : "Seguimiento", slug: "seguimientos", pacienteId: r.paciente_id, celular: r.celular, semaforo: r.semaforo,
    acciones: <AccionesSeguimiento id={r.id} paciente={r.paciente} />,
    texto: <><b>{r.paciente}</b> <AltoValor internacional={r.internacional} deportista={r.deportista} />: {r.escalado ? "el sistema ya no pudo contactarle; llámale tú" : `seguimiento abierto de ${limpio(r.tipo)}`} ({r.intentos} intentos).</> });
  for (const r of d.mensajes ?? []) f.push({ id: `msj-${r.id}`, urgencia: 1, orden: r.momento, etiqueta: "Mensaje", slug: "sin-interpretar", pacienteId: r.paciente_id,
    acciones: <BotonResuelto id={r.id} paciente={r.paciente} />,
    texto: <><b>{r.paciente}</b> escribió algo que el sistema no entendió: “{r.texto}”.</> });
  for (const r of d.contactos ?? []) f.push({ id: `con-${r.id}`, urgencia: 2, orden: r.momento, etiqueta: esSolicitudWeb(r) ? "Solicitud web" : "Validar", slug: "contactos", celular: r.celular,
    acciones: <BotonGestionada id={r.id} />,
    texto: esSolicitudWeb(r) ? resumenWeb(r) : <>El documento <b>{r.documento}</b> intentó agendar desde otro celular ({r.celular}). Llama para validar.</> });
  for (const r of d.noConfirmadas ?? []) f.push({ id: `nc-${r.cita_id}`, urgencia: 3, orden: r.inicio, etiqueta: ESTADO_NC[r.estado], slug: "no-confirmadas", pacienteId: r.paciente_id, celular: r.celular, semaforo: r.semaforo,
    acciones: <AccionesCita citaId={r.cita_id} paciente={r.paciente} inicio={r.inicio} />,
    texto: <>Llama a <b>{r.paciente}</b>: su cita del {fechaHora(r.inicio)} {r.estado === "programada" ? "aún no responde al recordatorio" : "sigue sin confirmar"}.</> });
  for (const r of d.dadosDeBaja ?? []) f.push({ id: `baja-${r.cita_id}`, urgencia: 5, orden: r.inicio, etiqueta: "Sin mensajes", slug: "dados-de-baja", pacienteId: r.paciente_id, celular: r.celular, semaforo: r.semaforo,
    acciones: <AccionesCita citaId={r.cita_id} paciente={r.paciente} inicio={r.inicio} />,
    texto: <>Confirma por teléfono a <b>{r.paciente}</b> su cita del {fechaHora(r.inicio)}: pidió no recibir mensajes.</> });
  for (const r of d.celulares ?? []) f.push({ id: `cel-${r.paciente_id}`, urgencia: 3, orden: r.proxima_cita ?? "9", etiqueta: "Celular por revisar", slug: "celulares-por-revisar", pacienteId: r.paciente_id, celular: r.responsable_celular,
    acciones: <AccionesCelular r={r} />,
    texto: <><b>{r.paciente}</b>: {TEXTO_CELULAR[r.motivo] ?? "celular por revisar"}. <Responsable r={r} /></> });
  return f.sort((a, b) => a.urgencia - b.urgencia || Number(!!b.altoValor) - Number(!!a.altoValor) || a.orden.localeCompare(b.orden));
}

const TEXTO_CELULAR: Record<string, string> = { sin_celular: "no tiene celular", invalido: "Celular no válido", sin_whatsapp: "su celular no tiene WhatsApp" };

/** Si el paciente depende de un responsable con celular usable, la recepción llama a quien sí recibe los mensajes. */
function Responsable({ r }: { r: CelularPorRevisar }) {
  if (!r.responsable_id) return <>Corrige el número o llámale por otro medio.</>;
  return <>Contactar a <Link className={ENLACE} to={`/pacientes/${r.responsable_id}`}>{r.responsable}</Link>{r.parentesco ? ` (${r.parentesco})` : ""}.</>;
}

function AccionesCelular({ r }: { r: CelularPorRevisar }) {
  const [abierta, setAbierta] = useState(false);
  const [celular, setCelular] = useState("");
  const editar = useAccion((c: string) => api.pacientes.cambiarCelular(r.paciente_id, { celular: c }), { ok: "Celular actualizado", alExito: () => { setAbierta(false); setCelular(""); } });
  const enChat = useAccion(() => api.pacientes.celularEnChat(r.paciente_id), { ok: "Celular marcado como válido" });
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Boton variante="secundario" pequeno onClick={() => setAbierta(true)}>Editar celular</Boton>
      <Confirmar etiqueta="Ya está en un chat de WhatsApp" pequeno deshabilitado={enChat.isPending} si="Sí, ya está en un chat"
        pregunta={<>¿<b className="text-tinta">{r.paciente}</b> ya está en un chat de WhatsApp con la clínica? El celular se marca como válido y se le vuelve a escribir.</>}
        alConfirmar={() => enChat.mutate(undefined)} />
      <Hoja abierta={abierta} alCerrar={() => setAbierta(false)} titulo="Editar celular" descripcion={`Nuevo celular de ${r.paciente}. Si comparte el número con su familia, se corrige para todos.`}>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); editar.mutate(celular); }}>
          {editar.error instanceof ApiError && <Aviso>{editar.error.mensaje}</Aviso>}
          <Entrada etiqueta="Celular" inputMode="tel" value={celular} onChange={(e) => setCelular(e.target.value)} required />
          <Boton type="submit" disabled={editar.isPending}>Guardar</Boton>
        </form>
      </Hoja>
    </div>
  );
}

const ESTADO_NC = { no_confirmada: "Sin confirmar", programada: "Sin respuesta aún" } as const;

const MAXIMO_HOY = 15;

function resumenWeb(r: Contacto): ReactNode {
  const adjuntos = r.adjuntos?.length ? ` Adjuntó ${r.adjuntos.length === 1 ? "1 archivo" : `${r.adjuntos.length} archivos`}.` : "";
  return <><b>{r.nombre ?? "Sin nombre"}</b> escribió desde el sitio web: {tipoDeSolicitud(r)}{r.pais ? ` (${r.pais})` : ""}.{adjuntos} Contáctale por {r.correo && !r.celular ? "correo" : "teléfono o WhatsApp"}.</>;
}

function DetalleWeb({ r }: { r: Contacto }) {
  const wa = digitosWhatsApp(r.celular);
  return (
    <div className="min-w-48 flex-1 space-y-1">
      <p><span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-950">Solicitud web</span> <b>{tipoDeSolicitud(r)}</b>{r.idioma ? ` · ${r.idioma.toUpperCase()}` : ""}</p>
      <p><b>{r.nombre ?? "Sin nombre"}</b>{r.pais ? ` · ${r.pais}` : ""}</p>
      <p className="flex flex-wrap gap-x-3">
        {r.celular && <><a className={ENLACE} href={`tel:${r.celular.replace(/[^\d+]/g, "")}`}>Llamar {r.celular}</a>{wa && <a className={ENLACE} href={`https://wa.me/${wa}`} target="_blank" rel="noopener noreferrer">WhatsApp</a>}</>}
        {r.correo && <a className={ENLACE} href={`mailto:${r.correo}`}>{r.correo}</a>}
      </p>
      {r.mensaje && <p className="whitespace-pre-wrap text-tinta-suave">“{r.mensaje}”</p>}
      {(r.adjuntos ?? []).length > 0 && (
        <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label="Archivos adjuntos">
          {(r.adjuntos ?? []).map((a) => (
            <li key={a.id}><a className={ENLACE} href={api.bandejas.urlAdjunto(r.id, a.id)} download={a.nombre}>{a.nombre}</a> <span className="text-tinta-suave">({tamanoLegible(a.tamano)})</span></li>
          ))}
        </ul>
      )}
      {r.paciente_id
        ? <p>Ficha: <Link className={ENLACE} to={`/pacientes/${r.paciente_id}`}>{r.paciente ?? "Ver paciente"}</Link></p>
        : <VincularPaciente r={r} />}
    </div>
  );
}

/** Vincula la solicitud a un paciente existente o a uno nuevo, con los datos de la solicitud ya escritos. */
function VincularPaciente({ r }: { r: Contacto }) {
  const [abierta, setAbierta] = useState(false);
  const m = useAccion((pacienteId: number) => api.bandejas.vincularContacto(r.id, pacienteId), {
    ok: "Solicitud vinculada a la ficha", alExito: () => setAbierta(false) });
  const celular = r.celular.replace(/\D/g, "");
  return (
    <>
      <Boton variante="secundario" pequeno onClick={() => setAbierta(true)}>Vincular a un paciente</Boton>
      <Hoja abierta={abierta} alCerrar={() => setAbierta(false)} titulo="Vincular a un paciente"
        descripcion="Busca la ficha de esta persona o créala. La solicitud y sus archivos quedan con el paciente.">
        <div className="space-y-3">
          {m.error instanceof ApiError && <Aviso>{m.error.mensaje}</Aviso>}
          <BuscarPaciente alElegir={(p) => m.mutate(p.id)}
            inicial={{ texto: r.nombre ?? "", paciente: { ...separarNombre(r.nombre), celular: celular.length === 12 && celular.startsWith("57") ? celular.slice(2) : r.celular } }} />
        </div>
      </Hoja>
    </>
  );
}

function QueHacerHoy() {
  const [, setParams] = useSearchParams();
  const conteo = useConteoBandejas();
  const consultas = useQueries({ queries: [
    { queryKey: ["bandeja", "seguimientos"], queryFn: api.bandejas.seguimientos, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "contactos"], queryFn: api.bandejas.contactos, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "sin-interpretar"], queryFn: api.bandejas.sinInterpretar, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "no-confirmadas"], queryFn: api.bandejas.noConfirmadas, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "dados-de-baja"], queryFn: api.bandejas.dadosDeBaja, refetchInterval: CADA_MINUTO },
    { queryKey: ["bandeja", "celulares-por-revisar"], queryFn: api.bandejas.celularesPorRevisar, refetchInterval: CADA_MINUTO },
  ] });
  const [seguimientos, contactos, mensajes, noConfirmadas, dadosDeBaja, celulares] = consultas;
  const fallo = consultas.find((c) => c.error);
  if (fallo) return <Aviso>No pudimos cargar todo. <button className="underline" onClick={() => consultas.forEach((c) => void c.refetch())}>Reintentar</button></Aviso>;
  if (consultas.some((c) => c.isPending)) return <Cargando />;
  const filas = pendientes({ seguimientos: seguimientos.data, contactos: contactos.data, mensajes: mensajes.data, noConfirmadas: noConfirmadas.data, dadosDeBaja: dadosDeBaja.data, celulares: celulares.data });
  const porCerrar = conteo.data?.sin_desenlace ?? 0;
  return (
    <div className="space-y-4">
      <section aria-label="Llamadas" className="space-y-2">
        <h2 className="text-base font-semibold">Llamadas ({filas.length})</h2>
        {filas.length === 0 ? <Tarjeta><Vacio titulo="Todo al día">No hay llamadas pendientes. Revisa las demás pestañas si quieres ver cupos libres o pacientes en riesgo.</Vacio></Tarjeta> : (
          <Tarjeta className="divide-y divide-linea">
            {filas.slice(0, MAXIMO_HOY).map((f) => (
              <Fila key={f.id}>
                <span className={cn("w-32 shrink-0 rounded-full px-2 py-0.5 text-center text-xs font-medium", f.urgencia === 0 ? "bg-rose-100 text-rose-900" : f.urgencia <= 3 ? "bg-amber-100 text-amber-950" : "bg-zinc-200 text-zinc-900")}>{f.etiqueta}</span>
                <span className="min-w-48 flex-1">{f.texto}</span>
                <Semaforo semaforo={f.semaforo} />
                <EnlacesContacto celular={f.celular} />
                {f.pacienteId !== undefined && <Link className={ENLACE} to={`/pacientes/${f.pacienteId}`}>Ver paciente</Link>}
                <div className="ml-auto flex flex-wrap items-center gap-1.5">{f.acciones}</div>
              </Fila>
            ))}
          </Tarjeta>
        )}
        {filas.length > MAXIMO_HOY && <p className="text-sm text-tinta-suave">Y {filas.length - MAXIMO_HOY} más. Al resolver estas, aparecerán las siguientes.</p>}
      </section>
      <details className="rounded-xl border border-linea bg-papel p-3 text-sm">
        <summary className="cursor-pointer font-semibold">Trámites ({porCerrar})</summary>
        <p className="mt-2 text-tinta-suave">{porCerrar === 0 ? "No hay citas pasadas sin cerrar." : `Hay ${porCerrar} citas pasadas sin desenlace. No necesitan llamada: ciérralas cuando tengas un momento.`}
          {porCerrar > 0 && <> <button className={ENLACE} onClick={() => setParams({ b: "sin-desenlace" })}>Ver citas por cerrar</button></>}</p>
      </details>
    </div>
  );
}

/** Las acciones de cada tipo de pendiente: las mismas en «Qué hacer hoy» y en su bandeja, siempre con confirmación. */
function AccionesSeguimiento({ id, paciente }: { id: number; paciente: string }) {
  const m = useAccion((v: { r: ResultadoGestion; detalle: string }) => api.bandejas.gestionSeguimiento(id, v.r, v.detalle), { ok: "Registrado" });
  const quien = <b className="text-tinta">{paciente}</b>;
  return (
    <div className="flex flex-wrap gap-1.5">
      <Confirmar etiqueta="Aceptó" pequeno deshabilitado={m.isPending} si="Sí, aceptó" pregunta={<>{quien} aceptó por teléfono. El seguimiento se cierra como aceptado; si quiere una cita, agéndala tú.</>}
        alConfirmar={() => m.mutate({ r: "acepto", detalle: "Gestión telefónica" })} />
      <Confirmar etiqueta="Rechazó" pequeno deshabilitado={m.isPending} si="Sí, rechazó" pregunta={<>{quien} no quiere continuar. El seguimiento se cierra y no se le volverá a escribir por este caso.</>}
        alConfirmar={() => m.mutate({ r: "rechazo", detalle: "Gestión telefónica" })} />
      <Confirmar etiqueta="Sin respuesta" pequeno deshabilitado={m.isPending} si="Sí, no contestó" pregunta={<>Llamaste a {quien} y no contestó. Queda registrado como un intento más.</>}
        alConfirmar={() => m.mutate({ r: "sin_respuesta", detalle: "Llamada sin respuesta" })} />
    </div>
  );
}

function BotonResuelto({ id, paciente }: { id: number; paciente: string }) {
  const m = useAccion(() => api.bandejas.gestionarMensaje(id), { ok: "Mensaje resuelto" });
  return <Confirmar etiqueta="Resuelto" pequeno deshabilitado={m.isPending} si="Sí, ya le respondí"
    pregunta={<>¿Ya le respondiste a <b className="text-tinta">{paciente}</b> por tu cuenta? El mensaje sale de la lista.</>} alConfirmar={() => m.mutate(undefined)} />;
}

function BotonGestionada({ id }: { id: number }) {
  const m = useAccion(() => api.bandejas.gestionarContacto(id), { ok: "Solicitud gestionada" });
  return <Confirmar etiqueta="Gestionada" pequeno deshabilitado={m.isPending} si="Sí, ya la gestioné"
    pregunta="¿Ya contactaste a esta persona? La solicitud sale de la lista." alConfirmar={() => m.mutate(undefined)} />;
}

function AccionesCita({ citaId, paciente, inicio }: { citaId: number; paciente: string; inicio: string }) {
  return <div className="flex items-center gap-3"><Link className={ENLACE} to={verCita(citaId, inicio)}>Abrir cita</Link><BotonConfirmo citaId={citaId} paciente={paciente} inicio={inicio} /></div>;
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
const Paciente = ({ id, nombre, celular, semaforo }: { id: number; nombre: string; celular?: string | null; semaforo?: TipoSemaforo | null }) => (
  <div className="min-w-40 flex-1"><Link className={ENLACE} to={`/pacientes/${id}`}>{nombre}</Link> <Semaforo semaforo={semaforo} />{celular && <p><EnlacesContacto celular={celular} /></p>}</div>
);
const limpio = (s: string) => s.replace(/_/g, " ");
const CAUSAS: Record<string, string> = { cancelacion: "cancelación", cambio_fecha: "cambio de fecha" };
const causa = (s: string) => CAUSAS[s] ?? limpio(s);

function Contenido({ slug, vacio }: { slug: string; vacio: string }) {
  const desenlace = useAccion((v: { id: number; d: "atendida" | "no_asistio" }) => api.citas.desenlace(v.id, v.d), { ok: (_, v) => (v.d === "atendida" ? "Marcada como atendida" : "Marcada como no asistió") });
  const errores = desenlace.error instanceof ApiError ? desenlace.error : undefined;
  const aviso = errores && <Aviso tipo="aviso">{errores.mensaje}</Aviso>;
  switch (slug) {
    case "no-confirmadas":
      return <Lista clave={slug} fn={api.bandejas.noConfirmadas} vacio={vacio} fila={(r) => (
        <Fila key={r.cita_id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><Paciente id={r.paciente_id} nombre={r.paciente} celular={r.celular} semaforo={r.semaforo} />
          <div className="min-w-36"><span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", r.estado === "no_confirmada" ? "bg-amber-100 text-amber-950" : "bg-sky-100 text-sky-950")}>{ESTADO_NC[r.estado]}</span>
            {r.recordatorio_enviado && <p className="text-tinta-suave">{r.recordatorio_en ? `Recordatorio enviado ${fechaHora(r.recordatorio_en)}` : "Recordatorio enviado"}</p>}</div>
          <span className="text-tinta-suave">{r.profesional}</span>
          <div className="ml-auto"><AccionesCita citaId={r.cita_id} paciente={r.paciente} inicio={r.inicio} /></div></Fila>)} />;
    case "seguimientos":
      return <>{aviso}<Lista clave={slug} fn={api.bandejas.seguimientos} vacio={vacio} fila={(r) => (
        <Fila key={r.id}><Paciente id={r.paciente_id} nombre={r.paciente} celular={r.celular} semaforo={r.semaforo} />
          <AltoValor internacional={r.internacional} deportista={r.deportista} />
          <span>{limpio(r.tipo)}{r.escalado && <> <b className="rounded bg-rose-100 px-1.5 text-xs text-rose-900">Necesita llamada</b></>}</span>
          <span className="text-tinta-suave">{r.intentos} intentos · último: {limpio(r.ultimo ?? "pendiente")}</span>
          <div className="ml-auto"><AccionesSeguimiento id={r.id} paciente={r.paciente} /></div></Fila>)} /></>;
    case "en-riesgo":
      return <Lista clave={slug} fn={api.bandejas.enRiesgo} vacio={vacio} fila={(r) => (
        <Fila key={r.tratamiento_id}><Paciente id={r.paciente_id} nombre={r.paciente} />
          <AltoValor internacional={r.internacional} deportista={r.deportista} /><span>Última cita: {r.ultima_cita}</span>
          <span>{r.dias_sin_cita} días sin cita</span><span className="text-tinta-suave">Mensaje de recuperación: {r.caso_id ? "enviado" : "aún no"}</span>
          <Link className={cn(ENLACE, "ml-auto")} to={`/agendar?paciente=${r.paciente_id}`}>Agendar</Link></Fila>)} />;
    case "cupos-libres":
      return <Lista clave={slug} fn={api.bandejas.cuposLibres} vacio={vacio} fila={(r) => (
        <Fila key={r.id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><span>{r.profesional}</span>
          <span className="text-tinta-suave">{limpio(r.estado)} · {causa(r.causa)}</span><span className="text-tinta-suave">Ofertado a: {r.ofrecido_a ?? "—"}</span></Fila>)} />;
    case "sin-desenlace":
      return <>{aviso}<Lista clave={slug} fn={api.bandejas.sinDesenlace} vacio={vacio} fila={(r) => (
        <Fila key={r.cita_id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><Paciente id={r.paciente_id} nombre={r.paciente} />
          <span className="text-tinta-suave">{r.profesional}</span><Link className={ENLACE} to={verCita(r.cita_id, r.inicio)}>Abrir cita</Link>
          <div className="ml-auto flex gap-1.5">
            <Confirmar etiqueta="Atendida" pequeno si="Sí, fue atendida" pregunta={<><b className="text-tinta">{r.paciente}</b> asistió a la cita del {fechaHora(r.inicio)}. Se cierra como atendida.</>} alConfirmar={() => desenlace.mutate({ id: r.cita_id, d: "atendida" })} />
            <Confirmar etiqueta="No asistió" pequeno pregunta="Se abrirá un seguimiento y el paciente recibirá un mensaje para reagendar." alConfirmar={() => desenlace.mutate({ id: r.cita_id, d: "no_asistio" })} />
          </div></Fila>)} /></>;
    case "sin-interpretar":
      return <Lista clave={slug} fn={api.bandejas.sinInterpretar} vacio={vacio} fila={(r) => (
        <Fila key={r.id}><Paciente id={r.paciente_id} nombre={r.paciente} /><span className="flex-[2] italic">“{r.texto}”</span>
          <span className="text-tinta-suave">{fechaHora(r.momento)}</span><BotonResuelto id={r.id} paciente={r.paciente} /></Fila>)} />;
    case "contactos":
      return <Lista clave={slug} fn={api.bandejas.contactos} vacio={vacio} fila={(r) => (
        <Fila key={r.id}>
          {esSolicitudWeb(r) ? <DetalleWeb r={r} /> : <><span className="w-32 font-medium">{r.documento}</span><span className="w-32">{r.celular}</span><span className="flex-1 text-tinta-suave">{r.nota}</span></>}
          <span className="text-tinta-suave">{fechaHora(r.momento)}</span><BotonGestionada id={r.id} /></Fila>)} />;
    case "celulares-por-revisar":
      return <Lista clave={slug} fn={api.bandejas.celularesPorRevisar} vacio={vacio} fila={(r) => (
        <Fila key={r.paciente_id}><Paciente id={r.paciente_id} nombre={r.paciente} celular={r.celular} />
          <span className="min-w-40"><b className="rounded bg-amber-100 px-1.5 text-xs text-amber-950">{TEXTO_CELULAR[r.motivo] ?? r.motivo}</b>
            {r.proxima_cita && <p className="text-tinta-suave">Cita: {fechaHora(r.proxima_cita)}</p>}</span>
          <span className="flex-1"><Responsable r={r} />{r.responsable_celular && <> <EnlacesContacto celular={r.responsable_celular} /></>}</span>
          <div className="ml-auto"><AccionesCelular r={r} /></div></Fila>)} />;
    default:
      return <Lista clave={slug} fn={api.bandejas.dadosDeBaja} vacio={vacio} fila={(r) => (
        <Fila key={r.cita_id}><span className="w-36 font-medium">{fechaHora(r.inicio)}</span><Paciente id={r.paciente_id} nombre={r.paciente} celular={r.celular} semaforo={r.semaforo} />
          <div className="ml-auto"><AccionesCita citaId={r.cita_id} paciente={r.paciente} inicio={r.inicio} /></div></Fila>)} />;
  }
}
