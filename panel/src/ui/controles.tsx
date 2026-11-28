import { forwardRef, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { Ban, CalendarClock, CircleCheck, CircleHelp, CheckCheck, Repeat, Star, UserX } from "lucide-react";
import { cn } from "@/lib/utils";
import { ESTADOS } from "@/lib/estados";
import type { Estado } from "@/api/tipos";

type Variante = "primario" | "secundario" | "fantasma" | "peligro";
const VARIANTES: Record<Variante, string> = {
  primario: "bg-marca text-white hover:bg-marca-suave",
  secundario: "bg-papel text-tinta border border-linea hover:bg-zinc-50",
  fantasma: "text-tinta hover:bg-zinc-100",
  peligro: "bg-rose-700 text-white hover:bg-rose-800",
};

export const Boton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; pequeno?: boolean }>(
  function Boton({ variante = "primario", pequeno, className, type = "button", ...p }, ref) {
    return (
      <button ref={ref} type={type} {...p}
        className={cn("inline-flex cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-control)] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
          pequeno ? "min-h-9 px-3 py-1.5 text-sm" : "min-h-10 px-4 py-2.5 text-sm", VARIANTES[variante], className)} />
    );
  });

const BASE_CAMPO = "w-full rounded-[var(--radius-control)] border border-zinc-300 bg-papel px-3 py-2 text-sm text-tinta placeholder:text-zinc-500 transition-colors focus:border-marca disabled:bg-zinc-100";

function Rotulo({ id, texto }: { id: string; texto: string }) {
  return <label htmlFor={id} className="mb-1 block text-sm font-medium">{texto}</label>;
}

export const Entrada = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { etiqueta: string }>(
  function Entrada({ etiqueta, className, ...p }, ref) {
    const id = useId();
    return <div className={className}><Rotulo id={id} texto={etiqueta} /><input ref={ref} id={id} className={BASE_CAMPO} {...p} /></div>;
  });

export function Seleccion({ etiqueta, className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { etiqueta: string }) {
  const id = useId();
  return <div className={className}><Rotulo id={id} texto={etiqueta} /><select id={id} className={BASE_CAMPO} {...p}>{children}</select></div>;
}

export function AreaTexto({ etiqueta, className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement> & { etiqueta: string }) {
  const id = useId();
  return <div className={className}><Rotulo id={id} texto={etiqueta} /><textarea id={id} rows={2} className={BASE_CAMPO} {...p} /></div>;
}

export function Casilla({ etiqueta, ...p }: InputHTMLAttributes<HTMLInputElement> & { etiqueta: ReactNode }) {
  const id = useId();
  return (
    <div className="flex items-start gap-2">
      <input id={id} type="checkbox" className="mt-0.5 size-4 accent-black" {...p} />
      <label htmlFor={id} className="text-sm">{etiqueta}</label>
    </div>
  );
}

export function Tarjeta({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-[var(--radius-tarjeta)] border border-linea bg-papel", className)} {...p} />;
}

const ICONOS = { calendario: CalendarClock, check: CircleCheck, pregunta: CircleHelp, doble: CheckCheck, "usuario-x": UserX, x: Ban, repetir: Repeat };

export function IconoEstado({ estado, className }: { estado: Estado; className?: string }) {
  const Icono = ICONOS[ESTADOS[estado].icono as keyof typeof ICONOS];
  return <Icono className={cn("size-3.5 shrink-0", className)} aria-hidden />;
}

export function EtiquetaEstado({ estado, className }: { estado: Estado; className?: string }) {
  const e = ESTADOS[estado];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", e.clases, className)}>
      <IconoEstado estado={estado} />{e.texto}
    </span>
  );
}

/** Pacientes de alto valor para la clínica: internacionales y deportistas de alto nivel. Sin marca no pinta nada. */
export function AltoValor({ internacional, deportista, className }: { internacional?: boolean; deportista?: boolean; className?: string }) {
  if (!internacional && !deportista) return null;
  const texto = [internacional && "Internacional", deportista && "Deportista"].filter(Boolean).join(" · ");
  return (
    <span title="Paciente de alto valor: sale primero en las bandejas" className={cn("inline-flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-950", className)}>
      <Star className="size-3" aria-hidden />{texto}
    </span>
  );
}

/** Hoja de detalle: panel lateral sobre la vista actual (pantalla completa en celular). */
export function Hoja({ abierta, alCerrar, titulo, descripcion, ancho = "md:max-w-md", children }: {
  abierta: boolean; alCerrar: () => void; titulo: string; descripcion?: string; ancho?: string; children: ReactNode;
}) {
  return (
    <Dialog.Root open={abierta} onOpenChange={(o) => { if (!o) alCerrar(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content aria-describedby={descripcion ? undefined : undefined}
          className={cn("fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-papel shadow-2xl", ancho)}>
          <div className="flex items-start justify-between gap-4 border-b border-linea px-5 py-4">
            <div>
              <Dialog.Title className="text-lg font-semibold">{titulo}</Dialog.Title>
              <Dialog.Description className={descripcion ? "text-sm text-tinta-suave" : "sr-only"}>{descripcion ?? titulo}</Dialog.Description>
            </div>
            <Dialog.Close aria-label="Cerrar" className="rounded-md p-1 hover:bg-zinc-100"><X className="size-5" /></Dialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Acción que pide confirmación antes de ejecutarse (envía mensajes al paciente o es difícil de deshacer). */
/** Toda acción que cambia datos pasa por aquí: un clic por error no debe registrar nada. `pregunta` dice a quién y qué
 * afecta (nombre, fecha) y `si` repite la acción en el botón que la ejecuta. */
export function Confirmar({ etiqueta, pregunta, alConfirmar, variante = "secundario", deshabilitado, pequeno, icono, titulo, si = "Sí, continuar" }: {
  etiqueta: string; pregunta: ReactNode; alConfirmar: () => void; variante?: Variante; deshabilitado?: boolean; pequeno?: boolean;
  icono?: ReactNode; titulo?: string; si?: string;
}) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild><Boton variante={variante} disabled={deshabilitado} pequeno={pequeno}>{icono}{etiqueta}</Boton></Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[71] max-h-[90dvh] w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl bg-papel p-5 shadow-2xl">
          <Dialog.Title className="text-base font-semibold">{titulo ?? etiqueta}</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-tinta-suave">{pregunta}</Dialog.Description>
          <div className="mt-4 flex justify-end gap-2">
            <Dialog.Close asChild><Boton variante="secundario" pequeno>No, volver</Boton></Dialog.Close>
            <Dialog.Close asChild><Boton variante={variante === "secundario" ? "primario" : variante} pequeno onClick={alConfirmar}>{si}</Boton></Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
