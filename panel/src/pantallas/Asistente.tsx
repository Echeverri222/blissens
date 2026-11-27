// Asistente del equipo: un cajón disponible en toda pantalla. El asistente NO ejecuta nada: cada propuesta es una acción
// preparada que la persona confirma, y se ejecuta con los mismos endpoints (y las mismas reglas) que el resto del panel.
import { useEffect, useRef, useState, type FormEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, RotateCcw, Send, Sparkles, X } from "lucide-react";
import { ApiError, api } from "@/api/cliente";
import { useAccion } from "@/api/consultas";
import type { Propuesta } from "@/api/tipos";
import { cn } from "@/lib/utils";
import { Boton, Confirmar } from "@/ui/controles";
import { Aviso } from "@/ui/vistas";

const MAX_TEXTO = 1000;
const POCOS_MENSAJES = 5;

interface Mensaje { rol: "usuario" | "asistente"; texto: string; propuestas: Propuesta[] }
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
      default: return Promise.reject(new Error("tipo desconocido"));
    }
  } catch (e) {
    return Promise.reject(e);
  }
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

export function Asistente() {
  const qc = useQueryClient();
  const estado = useQuery({ queryKey: ["asistente", "estado"], queryFn: api.asistente.estado, retry: false, staleTime: 5 * 60_000 });
  const [abierto, setAbierto] = useState(false);
  const [conv, setConv] = useState<Conversacion>(VACIA);
  const [borrador, setBorrador] = useState("");
  const [fallo, setFallo] = useState<string | null>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);
  const lista = useRef<HTMLDivElement>(null);

  const envio = useMutation({
    mutationFn: (v: { texto: string; id: number | null }) => api.asistente.enviar(v.texto, v.id),
    onSuccess: (r) => {
      setConv((c) => ({ ...c, id: r.conversacion_id ?? c.id, mensajes: [...c.mensajes, { rol: "asistente", texto: r.respuesta, propuestas: r.propuestas }] }));
      void qc.invalidateQueries({ queryKey: ["asistente", "estado"] });
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

  return (
    <Dialog.Root open={abierto} onOpenChange={setAbierto}>
      <Dialog.Trigger asChild>
        <button aria-label="Asistente" className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium hover:bg-zinc-100">
          <Sparkles className="size-5" aria-hidden /><span className="hidden sm:inline">Asistente</span>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content onOpenAutoFocus={(e) => { e.preventDefault(); entrada.current?.focus(); }}
          className="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-papel shadow-2xl md:max-w-md">
          <div className="flex items-start justify-between gap-4 border-b border-linea px-4 py-3">
            <div>
              <Dialog.Title className="text-lg font-semibold">Asistente</Dialog.Title>
              <Dialog.Description className="text-xs text-tinta-suave">
                Puede equivocarse. Te propone acciones y solo se hacen si las confirmas.
              </Dialog.Description>
            </div>
            <div className="flex items-center gap-1">
              <Boton variante="fantasma" pequeno onClick={nueva} disabled={envio.isPending || (!conv.mensajes.length && !conv.id)}>
                <RotateCcw className="size-4" aria-hidden /> Nueva conversación</Boton>
              <Dialog.Close aria-label="Cerrar" className="rounded-md p-1 hover:bg-zinc-100"><X className="size-5" /></Dialog.Close>
            </div>
          </div>

          <div ref={lista} role="log" aria-live="polite" aria-label="Conversación con el asistente" className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {conv.mensajes.length === 0 && !envio.isPending && (
              <p className="text-sm text-tinta-suave">Pregúntame por la agenda, los pendientes o los pacientes, o pídeme preparar una acción.</p>
            )}
            {conv.mensajes.map((m, i) => (
              <div key={i} className={cn("flex flex-col", m.rol === "usuario" ? "items-end" : "items-start")}>
                <div className={cn("max-w-[90%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm",
                  m.rol === "usuario" ? "bg-marca text-white" : "bg-zinc-100 text-tinta")}>{m.texto}</div>
                {m.propuestas.length > 0 && (
                  <div className="w-full max-w-[90%]">
                    {m.propuestas.map((p, j) => {
                      const clave = `${i}:${j}`;
                      return <TarjetaPropuesta key={clave} propuesta={p} estado={conv.estados[clave]} error={conv.errores[clave] || undefined}
                        alConfirmar={() => confirmar(clave, p)} alDescartar={() => setConv((c) => ({ ...c, estados: { ...c.estados, [clave]: "descartada" } }))} />;
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
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
