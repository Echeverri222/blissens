/** Identidad de marca: logotipo oficial para Blissens y distintivo con aro iridiscente para otros negocios.
 * `soloInicial` (menú contraído): solo el aro con la inicial, porque el logotipo no cabe. */
export function Distintivo({ nombre, grande, claro, soloInicial }: { nombre: string; grande?: boolean; claro?: boolean; soloInicial?: boolean }) {
  const esBlissens = nombre.toLowerCase().includes("blissens");
  if (esBlissens && !soloInicial) {
    return (
      <span className="inline-flex items-center gap-2.5">
        <img
          src="/static/sitio/logo-1024x110.png"
          alt={nombre}
          width={1024}
          height={110}
          className={`${grande ? "h-6" : claro ? "h-3.5 sm:h-4" : "h-4"} w-auto select-none ${claro ? "" : "invert"}`}
        />
      </span>
    );
  }
  return (
    <span className="flex items-center gap-3">
      <span className="aro" aria-hidden>
        <span className={`flex items-center justify-center font-serif font-normal ${grande ? "size-12 text-xl" : "size-8 text-sm"}`}>
          {nombre.slice(0, 1).toUpperCase()}
        </span>
      </span>
      {soloInicial ? <span className="sr-only">{nombre}</span>
        : <span className={`font-semibold uppercase tracking-[0.18em] ${grande ? "text-base" : "text-xs"}`}>{nombre}</span>}
    </span>
  );
}
