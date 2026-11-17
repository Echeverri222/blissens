/** Distintivo en texto: el nombre de la clínica dentro del aro iridiscente. El logotipo original no se incluye. */
export function Distintivo({ grande }: { grande?: boolean }) {
  return (
    <span className="flex items-center gap-3">
      <span className="aro" aria-hidden><span className={`flex items-center justify-center font-semibold ${grande ? "size-14 text-xl" : "size-9 text-sm"}`}>B</span></span>
      <span className={`font-semibold uppercase tracking-[0.2em] ${grande ? "text-lg" : "text-xs"}`}>Blissens</span>
    </span>
  );
}
