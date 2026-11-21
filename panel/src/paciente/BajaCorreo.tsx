import { useState } from "react";
import { useParams } from "react-router-dom";
import { MailX, CheckCircle } from "lucide-react";
import { api, ApiError } from "@/api/cliente";
import { Boton, Tarjeta } from "@/ui/controles";
import { Aviso } from "@/ui/vistas";
import { LayoutPaciente } from "./LayoutPaciente";

export function BajaCorreo() {
  const { token } = useParams<{ token: string }>();
  const [listo, setListo] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmarBaja() {
    if (!token) return;
    setError(null);
    setEnviando(true);
    try {
      await api.publico.bajaCorreo({ token });
      setListo(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.mensaje : "Algo salió mal. Inténtalo de nuevo.");
      setEnviando(false);
    }
  }

  return (
    <LayoutPaciente titulo="Baja de notificaciones">
      <Tarjeta className="p-6 text-center space-y-4">
        {listo ? (
          <>
            <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-menta/20 text-emerald-800">
              <CheckCircle className="size-6" />
            </div>
            <h1 className="text-lg font-semibold">Listo, no te enviaremos más correos</h1>
            <p className="text-xs text-tinta-suave">
              Dejaste de recibir correos informativos de Blissens Odontología. Esto no afecta tus recordatorios por WhatsApp.
            </p>
          </>
        ) : (
          <>
            <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-zinc-100 text-tinta-suave">
              <MailX className="size-6" />
            </div>
            <h1 className="text-lg font-semibold">¿Dejar de recibir correos?</h1>
            <p className="text-xs text-tinta-suave">
              Dejarás de recibir notificaciones por correo electrónico sobre tus citas. Si necesitas cancelaciones futuras, mantendrás activo el canal de WhatsApp.
            </p>
            {error && <Aviso tipo="error">{error}</Aviso>}
            <Boton
              onClick={confirmarBaja}
              disabled={enviando}
              variante="peligro"
              className="w-full mt-2"
            >
              {enviando ? "Procesando…" : "Sí, dar de baja mi correo"}
            </Boton>
          </>
        )}
      </Tarjeta>
    </LayoutPaciente>
  );
}
