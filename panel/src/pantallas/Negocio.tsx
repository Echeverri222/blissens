import { useState } from "react";
import { Navigate } from "react-router-dom";
import { api, ApiError } from "@/api/cliente";
import { useSesion } from "@/sesion/Sesion";
import { Boton } from "@/ui/controles";
import { Aviso } from "@/ui/vistas";
import { Distintivo } from "./Marca";

/** Con acceso a varios negocios se elige con cuál trabajar; también sirve para cambiar sin volver a ingresar. */
export function ElegirNegocio() {
  const { sesion, establecer, salir } = useSesion();
  const [listo, setListo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [eligiendo, setEligiendo] = useState<number | null>(null);

  async function elegir(id: number) {
    setError(null);
    setEligiendo(id);
    try {
      establecer(await api.sesion.elegirNegocio(id));
      setListo(true); // la sesión nueva llega al contexto un instante después: se navega al verla, no antes
    } catch (e) {
      setError(e instanceof ApiError ? e.mensaje : "Algo salió mal. Inténtalo de nuevo.");
      setEligiendo(null);
    }
  }

  if (listo && sesion.rol) return <Navigate to="/agenda" replace />;
  return (
    <main className="flex min-h-dvh items-center justify-center bg-marca px-4 text-white">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2"><Distintivo nombre="Estud-IA" grande /></div>
        <section aria-label="Elegir negocio" className="space-y-3 rounded-2xl bg-papel p-6 text-tinta shadow-xl">
          <h1 className="text-lg font-semibold">¿Con qué negocio vas a trabajar?</h1>
          {error && <Aviso>{error}</Aviso>}
          {sesion.negocios.length === 0 && <Aviso tipo="aviso">No tienes acceso a ningún negocio. Pídelo a quien administra el sistema.</Aviso>}
          <ul className="space-y-2">
            {sesion.negocios.map((n) => (
              <li key={n.id}>
                <Boton variante={n.id === sesion.negocio?.id ? "primario" : "secundario"} className="w-full justify-start" disabled={eligiendo !== null}
                  onClick={() => void elegir(n.id)}>{n.nombre}</Boton>
              </li>
            ))}
          </ul>
          <Boton variante="secundario" pequeno onClick={() => void salir()}>Cerrar sesión</Boton>
        </section>
      </div>
    </main>
  );
}
