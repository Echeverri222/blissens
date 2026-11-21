import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Calendar, Plus, Clock, User } from "lucide-react";
import { api } from "@/api/cliente";
import { fechaLarga, horaDe } from "@/lib/tiempo";
import { EtiquetaEstado, Tarjeta } from "@/ui/controles";
import { Consulta, Vacio } from "@/ui/vistas";
import { LayoutPaciente } from "./LayoutPaciente";

export function MisCitas() {
  const { token } = useParams<{ token: string }>();

  const q = useQuery({
    queryKey: ["publico", "citas", token],
    queryFn: () => api.publico.misCitas(token!),
    enabled: Boolean(token),
  });

  return (
    <LayoutPaciente titulo="Mis Citas">
      <Consulta q={q}>
        {(data) => {
          const primerNombre = data.paciente.nombres.split(" ")[0];
          return (
            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-xl font-bold tracking-tight">
                    Hola, <span className="texto-holografico">{primerNombre}</span>
                  </h1>
                  <p className="text-xs text-tinta-suave mt-0.5">
                    Gestiona tus próximas citas o reserva un nuevo espacio.
                  </p>
                </div>
              </div>

              <section aria-label="Próximas citas" className="space-y-3">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-tinta-suave">
                  Tus próximas citas
                </h2>

                {data.citas.length === 0 ? (
                  <Tarjeta className="p-6 text-center">
                    <Vacio titulo="No tienes citas agendadas">
                      Selecciona un servicio y reserva tu espacio con el especialista.
                    </Vacio>
                    <Link
                      to={`/p/${token}/agendar`}
                      className="mt-4 inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] bg-marca px-4 py-2.5 text-sm font-medium text-white hover:bg-marca-suave transition-colors w-full"
                    >
                      <Plus className="size-4" /> Agendar una cita
                    </Link>
                  </Tarjeta>
                ) : (
                  <div className="space-y-3">
                    {data.citas.map((c) => (
                      <Tarjeta key={c.id} className="p-4 space-y-3 shadow-sm border border-linea">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-1.5 text-sm font-semibold">
                              <Calendar className="size-4 text-azul shrink-0" />
                              <span className="capitalize">{fechaLarga(c.dia)}</span>
                            </div>
                            {c.inicio && (
                              <p className="text-xs text-tinta-suave flex items-center gap-1.5 mt-1 ml-5">
                                <Clock className="size-3.5" />
                                <span>{horaDe(c.inicio)}</span>
                              </p>
                            )}
                          </div>
                          <EtiquetaEstado estado={c.estado} />
                        </div>

                        <div className="rounded-lg bg-fondo p-2.5 text-xs text-tinta space-y-1">
                          <p className="font-medium">{c.servicio}</p>
                          <p className="text-tinta-suave flex items-center gap-1">
                            <User className="size-3" /> {c.profesional}
                          </p>
                        </div>

                        <div className="flex items-center gap-2 pt-1">
                          <Link
                            to={`/p/${token}/cambiar/${c.id}`}
                            className="flex-1 text-center rounded-[var(--radius-control)] border border-linea bg-papel px-3 py-1.5 text-xs font-medium text-tinta hover:bg-zinc-50 transition-colors"
                          >
                            Cambiar fecha
                          </Link>
                          <Link
                            to={`/p/${token}/cancelar/${c.id}`}
                            className="rounded-[var(--radius-control)] px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50 transition-colors"
                          >
                            Cancelar
                          </Link>
                        </div>
                      </Tarjeta>
                    ))}

                    <Link
                      to={`/p/${token}/agendar`}
                      className="flex items-center justify-center gap-2 rounded-[var(--radius-control)] bg-marca px-4 py-2.5 text-sm font-medium text-white hover:bg-marca-suave transition-colors w-full"
                    >
                      <Plus className="size-4" /> Agendar otra cita
                    </Link>
                  </div>
                )}
              </section>
            </div>
          );
        }}
      </Consulta>
    </LayoutPaciente>
  );
}
