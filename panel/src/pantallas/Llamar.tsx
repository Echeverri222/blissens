// Lo que la auxiliar necesita al lado de un nombre para llamar: teléfono, WhatsApp y registrar que el paciente confirmó.
import { Check, MessageCircle, Phone } from "lucide-react";
import { api } from "@/api/cliente";
import { useAccion } from "@/api/consultas";
import { digitosWhatsApp } from "@/lib/solicitudes";
import { Boton } from "@/ui/controles";

const ENLACE = "inline-flex items-center gap-1 font-medium text-sky-800 underline";

export function EnlacesContacto({ celular }: { celular?: string | null }) {
  if (!celular || !/\d/.test(celular)) return null;
  const wa = digitosWhatsApp(celular);
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <a className={ENLACE} href={`tel:${celular.replace(/[^\d+]/g, "")}`}><Phone className="size-4" aria-hidden /> {celular}</a>
      {wa && <a className={ENLACE} href={`https://wa.me/${wa}`} target="_blank" rel="noopener noreferrer"><MessageCircle className="size-4" aria-hidden /> WhatsApp</a>}
    </span>
  );
}

/** Registra la confirmación dada por teléfono. Tras el éxito la fila sale sola de la lista (se vuelve a consultar todo). */
export function BotonConfirmo({ citaId, pequeno = true, alExito }: { citaId: number; pequeno?: boolean; alExito?: () => void }) {
  const m = useAccion(() => api.citas.confirmar(citaId), { ok: "Cita confirmada", alExito });
  return <Boton pequeno={pequeno} disabled={m.isPending} onClick={() => m.mutate()}><Check className="size-4" aria-hidden /> Confirmó</Boton>;
}
