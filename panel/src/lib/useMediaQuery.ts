import { useEffect, useState } from "react";

/** Coincidencia con una media query; sin `matchMedia` (pruebas) se asume escritorio. */
export function useMediaQuery(consulta: string): boolean {
  const lee = () => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(consulta).matches : false);
  const [coincide, setCoincide] = useState(lee);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const m = window.matchMedia(consulta);
    const f = () => setCoincide(m.matches);
    f();
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, [consulta]);
  return coincide;
}
