import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "@/api/cliente";
import { Boton, Entrada } from "@/ui/controles";
import { Aviso } from "@/ui/vistas";
import { Distintivo } from "./Marca";
import { origenSeguro, useEstadoSesion, useSesionOpcional } from "@/sesion/Sesion";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CLAVE_SESION } from "@/sesion/Sesion";

export function Ingresar() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const e = useEstadoSesion();
  const ya = useSesionOpcional();
  const marca = useQuery({ queryKey: ["marca"], queryFn: api.marca, retry: false });
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const destino = origenSeguro(params.get("de"));
  if (ya && !enviando) return <Navigate to={destino} replace />;

  async function enviar(ev: FormEvent) {
    ev.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const s = await api.sesion.entrar(usuario.trim(), clave);
      qc.removeQueries({ predicate: (x) => x.queryKey[0] !== CLAVE_SESION[0] });
      qc.setQueryData(CLAVE_SESION, s);
      nav(destino, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.mensaje : "Algo salió mal. Inténtalo de nuevo.");
      setClave("");
      setEnviando(false);
    }
  }

  return (
    <main className="portada-brillo relative flex min-h-dvh flex-col bg-marca px-4 py-6 text-white">
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-3">
        <a href="/" className="inline-flex min-h-11 items-center gap-2 rounded-full border border-white/20 px-4 py-2 text-xs font-medium text-zinc-200 transition-colors hover:border-white/60 hover:bg-white/10 hover:text-white">
          <span aria-hidden>&larr;</span> Volver al sitio
        </a>
        <a href="/agendar" className="inline-flex min-h-11 items-center px-1 py-2 text-xs font-medium text-zinc-300 transition-colors hover:text-white">
          ¿Eres paciente? Agendar cita
        </a>
      </div>
      <div className="mx-auto my-auto w-full max-w-sm py-10">
        <div className="mb-8 flex flex-col items-center gap-2.5 text-center">
          <Distintivo nombre={marca.data?.nombre ?? "Estud-IA"} grande />
          <p className="font-serif text-base tracking-wide text-zinc-300">Panel de gestión de citas</p>
        </div>
        <form onSubmit={enviar} className="tarjeta-acento space-y-4 rounded-2xl bg-papel p-7 text-tinta shadow-2xl" aria-label="Iniciar sesión">
          <h1 className="text-xl font-semibold tracking-tight">Iniciar sesión</h1>
          {e.error && !e.hay && <Aviso tipo="aviso">No se pudo comprobar la sesión: {e.error.message}</Aviso>}
          {error && <Aviso>{error}</Aviso>}
          <Entrada etiqueta="Usuario" autoComplete="username" autoCapitalize="none" value={usuario} onChange={(x) => setUsuario(x.target.value)} required />
          <Entrada etiqueta="Contraseña" type="password" autoComplete="current-password" value={clave} onChange={(x) => setClave(x.target.value)} required />
          <Boton type="submit" className="w-full" disabled={enviando}>{enviando ? "Entrando…" : "Entrar"}</Boton>
          <p className="text-xs leading-relaxed text-tinta-suave">¿Olvidaste tu contraseña? Pídesela a quien administra el sistema.</p>
        </form>
      </div>
    </main>
  );
}
