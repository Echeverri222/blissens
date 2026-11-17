import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { api, ApiError } from "@/api/cliente";
import { useSesion } from "@/sesion/Sesion";
import { Boton, Entrada } from "@/ui/controles";
import { Aviso } from "@/ui/vistas";
import { Distintivo } from "./Marca";

/** Tras recibir una contraseña temporal no se puede usar nada más hasta cambiarla. */
export function ClaveObligatoria() {
  const { sesion, establecer, salir } = useSesion();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  if (!sesion.debe_cambiar_clave) return <Navigate to="/agenda" replace />;

  async function enviar(ev: FormEvent) {
    ev.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await api.sesion.cambiarClave(actual, nueva);
      establecer(await api.sesion.actual()); // al llegar la sesión nueva, el Navigate de abajo lleva al inicio
    } catch (e) {
      setError(e instanceof ApiError ? e.mensaje : "Algo salió mal. Inténtalo de nuevo.");
      setEnviando(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-marca px-4 text-white">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2"><Distintivo nombre={sesion.negocio?.nombre ?? "Estud-IA"} grande /></div>
        <form onSubmit={(e) => void enviar(e)} aria-label="Cambiar contraseña temporal" className="space-y-4 rounded-2xl bg-papel p-6 text-tinta shadow-xl">
          <h1 className="text-lg font-semibold">Elige tu contraseña</h1>
          <p className="text-sm text-tinta-suave">Ingresaste con una contraseña temporal. Cámbiala para continuar (mínimo 8 caracteres).</p>
          {error && <Aviso>{error}</Aviso>}
          <Entrada etiqueta="Contraseña temporal" type="password" autoComplete="current-password" value={actual} onChange={(x) => setActual(x.target.value)} required />
          <Entrada etiqueta="Contraseña nueva" type="password" autoComplete="new-password" value={nueva} onChange={(x) => setNueva(x.target.value)} required />
          <div className="flex gap-2">
            <Boton type="submit" disabled={enviando}>Guardar</Boton>
            <Boton variante="secundario" onClick={() => void salir()}>Cerrar sesión</Boton>
          </div>
        </form>
      </div>
    </main>
  );
}
