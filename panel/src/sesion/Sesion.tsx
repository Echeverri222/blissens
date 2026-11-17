import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, alNoAutenticado } from "@/api/cliente";
import type { Rol, Sesion } from "@/api/tipos";
import { ahoraSistema, fechaDe } from "@/lib/tiempo";
import { Cargando, ErrorVista } from "@/ui/vistas";

const REFRESCO_MS = 60_000;

interface Valor {
  sesion: Sesion;
  /** Hora del sistema (no la del navegador: el modo demo adelanta el reloj). */
  ahora: Date;
  /** Día del sistema, "YYYY-MM-DD". */
  hoy: string;
  establecer: (s: Sesion) => void;
  salir: () => Promise<void>;
}

const Ctx = createContext<Valor | null>(null);
const Estado = createContext<{ cargando: boolean; error: Error | null; reintentar: () => void; hay: boolean } | null>(null);

export const CLAVE_SESION = ["sesion"] as const;

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: CLAVE_SESION, refetchInterval: REFRESCO_MS, retry: false,
    queryFn: async (): Promise<Sesion | null> => {
      try { return await api.sesion.actual(); } catch (e) {
        if (e instanceof ApiError && e.codigo === "no_autenticado") return null;
        throw e;
      }
    },
  });

  const vaciar = useCallback(() => {
    qc.removeQueries({ predicate: (x) => x.queryKey[0] !== CLAVE_SESION[0] });
    qc.setQueryData(CLAVE_SESION, null);
  }, [qc]);

  useEffect(() => { alNoAutenticado(vaciar); return () => alNoAutenticado(null); }, [vaciar]);

  // Reloj del navegador, solo para avanzar la hora del sistema entre lecturas de la sesión.
  const [reloj, setReloj] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setReloj(Date.now()), 30_000); return () => clearInterval(t); }, []);

  const sesion = q.data ?? null;
  const leidaEn = q.dataUpdatedAt;
  const ahora = useMemo(() => (sesion ? ahoraSistema(sesion.hora_sistema, leidaEn, Math.max(reloj, leidaEn)) : new Date(reloj)),
    [sesion, leidaEn, reloj]);
  const hoy = fechaDe(ahora);

  // Cuando cambia el día del sistema las vistas se vuelven a consultar.
  const hoyPrevio = useRef(hoy);
  useEffect(() => {
    if (hoyPrevio.current === hoy) return;
    hoyPrevio.current = hoy;
    void qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== CLAVE_SESION[0] });
  }, [hoy, qc]);

  const establecer = useCallback((s: Sesion) => {
    qc.removeQueries({ predicate: (x) => x.queryKey[0] !== CLAVE_SESION[0] }); // cambio de usuario: cache vacía
    qc.setQueryData(CLAVE_SESION, s);
  }, [qc]);
  const salir = useCallback(async () => {
    try { await api.sesion.salir(); } catch { /* la sesión se descarta igual en el navegador */ }
    qc.clear();
    qc.setQueryData(CLAVE_SESION, null);
  }, [qc]);

  const valor = useMemo<Valor | null>(() => (sesion ? { sesion, ahora, hoy, establecer, salir } : null), [sesion, ahora, hoy, establecer, salir]);
  const { isPending, error, refetch } = q;
  const estado = useMemo(() => ({ cargando: isPending, error, reintentar: () => void refetch(), hay: !!sesion }),
    [isPending, error, refetch, sesion]);
  return <Estado.Provider value={estado}><Ctx.Provider value={valor}>{children}</Ctx.Provider></Estado.Provider>;
}

export function useSesion(): Valor {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSesion fuera de una ruta protegida");
  return v;
}
export const useSesionOpcional = () => useContext(Ctx);
export const useEstadoSesion = () => useContext(Estado)!;

export const inicioDelRol = (_rol: Rol) => "/agenda";

/** Guarda de rutas por rol: sin sesión lleva a iniciar sesión y recuerda el origen; con otro rol, al inicio del rol. */
export function RutaProtegida({ roles, children }: { roles?: Rol[]; children: ReactNode }) {
  const e = useEstadoSesion();
  const v = useContext(Ctx);
  const loc = useLocation();
  if (e.cargando) return <Cargando pantalla />;
  if (e.error && !v) return <ErrorVista error={e.error} reintentar={e.reintentar} pantalla />;
  if (!v) return <Navigate to={`/ingresar?de=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (roles && !roles.includes(v.sesion.rol)) return <Navigate to={inicioDelRol(v.sesion.rol)} replace />;
  return <>{children}</>;
}

/** Origen seguro tras iniciar sesión: solo rutas internas del panel. */
export const origenSeguro = (de: string | null): string =>
  de && de.startsWith("/") && !de.startsWith("//") && !de.startsWith("/ingresar") ? de : "/agenda";
