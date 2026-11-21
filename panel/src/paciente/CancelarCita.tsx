import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, CheckCircle2 } from "lucide-react";
import { api, ApiError } from "@/api/cliente";
import type { CatalogoEspaciosPublico } from "@/api/tipos";
import { Tarjeta } from "@/ui/controles";
import { Aviso, Consulta } from "@/ui/vistas";
import { LayoutPaciente } from "./LayoutPaciente";

export function CancelarCita() {
  const { token, id } = useParams<{ token: string; id: string }>();
  const citaId = Number(id);

  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<{ cancelada: boolean; alternativos?: CatalogoEspaciosPublico | null } | null>(null);

  const motivos = useQuery({
    queryKey: ["publico", "motivos", token],
    queryFn: () => api.publico.motivosCancelacion(token!),
    enabled: Boolean(token),
  });

  async function cancelarConMotivo(motivoId: number) {
    if (!token || !citaId) return;
    setError(null);
    setEnviando(true);

    try {
      const r = await api.publico.cancelar(citaId, { token, motivo_id: motivoId });
      setResultado({ cancelada: true, alternativos: r.espacios_alternativos });
    } catch (err) {
      setError(err instanceof ApiError ? err.mensaje : "Algo salió mal. Inténtalo de nuevo.");
      setEnviando(false);
    }
  }

  if (resultado?.cancelada) {
    return (
      <LayoutPaciente titulo="Cita cancelada">
        <Tarjeta className="p-6 text-center space-y-4">
          <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-rose-100 text-rose-700">
            <CheckCircle2 className="size-6" />
          </div>

          <h1 className="text-lg font-semibold">Tu cita ha sido cancelada</h1>
          <p className="text-xs text-tinta-suave">
            Entendemos que pueden surgir imprevistos. ¿Te gustaría reagendar para otro día libre de esta semana?
          </p>

          <div className="pt-3 space-y-2">
            <Link
              to={`/p/${token}/agendar`}
              className="inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] bg-marca px-4 py-2.5 text-sm font-medium text-white hover:bg-marca-suave transition-colors w-full"
            >
              <CalendarPlus className="size-4" /> Ver otros espacios libres
            </Link>

            <Link
              to={`/p/${token}`}
              className="inline-flex items-center justify-center rounded-[var(--radius-control)] border border-linea bg-papel px-4 py-2 text-xs font-medium text-tinta hover:bg-zinc-50 transition-colors w-full"
            >
              Volver a mis citas
            </Link>
          </div>
        </Tarjeta>
      </LayoutPaciente>
    );
  }

  return (
    <LayoutPaciente titulo="Cancelar cita">
      <div className="space-y-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">¿Deseas cancelar tu cita?</h1>
          <p className="text-xs text-tinta-suave mt-0.5">
            Cuéntanos el motivo con un solo toque. Tu respuesta nos ayuda a optimizar el servicio.
          </p>
        </div>

        {error && <Aviso tipo="error">{error}</Aviso>}

        <Consulta q={motivos}>
          {(lista) => (
            <Tarjeta className="p-4 space-y-2 border border-linea shadow-sm">
              <p className="text-xs font-semibold text-tinta-suave mb-2">Selecciona un motivo:</p>
              <div className="space-y-2">
                {lista.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    disabled={enviando}
                    onClick={() => cancelarConMotivo(m.id)}
                    className="w-full text-left rounded-lg border border-linea bg-papel p-3 text-sm font-medium text-tinta hover:border-zinc-400 hover:bg-zinc-50 transition-all active:scale-[0.99] disabled:opacity-50"
                  >
                    {m.etiqueta}
                  </button>
                ))}
              </div>
            </Tarjeta>
          )}
        </Consulta>

        <div className="text-center pt-2">
          <Link to={`/p/${token}`} className="text-xs text-tinta-suave underline hover:text-tinta">
            No cancelar, volver a mis citas
          </Link>
        </div>
      </div>
    </LayoutPaciente>
  );
}
