// Asistente del equipo: en escritorio, un panel fijo a la derecha que sigue abierto mientras se navega y se trabaja en el resto
// del panel; en el celular, un cajón a pantalla completa. El asistente NO ejecuta nada: cada propuesta es una acción
// preparada que la persona confirma, y se ejecuta con los mismos endpoints (y las mismas reglas) que el resto del panel.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, RotateCcw, Send, Sparkles, X } from "lucide-react";
import { ApiError, api } from "@/api/cliente";
import { useAccion } from "@/api/consultas";
import { Link } from "react-router-dom";
import type { AsistenteRespuesta, Propuesta } from "@/api/tipos";
import { cn } from "@/lib/utils";
import { Boton, Confirmar } from "@/ui/controles";
import { Aviso } from "@/ui/vistas";
import { FormularioPaciente } from "@/pantallas/Agendar";

const MAX_TEXTO = 1000;
const POCOS_MENSAJES = 5;

type Enlace = AsistenteRespuesta["enlaces"][number];
interface Mensaje { rol: "usuario" | "asistente"; texto: string; propuestas: Propuesta[]; enlaces?: Enlace[] }

/** El texto del asistente con los nombres de pacientes como enlaces a su ficha (el servidor dice cuáles y a dónde). */
export function TextoConEnlaces({ texto, enlaces = [], alNavegar }: { texto: string; enlaces?: Enlace[]; alNavegar?: () => void }) {
  if (!enlaces.length) return <>{texto}</>;
  const porTexto = new Map(enlaces.map((e) => [e.texto, e.ruta]));
  const patron = new RegExp(`(${enlaces.map((e) => e.texto.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "g");
  return <>{texto.split(patron).map((trozo, i) => {
    const ruta = porTexto.get(trozo);
    return ruta ? <Link key={i} to={ruta} onClick={alNavegar} className="font-medium text-marca underline">{trozo}</Link> : trozo;
  })}</>;
}
type Estado = "enviando" | "hecha" | "descartada";

const numero = (p: Propuesta["parametros"], k: string): number => {
  const v = p[k];
  if (typeof v !== "number" || !Number.isFinite(v)) throw new Error(`parámetro inválido: ${k}`);
  return v;
};
const texto = (p: Propuesta["parametros"], k: string): string => {
  const v = p[k];
  if (typeof v !== "string") throw new Error(`parámetro inválido: ${k}`);
  return v;
};
const booleano = (p: Propuesta["parametros"], k: string): boolean => {
  const v = p[k];
  if (typeof v !== "boolean") throw new Error(`parámetro inválido: ${k}`);
  return v;
};
const RESULTADOS = ["acepto", "rechazo", "sin_respuesta"] as const;

/** Cada tipo de propuesta se ejecuta con el endpoint que ya usa el panel; los parámetros se validan antes de enviarlos. */
export function ejecutarPropuesta(pr: Propuesta): Promise<unknown> {
  const p = pr.parametros;
  try {
    switch (pr.tipo) {
      case "agendar":
        return api.citas.agendar({ paciente_id: numero(p, "paciente_id"), profesional_id: numero(p, "profesional_id"), servicio_id: numero(p, "servicio_id"), inicio: texto(p, "inicio") });
      case "cambiar_fecha": return api.citas.cambiarFecha(numero(p, "cita_id"), texto(p, "inicio"));
      case "cancelar": return api.citas.cancelar(numero(p, "cita_id"), numero(p, "motivo_id"), typeof p.texto === "string" ? p.texto : undefined);
      case "confirmar_telefono": return api.citas.confirmar(numero(p, "cita_id"));
      case "desenlace": {
        const d = texto(p, "desenlace");
        if (d !== "atendida" && d !== "no_asistio") throw new Error("parámetro inválido: desenlace");
        return api.citas.desenlace(numero(p, "cita_id"), d);
      }
      case "bloqueo":
        return api.bloqueos.crear({ profesional_id: numero(p, "profesional_id"), inicio: texto(p, "inicio"), fin: texto(p, "fin"), motivo: typeof p.motivo === "string" ? p.motivo : "" });
      case "eliminar_bloqueo": return api.bloqueos.eliminar(numero(p, "bloqueo_id"));
      case "segmentos":
        return api.pacientes.segmentos(numero(p, "paciente_id"), { internacional: booleano(p, "internacional"), deportista: booleano(p, "deportista") });
      case "gestion_seguimiento": {
        const r = RESULTADOS.find((x) => x === p.resultado);
        if (!r) throw new Error("parámetro inválido: resultado");
        return api.bandejas.gestionSeguimiento(numero(p, "caso_id"), r, typeof p.detalle === "string" ? p.detalle : "");
      }
      case "gestionar_mensaje": return api.bandejas.gestionarMensaje(numero(p, "mensaje_id"));
      case "gestionar_contacto": return api.bandejas.gestionarContacto(numero(p, "solicitud_id"));
      case "vincular_contacto": return api.bandejas.vincularContacto(numero(p, "solicitud_id"), numero(p, "paciente_id"));
      case "revertir": return api.citas.revertir(numero(p, "historial_id"));
      // Lleva datos que no pasan por el modelo: lo crea el formulario de su tarjeta, no un botón de confirmar.
      case "crear_paciente": return Promise.reject(new Error("se crea desde el formulario"));
      default: return Promise.reject(new Error("tipo desconocido"));
    }
  } catch (e) {
    return Promise.reject(e);
  }
}

/** Paciente nuevo: el modelo solo trae el nombre; documento, celular y autorización se escriben aquí y van directo a la API. */
function TarjetaPaciente({ propuesta, estado, alCreado, alDescartar }: {
  propuesta: Propuesta; estado?: Estado; alCreado: () => void; alDescartar: () => void;
}) {
  const p = propuesta.parametros;
  const inicial = { nombres: typeof p.nombres === "string" ? p.nombres : "", apellidos: typeof p.apellidos === "string" ? p.apellidos : "" };
  if (estado === "hecha" || estado === "descartada") {
    return (
      <div data-testid="propuesta" className={cn("mt-2 rounded-[var(--radius-control)] border border-linea bg-papel p-3 text-sm", estado === "descartada" && "opacity-60")}>
        <p className="whitespace-pre-wrap break-words">{propuesta.resumen}</p>
        {estado === "hecha" ? <p className="mt-2 flex items-center gap-1 font-medium text-emerald-800"><Check className="size-4" aria-hidden /> Hecho</p>
          : <p className="mt-2 text-tinta-suave">Descartada</p>}
      </div>
    );
  }
  return (
    <div data-testid="propuesta" className="mt-2">
      <FormularioPaciente inicial={inicial} boton="Crear paciente" cancelar="Descartar" alCrear={alCreado} alCancelar={alDescartar} />
    </div>
  );
}

function TarjetaPropuesta({ propuesta, estado, error, alConfirmar, alDescartar }: {
  propuesta: Propuesta; estado?: Estado; error?: string; alConfirmar: () => void; alDescartar: () => void;
}) {
  const cerrada = estado === "hecha" || estado === "descartada";
  return (
    <div data-testid="propuesta" className={cn("mt-2 rounded-[var(--radius-control)] border border-linea bg-papel p-3 text-sm", estado === "descartada" && "opacity-60")}>
      <p className="whitespace-pre-wrap break-words">{propuesta.resumen}</p>
      {error && <div className="mt-2"><Aviso>{error}</Aviso></div>}
      {estado === "hecha" && <p className="mt-2 flex items-center gap-1 font-medium text-emerald-800"><Check className="size-4" aria-hidden /> Hecho</p>}
      {estado === "descartada" && <p className="mt-2 text-tinta-suave">Descartada</p>}
      {!cerrada && (
        <div className="mt-2 flex gap-2">
          <Confirmar etiqueta="Confirmar" titulo="¿Confirmar esta acción?" si="Sí, confirmar" variante="primario" pequeno
            deshabilitado={estado === "enviando"} pregunta={propuesta.resumen} alConfirmar={alConfirmar} />
          <Boton variante="secundario" pequeno disabled={estado === "enviando"} onClick={alDescartar}>Descartar</Boton>
        </div>
      )}
    </div>
  );
}

interface Conversacion {
  id: number | null; mensajes: Mensaje[]; estados: Record<string, Estado>; errores: Record<string, string>;
}
const VACIA: Conversacion = { id: null, mensajes: [], estados: {}, errores: {} };

/** Ancho del panel acoplado; el contenido del panel deja ese margen a la derecha para no quedar debajo. */
export const ANCHO_ASISTENTE = "md:mr-96";

/** `acoplado`: panel fijo a la derecha, sin tapar el resto (escritorio). Si no, cajón modal (celular). El estado abierto lo
 * lleva quien lo monta, para correr el contenido cuando está acoplado. */
export function Asistente({ acoplado = false, abierto, alCambiar: setAbierto }: { acoplado?: boolean; abierto: boolean; alCambiar: (v: boolean) => void }) {
  const qc = useQueryClient();
  const estado = useQuery({ queryKey: ["asistente", "estado"], queryFn: api.asistente.estado, retry: false, staleTime: 5 * 60_000 });
  const [conv, setConv] = useState<Conversacion>(VACIA);
  const [borrador, setBorrador] = useState("");
  const [fallo, setFallo] = useState<string | null>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);
  const lista = useRef<HTMLDivElement>(null);

  const envio = useMutation({
    mutationFn: (v: { texto: string; id: number | null }) => api.asistente.enviar(v.texto, v.id),
    onSuccess: (r) => {
      setConv((c) => ({ ...c, id: r.conversacion_id ?? c.id, mensajes: [...c.mensajes, { rol: "asistente", texto: r.respuesta, propuestas: r.propuestas, enlaces: r.enlaces }] }));
      void qc.invalidateQueries({ queryKey: ["asistente", "estado"] });
      // De vuelta al cuadro de texto para seguir la conversación, salvo que la persona ya esté trabajando en otra parte.
      const activo = document.activeElement;
      if (!activo || activo === document.body || entrada.current?.closest("aside, [role=dialog]")?.contains(activo)) entrada.current?.focus();
    },
    onError: (e) => {
      setFallo(e instanceof ApiError ? e.mensaje : "No pude responder eso. Intenta de nuevo.");
      if (e instanceof ApiError && e.codigo === "asistente_apagado") void qc.invalidateQueries({ queryKey: ["asistente", "estado"] });
    },
  });
  const ejecutar = useAccion(
    async (v: { clave: string; propuesta: Propuesta }) => {
      try { return await ejecutarPropuesta(v.propuesta); }
      catch (e) {
        const mensaje = e instanceof ApiError ? e.mensaje : "No se pudo ejecutar. Inténtalo de nuevo.";
        // Vuelve a quedar confirmable: la acción no se hizo.
        setConv((c) => { const estados = { ...c.estados }; delete estados[v.clave]; return { ...c, estados, errores: { ...c.errores, [v.clave]: mensaje } }; });
        throw e;
      }
    },
    { ok: "Hecho", alExito: (_d, v) => setConv((c) => ({ ...c, estados: { ...c.estados, [v.clave]: "hecha" }, errores: { ...c.errores, [v.clave]: "" } })) },
  );

  useEffect(() => { if (lista.current) lista.current.scrollTop = lista.current.scrollHeight; }, [conv.mensajes.length, envio.isPending, abierto]);
  useEffect(() => { if (abierto && acoplado) entrada.current?.focus(); }, [abierto, acoplado]);

  if (estado.isPending || estado.isError || !estado.data.disponible) return null;
  const restantes = estado.data.mensajes_restantes;

  const enviar = (e?: FormEvent) => {
    e?.preventDefault();
    const t = borrador.trim();
    if (!t || envio.isPending) return;
    setFallo(null);
    setConv((c) => ({ ...c, mensajes: [...c.mensajes, { rol: "usuario", texto: t, propuestas: [] }] }));
    setBorrador("");
    envio.mutate({ texto: t, id: conv.id });
  };
  const confirmar = (clave: string, propuesta: Propuesta) => {
    if (conv.estados[clave]) return; // nunca dos veces
    setConv((c) => ({ ...c, estados: { ...c.estados, [clave]: "enviando" } }));
    ejecutar.mutate({ clave, propuesta });
  };
  const nueva = () => { setConv(VACIA); setFallo(null); setBorrador(""); };

  const AVISO = "Puede equivocarse. Te propone acciones y solo se hacen si las confirmas.";
  const cuerpo = (titulo: ReactNode, descripcion: ReactNode, cerrar: ReactNode) => (<>
    <div className="flex items-start justify-between gap-4 border-b border-linea px-4 py-3">
      <div>
        {titulo}
{descripcion}
      </div>
      <div className="flex items-center gap-1">
        <Boton variante="fantasma" pequeno onClick={nueva} disabled={envio.isPending || (!conv.mensajes.length && !conv.id)}>
          <RotateCcw className="size-4" aria-hidden /> Nueva conversación</Boton>
        {cerrar}
      </div>
    </div>

    <div ref={lista} role="log" aria-live="polite" aria-label="Conversación con el asistente" className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
      {conv.mensajes.length === 0 && !envio.isPending && (
        <p className="text-sm text-tinta-suave">Pregúntame por la agenda, los pendientes o los pacientes, o pídeme preparar una acción.</p>
      )}
      {conv.mensajes.map((m, i) => (
        <div key={i} className={cn("flex flex-col", m.rol === "usuario" ? "items-end" : "items-start")}>
          <div className={cn("max-w-[90%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm",
            m.rol === "usuario" ? "bg-marca text-white" : "bg-zinc-100 text-tinta")}>
            {m.rol === "asistente" ? <TextoConEnlaces texto={m.texto} enlaces={m.enlaces} alNavegar={acoplado ? undefined : () => setAbierto(false)} /> : m.texto}</div>
          {m.propuestas.length > 0 && (
            <div className="w-full max-w-[90%]">
              {m.propuestas.map((p, j) => {
                const clave = `${i}:${j}`;
                const descartar = () => setConv((c) => ({ ...c, estados: { ...c.estados, [clave]: "descartada" } }));
                if (p.tipo === "crear_paciente") {
                  return <TarjetaPaciente key={clave} propuesta={p} estado={conv.estados[clave]} alDescartar={descartar}
                    alCreado={() => setConv((c) => ({ ...c, estados: { ...c.estados, [clave]: "hecha" } }))} />;
                }
                return <TarjetaPropuesta key={clave} propuesta={p} estado={conv.estados[clave]} error={conv.errores[clave] || undefined}
                  alConfirmar={() => confirmar(clave, p)} alDescartar={descartar} />;
              })}
            </div>
          )}
        </div>
      ))}
      {envio.isPending && <p role="status" className="flex items-center gap-2 text-sm text-tinta-suave"><Loader2 className="size-4 animate-spin" aria-hidden /> Pensando…</p>}
      {fallo && <Aviso>{fallo}</Aviso>}
    </div>

    <form onSubmit={enviar} className="border-t border-linea px-4 py-3">
      {restantes <= POCOS_MENSAJES && (
        <p className="mb-1 text-xs text-tinta-suave">{restantes === 1 ? "Te queda 1 mensaje hoy." : `Te quedan ${restantes} mensajes hoy.`}</p>
      )}
      <div className="flex items-end gap-2">
        <textarea ref={entrada} aria-label="Escribe tu mensaje" rows={2} maxLength={MAX_TEXTO} value={borrador} placeholder="Escribe tu mensaje…"
          onChange={(e) => setBorrador(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) enviar(e); }}
          className="w-full resize-none rounded-[var(--radius-control)] border border-zinc-300 bg-papel px-3 py-2 text-sm text-tinta placeholder:text-zinc-500" />
        <Boton type="submit" disabled={envio.isPending || !borrador.trim()} aria-label="Enviar"><Send className="size-4" aria-hidden /></Boton>
      </div>
      <p className="mt-1 text-right text-xs text-tinta-suave" aria-hidden>{borrador.length}/{MAX_TEXTO}</p>
    </form>
  </>);
  const boton = (props: object = {}) => (
    <button aria-label="Asistente" {...props} className={cn("flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium hover:bg-zinc-100", acoplado && abierto && "bg-zinc-100")}>
      <Sparkles className="size-5" aria-hidden /><span className="hidden sm:inline">Asistente</span>
    </button>
  );

  if (acoplado) {
    return (<>
      {boton({ "aria-expanded": abierto, onClick: () => setAbierto(!abierto) })}
      {abierto && createPortal(
        // En <body>: dentro del encabezado (que tiene backdrop-blur) `fixed` quedaría atado a él y no a la ventana.
        // Sin fondo oscuro ni foco atrapado: se puede seguir usando el resto del panel con el asistente abierto.
        <aside aria-label="Asistente" className="fixed inset-y-0 right-0 z-30 flex w-96 flex-col border-l border-linea bg-papel shadow-xl"
          onKeyDown={(e) => { if (e.key === "Escape" && e.currentTarget.contains(e.target as Node)) setAbierto(false); }}>
          {cuerpo(<h2 className="text-lg font-semibold">Asistente</h2>, <p className="text-xs text-tinta-suave">{AVISO}</p>,
            <button aria-label="Cerrar" onClick={() => setAbierto(false)} className="rounded-md p-1 hover:bg-zinc-100"><X className="size-5" /></button>)}
        </aside>, document.body,
      )}
    </>);
  }

  return (
    <Dialog.Root open={abierto} onOpenChange={setAbierto}>
      <Dialog.Trigger asChild>{boton()}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content onOpenAutoFocus={(e) => { e.preventDefault(); entrada.current?.focus(); }}
          className="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-papel shadow-2xl md:max-w-md">
          {cuerpo(<Dialog.Title className="text-lg font-semibold">Asistente</Dialog.Title>,
            <Dialog.Description className="text-xs text-tinta-suave">{AVISO}</Dialog.Description>,
            <Dialog.Close aria-label="Cerrar" className="rounded-md p-1 hover:bg-zinc-100"><X className="size-5" /></Dialog.Close>)}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
