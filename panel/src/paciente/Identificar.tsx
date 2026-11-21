import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, PhoneCall, ArrowRight } from "lucide-react";
import { api, ApiError } from "@/api/cliente";
import { Boton, Casilla, Entrada, Tarjeta } from "@/ui/controles";
import { Aviso } from "@/ui/vistas";
import { LayoutPaciente } from "./LayoutPaciente";

export function Identificar() {
  const nav = useNavigate();
  const [documento, setDocumento] = useState("");
  const [celular, setCelular] = useState("");
  const [nombres, setNombres] = useState("");
  const [apellidos, setApellidos] = useState("");
  const [consentimiento, setConsentimiento] = useState(false);

  const [esNuevo, setEsNuevo] = useState(false);
  const [contactoPendiente, setContactoPendiente] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(ev: FormEvent) {
    ev.preventDefault();
    setError(null);
    setEnviando(true);

    try {
      const r = await api.publico.identificar({
        documento: documento.trim(),
        celular: celular.trim(),
        nombres: esNuevo ? nombres.trim() : undefined,
        apellidos: esNuevo ? apellidos.trim() : undefined,
        consentimiento: esNuevo ? consentimiento : false,
      });

      if (r.estado === "requiere_registro") {
        setEsNuevo(true);
        setEnviando(false);
        return;
      }

      if (r.estado === "contacto_pendiente") {
        setContactoPendiente(r.mensaje || "Nos pondremos en contacto contigo pronto.");
        setEnviando(false);
        return;
      }

      if (r.token) {
        nav(`/p/${r.token}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.mensaje : "Algo salió mal. Inténtalo de nuevo.");
      setEnviando(false);
    }
  }

  if (contactoPendiente) {
    return (
      <LayoutPaciente titulo="Solicitud recibida">
        <Tarjeta className="p-6 text-center space-y-4">
          <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-agua/20 text-agua">
            <PhoneCall className="size-6" />
          </div>
          <h1 className="text-lg font-semibold">Te contactaremos muy pronto</h1>
          <p className="text-sm text-tinta-suave">{contactoPendiente}</p>
          <Boton
            variante="secundario"
            className="w-full mt-4"
            onClick={() => {
              setContactoPendiente(null);
              setDocumento("");
              setCelular("");
            }}
          >
            Volver a intentar
          </Boton>
        </Tarjeta>
      </LayoutPaciente>
    );
  }

  return (
    <LayoutPaciente titulo="Portal Pacientes">
      <div className="space-y-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Agenda tu cita</h1>
          <p className="text-sm text-tinta-suave mt-1">
            Sin contraseñas. Solo necesitamos tu documento y número celular.
          </p>
        </div>

        {error && <Aviso tipo="error">{error}</Aviso>}

        <Tarjeta className="p-5 shadow-sm">
          <form onSubmit={enviar} className="space-y-4">
            <Entrada
              etiqueta="Documento de identidad"
              inputMode="numeric"
              placeholder="Número de cédula"
              value={documento}
              onChange={(e) => setDocumento(e.target.value)}
              disabled={esNuevo}
              required
            />

            <Entrada
              etiqueta="Celular WhatsApp"
              type="tel"
              placeholder="300 123 4567"
              value={celular}
              onChange={(e) => setCelular(e.target.value)}
              disabled={esNuevo}
              required
            />

            {esNuevo && (
              <div className="space-y-3 pt-2 border-t border-linea animate-in fade-in slide-in-from-top-2 duration-300">
                <div className="rounded-lg bg-menta/15 p-3 text-xs text-tinta-suave flex items-center gap-2">
                  <ShieldCheck className="size-4 text-menta shrink-0" />
                  <span>Es tu primera vez con nosotros. Completa tus datos para crear tu ficha.</span>
                </div>

                <Entrada
                  etiqueta="Nombres"
                  value={nombres}
                  onChange={(e) => setNombres(e.target.value)}
                  placeholder="Ej. Laura"
                  required
                />

                <Entrada
                  etiqueta="Apellidos"
                  value={apellidos}
                  onChange={(e) => setApellidos(e.target.value)}
                  placeholder="Ej. Gómez"
                  required
                />

                <Casilla
                  etiqueta={
                    <span className="text-xs text-tinta-suave leading-snug">
                      Autorizo el tratamiento de mis datos personales para agendamiento, confirmación y recordatorios por WhatsApp y correo (Ley 1581 de 2012).
                    </span>
                  }
                  checked={consentimiento}
                  onChange={(e) => setConsentimiento(e.target.checked)}
                  required
                />
              </div>
            )}

            <Boton
              type="submit"
              className="w-full mt-2 font-medium"
              disabled={enviando || (esNuevo && !consentimiento)}
            >
              {enviando ? "Verificando…" : esNuevo ? "Registrarme y agendar" : "Continuar"}
              {!enviando && <ArrowRight className="size-4 ml-1" />}
            </Boton>
          </form>
        </Tarjeta>
      </div>
    </LayoutPaciente>
  );
}
