import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Check, CalendarCheck2 } from "lucide-react";
import { api, ApiError } from "@/api/cliente";
import { diaCorto, etiquetaDia, horaDe, numeroDia } from "@/lib/tiempo";
import { cn } from "@/lib/utils";
import { Boton, Seleccion, Tarjeta } from "@/ui/controles";
import { Aviso, Consulta, Vacio } from "@/ui/vistas";
import { LayoutPaciente } from "./LayoutPaciente";

const DIAS_POR_PAGINA = 5;

export function SelectorEspaciosPaciente({ modo = "agendar" }: { modo?: "agendar" | "cambiar" }) {
  const nav = useNavigate();
  const { token, id } = useParams<{ token: string; id?: string }>();
  const citaId = id ? Number(id) : undefined;

  const [servicioId, setServicioId] = useState<number | undefined>(undefined);
  const [profesionalId, setProfesionalId] = useState<number>(0);
  const [diaElegido, setDiaElegido] = useState<string | null>(null);
  const [horaElegida, setHoraElegida] = useState<string | null>(null);
  const [pagina, setPagina] = useState(0);

  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["publico", "espacios", token, servicioId, profesionalId],
    queryFn: () => api.publico.espacios(token!, servicioId, profesionalId),
    enabled: Boolean(token),
  });

  // Inicializar servicio por defecto cuando cargan los datos
  useEffect(() => {
    if (q.data && servicioId === undefined && q.data.servicios.length > 0) {
      setServicioId(q.data.sid || q.data.servicios[0].id);
    }
  }, [q.data, servicioId]);

  const dias = q.data?.dias ?? [];
  const maxPagina = Math.max(0, Math.ceil(dias.length / DIAS_POR_PAGINA) - 1);
  const diasPagina = dias.slice(pagina * DIAS_POR_PAGINA, (pagina + 1) * DIAS_POR_PAGINA);

  // Asegurar que hay un día seleccionado
  useEffect(() => {
    if (diasPagina.length > 0) {
      const existe = diasPagina.some((d) => d.fecha === diaElegido);
      if (!existe) {
        setDiaElegido(diasPagina[0].fecha);
        setHoraElegida(null);
      }
    }
  }, [diasPagina, diaElegido]);

  const diaActual = dias.find((d) => d.fecha === diaElegido);
  const horasDelDia = diaActual?.horas ?? [];

  async function confirmar() {
    if (!token || !horaElegida || !servicioId) return;
    setError(null);
    setEnviando(true);

    try {
      if (modo === "cambiar" && citaId) {
        await api.publico.cambiar(citaId, { token, inicio: horaElegida });
      } else {
        await api.publico.agendar({
          token,
          servicio_id: servicioId,
          profesional_id: profesionalId,
          inicio: horaElegida,
        });
      }
      nav(`/p/${token}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.mensaje : "Algo salió mal. Por favor elige otro horario.");
      setEnviando(false);
      void q.refetch();
    }
  }

  return (
    <LayoutPaciente titulo={modo === "cambiar" ? "Reprogramar cita" : "Elegir espacio"}>
      <div className="space-y-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">
            {modo === "cambiar" ? "Cambiar fecha de cita" : "Elige tu espacio"}
          </h1>
          <p className="text-xs text-tinta-suave mt-0.5">
            Selecciona el tratamiento, especialista y el horario que más te convenga.
          </p>
        </div>

        {error && <Aviso tipo="aviso">{error}</Aviso>}

        <Consulta q={q}>
          {(cat) => (
            <Tarjeta className="p-4 space-y-4 shadow-sm border border-linea">
              <div className="grid gap-3 sm:grid-cols-2">
                <Seleccion
                  etiqueta="Servicio / Tratamiento"
                  value={servicioId ?? cat.sid}
                  onChange={(e) => {
                    setServicioId(Number(e.target.value));
                    setHoraElegida(null);
                  }}
                >
                  {cat.servicios.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre} ({s.duracion_min} min)
                    </option>
                  ))}
                </Seleccion>

                <Seleccion
                  etiqueta="Especialista"
                  value={profesionalId}
                  onChange={(e) => {
                    setProfesionalId(Number(e.target.value));
                    setHoraElegida(null);
                  }}
                >
                  <option value={0}>Cualquier especialista disponible</option>
                  {cat.profesionales.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre}
                    </option>
                  ))}
                </Seleccion>
              </div>

              {dias.length === 0 ? (
                <Vacio titulo="Sin espacios disponibles">
                  No hay cupos disponibles próximos para este servicio o especialista. Intenta con otro profesional.
                </Vacio>
              ) : (
                <div className="space-y-3 pt-2 border-t border-linea">
                  {/* Paginador de días horizontal */}
                  <div className="flex items-center justify-between gap-1">
                    <button
                      type="button"
                      aria-label="Días anteriores"
                      disabled={pagina === 0}
                      onClick={() => setPagina((p) => Math.max(0, p - 1))}
                      className="p-1 rounded-lg hover:bg-zinc-100 disabled:opacity-30 disabled:pointer-events-none"
                    >
                      <ChevronLeft className="size-5" />
                    </button>

                    <div className="flex gap-1.5 flex-1 justify-center">
                      {diasPagina.map((d) => {
                        const activo = d.fecha === diaElegido;
                        return (
                          <button
                            key={d.fecha}
                            type="button"
                            aria-pressed={activo}
                            onClick={() => {
                              setDiaElegido(d.fecha);
                              setHoraElegida(null);
                            }}
                            className={cn(
                              "flex flex-col items-center justify-center py-2 px-2.5 rounded-xl border text-xs min-w-12 transition-all",
                              activo
                                ? "bg-marca text-white border-marca shadow-sm scale-105"
                                : "bg-papel text-tinta border-linea hover:bg-zinc-50"
                            )}
                          >
                            <span className="capitalize text-[11px] font-normal opacity-80">{diaCorto(d.fecha)}</span>
                            <span className="text-sm font-bold">{numeroDia(d.fecha)}</span>
                          </button>
                        );
                      })}
                    </div>

                    <button
                      type="button"
                      aria-label="Días siguientes"
                      disabled={pagina >= maxPagina}
                      onClick={() => setPagina((p) => Math.min(maxPagina, p + 1))}
                      className="p-1 rounded-lg hover:bg-zinc-100 disabled:opacity-30 disabled:pointer-events-none"
                    >
                      <ChevronRight className="size-5" />
                    </button>
                  </div>

                  {/* Cuadrícula de horas */}
                  <div className="space-y-2 pt-2">
                    <p className="text-xs font-semibold text-tinta-suave capitalize">
                      Horas disponibles {diaElegido ? `para el ${etiquetaDia(diaElegido)}` : ""}
                    </p>

                    {horasDelDia.length === 0 ? (
                      <p className="text-xs text-tinta-suave py-4 text-center">
                        No hay horas disponibles en este día.
                      </p>
                    ) : (
                      <div className="grid grid-cols-3 gap-2 max-h-48 overflow-y-auto p-1">
                        {horasDelDia.map((h) => {
                          const activo = horaElegida === h;
                          return (
                            <button
                              key={h}
                              type="button"
                              aria-pressed={activo}
                              onClick={() => setHoraElegida(h)}
                              className={cn(
                                "flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-lg border text-sm font-medium transition-colors",
                                activo
                                  ? "bg-marca text-white border-marca shadow-sm"
                                  : "bg-papel text-tinta border-linea hover:bg-zinc-50"
                              )}
                            >
                              {activo && <Check className="size-3.5" />}
                              <span>{horaDe(h)}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <Boton
                    className="w-full mt-3 font-medium"
                    disabled={!horaElegida || enviando}
                    onClick={confirmar}
                  >
                    <CalendarCheck2 className="size-4 mr-1.5" />
                    {enviando
                      ? "Procesando…"
                      : modo === "cambiar"
                      ? "Confirmar reprogramación"
                      : "Confirmar mi cita"}
                  </Boton>
                </div>
              )}
            </Tarjeta>
          )}
        </Consulta>

        <div className="text-center">
          <Link to={`/p/${token}`} className="text-xs text-tinta-suave underline hover:text-tinta">
            Volver a mis citas
          </Link>
        </div>
      </div>
    </LayoutPaciente>
  );
}
