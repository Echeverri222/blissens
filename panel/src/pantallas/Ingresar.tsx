import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "@/api/cliente";
import { Boton, Entrada } from "@/ui/controles";
import { Aviso } from "@/ui/vistas";
import { Distintivo } from "./Marca";
import { origenSeguro, useEstadoSesion, useSesionOpcional } from "@/sesion/Sesion";
import { useQueryClient } from "@tanstack/react-query";
import { CLAVE_SESION } from "@/sesion/Sesion";

export function Ingresar() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const e = useEstadoSesion();
  const ya = useSesionOpcional();
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
    <main className="flex min-h-dvh items-center justify-center bg-marca px-4 text-white">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2"><Distintivo grande /><p className="text-sm text-zinc-400">Panel de gestión de citas</p></div>
        <form onSubmit={enviar} className="space-y-4 rounded-2xl bg-papel p-6 text-tinta shadow-xl" aria-label="Iniciar sesión">
          <h1 className="text-lg font-semibold">Iniciar sesión</h1>
          {e.error && !e.hay && <Aviso tipo="aviso">No se pudo comprobar la sesión: {e.error.message}</Aviso>}
          {error && <Aviso>{error}</Aviso>}
          <Entrada etiqueta="Usuario" autoComplete="username" autoCapitalize="none" value={usuario} onChange={(x) => setUsuario(x.target.value)} required />
          <Entrada etiqueta="Contraseña" type="password" autoComplete="current-password" value={clave} onChange={(x) => setClave(x.target.value)} required />
          <Boton type="submit" className="w-full" disabled={enviando}>{enviando ? "Entrando…" : "Entrar"}</Boton>
          <p className="text-xs text-tinta-suave">¿Olvidaste tu contraseña? Pídesela a quien administra el sistema.</p>
        </form>
        <div className="mt-4 h-0.5 rounded-full acento-activo" aria-hidden />
      </div>
    </main>
  );
}
