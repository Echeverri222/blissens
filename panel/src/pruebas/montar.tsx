import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Rutas } from "@/App";
import { ProveedorSesion } from "@/sesion/Sesion";
import { ProveedorAvisos } from "@/sesion/avisos";
import { enviadas, manejadores, servidor } from "./servidor";
import type { Sesion } from "@/api/tipos";

/** Monta el panel completo en una ruta, con la sesión (o su ausencia) y la red simulada. */
export function montar(ruta: string, sesion: Sesion | null) {
  enviadas.length = 0;
  servidor.use(manejadores(sesion)[0]); // solo la sesión: no pisa lo que la prueba haya registrado antes
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <ProveedorAvisos><ProveedorSesion><Rutas /></ProveedorSesion></ProveedorAvisos>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
