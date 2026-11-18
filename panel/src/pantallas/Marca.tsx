/** Distintivo en texto: el nombre del negocio dentro del aro iridiscente. El logotipo original no se incluye. */
export function Distintivo({ nombre, grande }: { nombre: string; grande?: boolean }) {
  return (
    <span className="flex items-center gap-3">
      <span className="aro" aria-hidden><span className={`flex items-center justify-center font-semibold ${grande ? "size-14 text-xl" : "size-9 text-sm"}`}>{nombre.slice(0, 1).toUpperCase()}</span></span>
      <span className={`font-semibold uppercase tracking-[0.2em] ${grande ? "text-lg" : "text-xs"}`}>{nombre}</span>
    </span>
  );
}
