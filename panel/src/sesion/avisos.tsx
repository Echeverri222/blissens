import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface Aviso { id: number; texto: string; tipo: "ok" | "aviso" | "error"; reintentar?: () => void }
interface Ctx { avisar: (texto: string, tipo?: Aviso["tipo"], reintentar?: () => void) => void }
const AvisosCtx = createContext<Ctx>({ avisar: () => {} });
let contador = 0;

export function ProveedorAvisos({ children }: { children: ReactNode }) {
  const [lista, setLista] = useState<Aviso[]>([]);
  const quitar = (id: number) => setLista((l) => l.filter((a) => a.id !== id));
  const avisar = useCallback<Ctx["avisar"]>((texto, tipo = "ok", reintentar) => {
    const id = ++contador;
    setLista((l) => [...l, { id, texto, tipo, reintentar }]);
    if (!reintentar) setTimeout(() => setLista((l) => l.filter((a) => a.id !== id)), tipo === "ok" ? 4000 : 8000);
  }, []);
  const valor = useMemo(() => ({ avisar }), [avisar]);
  return (
    <AvisosCtx.Provider value={valor}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 md:bottom-6">
        {lista.map((a) => (
          <div key={a.id} role={a.tipo === "error" ? "alert" : "status"}
            className={`pointer-events-auto flex max-w-md items-start gap-3 rounded-xl px-4 py-3 text-sm shadow-lg ${
              a.tipo === "ok" ? "bg-marca text-white" : a.tipo === "aviso" ? "bg-amber-100 text-amber-950" : "bg-rose-100 text-rose-950"}`}>
            <span>{a.texto}</span>
            {a.reintentar && <button className="font-semibold underline" onClick={() => { quitar(a.id); a.reintentar!(); }}>Reintentar</button>}
            <button aria-label="Cerrar aviso" className="ml-auto opacity-70 hover:opacity-100" onClick={() => quitar(a.id)}>×</button>
          </div>
        ))}
      </div>
    </AvisosCtx.Provider>
  );
}

export const useAvisos = () => useContext(AvisosCtx);
