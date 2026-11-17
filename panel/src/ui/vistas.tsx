import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Inbox, Loader2, Lock } from "lucide-react";
import { ApiError } from "@/api/cliente";
import { comportamientoDe } from "@/lib/errores";
import { cn } from "@/lib/utils";

export function Cargando({ texto = "Cargando…", pantalla }: { texto?: string; pantalla?: boolean }) {
  return (
    <div role="status" className={cn("flex items-center justify-center gap-2 p-8 text-sm text-tinta-suave", pantalla && "min-h-dvh")}>
      <Loader2 className="size-4 animate-spin" aria-hidden /> {texto}
    </div>
  );
}

export function Vacio({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <Inbox className="size-8 text-zinc-400" aria-hidden />
      <p className="font-medium">{titulo}</p>
      {children && <p className="max-w-md text-sm text-tinta-suave">{children}</p>}
    </div>
  );
}

export function NoDisponible() {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <Lock className="size-8 text-zinc-400" aria-hidden />
      <h2 className="text-lg font-semibold">Esto no está disponible</h2>
      <p className="max-w-md text-sm text-tinta-suave">No existe o no tienes permiso para verlo.</p>
      <Link to="/agenda" className="rounded-[var(--radius-control)] bg-marca px-4 py-2 text-sm font-medium text-white">Volver al inicio</Link>
    </div>
  );
}

export function ErrorVista({ error, reintentar, pantalla }: { error: unknown; reintentar?: () => void; pantalla?: boolean }) {
  if (error instanceof ApiError && comportamientoDe(error.codigo) === "no_disponible") return <NoDisponible />;
  const mensaje = error instanceof ApiError ? error.mensaje : "Algo salió mal. Inténtalo de nuevo.";
  return (
    <div role="alert" className={cn("flex flex-col items-center gap-3 p-8 text-center", pantalla && "min-h-dvh justify-center")}>
      <AlertTriangle className="size-8 text-rose-600" aria-hidden />
      <p className="max-w-md text-sm">{mensaje}</p>
      {reintentar && <button onClick={reintentar} className="rounded-[var(--radius-control)] border border-linea bg-papel px-4 py-2 text-sm font-medium">Reintentar</button>}
    </div>
  );
}

export function Aviso({ tipo = "error", children }: { tipo?: "error" | "info" | "aviso"; children: ReactNode }) {
  const clases = tipo === "error" ? "bg-rose-50 text-rose-950 border-rose-200" : tipo === "aviso" ? "bg-amber-50 text-amber-950 border-amber-200" : "bg-sky-50 text-sky-950 border-sky-200";
  return <div role={tipo === "error" ? "alert" : "status"} className={cn("rounded-[var(--radius-control)] border px-3 py-2 text-sm", clases)}>{children}</div>;
}

/** Resultado de una consulta: cargando, error con reintento, vacío o contenido. */
export function Consulta<T>({ q, vacio, children }: {
  q: { isPending: boolean; error: unknown; data: T | undefined; refetch: () => unknown };
  vacio?: (d: T) => boolean;
  children: (d: T) => ReactNode;
}) {
  if (q.isPending) return <Cargando />;
  if (q.error || q.data === undefined) return <ErrorVista error={q.error} reintentar={() => void q.refetch()} />;
  if (vacio?.(q.data)) return null;
  return <>{children(q.data)}</>;
}
