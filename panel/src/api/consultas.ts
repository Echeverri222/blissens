// Datos remotos con caché y revalidación (TanStack Query): al recuperar el foco, cada 60 s en lo vivo y tras cada acción.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./cliente";
import { comportamientoDe } from "@/lib/errores";
import { useAvisos } from "@/sesion/avisos";

export const CADA_MINUTO = 60_000;
const CATALOGO = { staleTime: 10 * 60_000 };

export const useProfesionales = () => useQuery({ queryKey: ["profesionales"], queryFn: api.catalogos.profesionales, ...CATALOGO });
export const useServicios = () => useQuery({ queryKey: ["servicios"], queryFn: api.catalogos.servicios, ...CATALOGO });
export const useMotivos = () => useQuery({ queryKey: ["motivos"], queryFn: api.catalogos.motivos, ...CATALOGO });

export const useAgenda = (desde: string, hasta: string, profesionalId?: number) =>
  useQuery({ queryKey: ["agenda", desde, hasta, profesionalId ?? null], queryFn: () => api.agenda.rango(desde, hasta, profesionalId), refetchInterval: CADA_MINUTO });

export const useCita = (id: number | null) =>
  useQuery({ queryKey: ["cita", id], queryFn: () => api.citas.detalle(id!), enabled: id !== null, refetchInterval: CADA_MINUTO });

export const useConteoBandejas = (activo = true) =>
  useQuery({ queryKey: ["bandejas", "conteo"], queryFn: api.bandejas.conteo, refetchInterval: CADA_MINUTO, enabled: activo });

/**
 * Una acción que modifica. Tras el éxito se vuelve a consultar todo; los errores siguen la tabla de `errores.ts`:
 * los de formulario se dejan en `error` para mostrarlos junto al formulario, el resto se avisan.
 */
export function useAccion<V, D>(fn: (v: V) => Promise<D>, opts: { ok?: string | ((d: D, v: V) => string); alExito?: (d: D, v: V) => void } = {}) {
  const qc = useQueryClient();
  const { avisar } = useAvisos();
  const m = useMutation<D, Error, V>({
    mutationFn: fn,
    onSuccess: (d, v) => {
      void qc.invalidateQueries();
      if (opts.ok) avisar(typeof opts.ok === "function" ? opts.ok(d, v) : opts.ok);
      opts.alExito?.(d, v);
    },
    onError: (e, v) => {
      if (!(e instanceof ApiError)) return avisar("Algo salió mal. Inténtalo de nuevo.", "error", () => m.mutate(v));
      switch (comportamientoDe(e.codigo)) {
        case "iniciar_sesion": case "mensaje_formulario": case "mensaje_inicio": case "conflicto_bloqueo": return;
        case "recargar_espacios": case "recargar_dato": case "no_disponible":
          avisar(e.mensaje, "aviso"); void qc.invalidateQueries(); return;
        default: avisar(e.mensaje, "error", () => m.mutate(v));
      }
    },
  });
  return m;
}

export const useEspacios = (profesionalId: number | null, servicioId: number | null) =>
  useQuery({
    queryKey: ["espacios", profesionalId, servicioId],
    queryFn: () => api.citas.espacios(profesionalId!, servicioId!),
    enabled: profesionalId !== null && servicioId !== null,
  });

export const useBloqueos = (desde: string, hasta: string, profesionalId?: number) =>
  useQuery({ queryKey: ["bloqueos", desde, hasta, profesionalId ?? null], queryFn: () => api.bloqueos.listar(desde, hasta, profesionalId), refetchInterval: CADA_MINUTO });
