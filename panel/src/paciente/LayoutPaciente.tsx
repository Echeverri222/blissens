import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Distintivo } from "@/pantallas/Marca";

export function LayoutPaciente({ children, titulo }: { children: ReactNode; titulo?: string }) {
  return (
    <div className="min-h-dvh bg-fondo text-tinta flex flex-col justify-between selection:bg-menta/30 selection:text-tinta">
      <header className="border-b border-linea bg-papel/80 backdrop-blur sticky top-0 z-20">
        <div className="mx-auto max-w-md px-4 py-3.5 flex items-center justify-between">
          <Link to="/agendar" className="inline-flex hover:opacity-90 transition-opacity">
            <Distintivo nombre="Blissens Odontología" />
          </Link>
          {titulo && <span className="text-xs font-medium text-tinta-suave">{titulo}</span>}
        </div>
      </header>

      <main className="mx-auto w-full max-w-md flex-1 px-4 py-6">
        {children}
      </main>

      <footer className="border-t border-linea bg-papel py-4 text-center text-xs text-tinta-suave">
        <div className="mx-auto max-w-md px-4 space-y-1">
          <p className="font-medium text-tinta">Blissens Odontología & Estética Dental</p>
          <p>Atención personalizada y agendamiento seguro sin contraseñas.</p>
        </div>
      </footer>
    </div>
  );
}
