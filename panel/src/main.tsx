import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@fontsource-variable/outfit";
import "./estilos.css";
import { Rutas } from "./App";
import { ProveedorSesion } from "./sesion/Sesion";
import { ProveedorAvisos } from "./sesion/avisos";

// La caché vive solo en memoria: ningún dato de pacientes se guarda en el navegador (PRD #3 §6.10).
const cliente = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: true, retry: (n, e) => n < 1 && !(e as { status?: number }).status } },
});

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <QueryClientProvider client={cliente}>
      <BrowserRouter basename="/panel">
        <ProveedorAvisos><ProveedorSesion><Rutas /></ProveedorSesion></ProveedorAvisos>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
