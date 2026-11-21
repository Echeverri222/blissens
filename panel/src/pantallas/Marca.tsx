/** Logotipo y monograma oficial de BLISSENS con el espectro holográfico. */

export function MonogramaBS({ tamano = 36 }: { tamano?: number }) {
  return (
    <span
      className="aro shrink-0 select-none shadow-sm"
      style={{ width: tamano, height: tamano }}
      aria-hidden
    >
      <span className="flex size-full items-center justify-center rounded-full bg-marca font-bold tracking-tighter text-white">
        <svg
          viewBox="0 0 100 100"
          className="size-3/5"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="blissensGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#E58CA8" />
              <stop offset="20%" stopColor="#E7B596" />
              <stop offset="40%" stopColor="#8EE0C6" />
              <stop offset="60%" stopColor="#58C2D8" />
              <stop offset="80%" stopColor="#9C85E5" />
              <stop offset="100%" stopColor="#BF76D6" />
            </linearGradient>
          </defs>
          <path
            d="M 28 20 H 60 C 72 20 78 28 78 37 C 78 46 70 51 58 52 C 72 53 80 61 80 72 C 80 83 70 90 56 90 H 26"
            stroke="url(#blissensGrad)"
            strokeWidth="9"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M 26 52 H 54 C 64 52 70 58 70 65 C 70 73 63 79 52 79 H 26"
            stroke="url(#blissensGrad)"
            strokeWidth="9"
            strokeLinecap="round"
          />
        </svg>
      </span>
    </span>
  );
}

export function LogotipoBlissens({ grande }: { grande?: boolean }) {
  return (
    <span className={`font-semibold tracking-[0.25em] uppercase ${grande ? "text-xl" : "text-sm"}`}>
      <span className="texto-holografico">BLISSENS</span>
    </span>
  );
}

export function Distintivo({ nombre, grande }: { nombre: string; grande?: boolean }) {
  const esBlissens = nombre.toLowerCase().includes("blissens");
  return (
    <span className="flex items-center gap-3">
      {esBlissens ? (
        <MonogramaBS tamano={grande ? 54 : 36} />
      ) : (
        <span className="aro" aria-hidden>
          <span className={`flex items-center justify-center font-semibold ${grande ? "size-14 text-xl" : "size-9 text-sm"}`}>
            {nombre.slice(0, 1).toUpperCase()}
          </span>
        </span>
      )}
      <span className={`font-semibold uppercase tracking-[0.2em] ${grande ? "text-lg" : "text-xs"}`}>
        {esBlissens ? <span className="texto-holografico font-bold">{nombre}</span> : nombre}
      </span>
    </span>
  );
}
