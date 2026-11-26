import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { montar } from "@/pruebas/montar";
import { AUX, servidor } from "@/pruebas/servidor";
import type { Resumen } from "@/api/tipos";

const API = "*/api/v1";
const resumen = (o: Partial<Resumen> = {}): Resumen => ({
  citas: 40, atendidas: 24, no_asistio: 6, atencion_efectiva: 0.6, asistencia: 0.8, inasistencia: 0.2, cancelaciones: 4, cancelaciones_tardias: 1,
  cancelaciones_recuperadas: 2, recuperacion: 0.5, confirmacion: 0.7, sin_desenlace: 0, capacidad_aplica: true, ocupacion: 0.5,
  minutos_disponibles: 1000, minutos_atendidos: 500, cupos_liberados: 3, cupos_ocupados_oferta: 1, cupos_ocupados_agendamiento: 1, cupos_vacios: 1,
  desde_anterior: "2026-09-17", hasta_anterior: "2026-10-16",
  anterior: { ...resumenBase(), inasistencia: 0.15 }, ...o,
});
function resumenBase() {
  const { anterior: _a, desde_anterior: _d, hasta_anterior: _h, ...base } = baseFija;
  return base;
}
const baseFija = {
  citas: 30, atendidas: 20, no_asistio: 3, atencion_efectiva: 0.6, asistencia: 0.85, inasistencia: 0.13, cancelaciones: 2, cancelaciones_tardias: 0,
  cancelaciones_recuperadas: 1, recuperacion: 0.5, confirmacion: 0.6, sin_desenlace: 0, capacidad_aplica: true, ocupacion: 0.4, minutos_disponibles: 900,
  minutos_atendidos: 400, cupos_liberados: 1, cupos_ocupados_oferta: 0, cupos_ocupados_agendamiento: 0, cupos_vacios: 1,
  anterior: null, desde_anterior: null, hasta_anterior: null,
};

const usar = (r: Resumen) => servidor.use(
  http.get(`${API}/indicadores/resumen`, () => HttpResponse.json(r)),
  http.get(`${API}/indicadores/tendencia`, () => HttpResponse.json([])),
  http.get(`${API}/indicadores/por-profesional`, () => HttpResponse.json([{ id: 1, nombre: "Dra. Uno", citas: 20, atendidas: 12, no_asistio: 4, canceladas: 1, inasistencia: 0.25 }])),
  http.get(`${API}/indicadores/por-servicio`, () => HttpResponse.json([])),
  http.get(`${API}/indicadores/motivos`, () => HttpResponse.json([])),
  http.get(`${API}/indicadores/tiempo-entre-citas`, () => HttpResponse.json({ por_servicio: [], por_paciente_dias: null })),
  http.get(`${API}/indicadores/faltas-repetidas`, () => HttpResponse.json([])),
  http.get(`${API}/indicadores/dia-hora`, () => HttpResponse.json([])),
  http.get(`${API}/indicadores/recordatorios`, () => HttpResponse.json({
    con_recordatorio: { n: 10, no_asistio: 2, inasistencia: 0.2 }, sin_recordatorio: { n: 10, no_asistio: 3, inasistencia: 0.3 },
    embudo: { citas: 20, con_recordatorio: 10, confirmadas: 6, atendidas: 14 } })),
  http.get(`${API}/indicadores/citas-perdidas`, () => HttpResponse.json([{
    cita_id: 55, dia: "2026-11-10", inicio: "2026-11-10T09:00:00-05:00", estado: "no_asistio", paciente_id: 7, paciente: "Ana Pérez",
    profesional: "Dra. Uno", servicio: "Valoración", motivo: null, cancelacion_tardia: null, reagendada: false }])),
  http.get(`${API}/sistema`, () => HttpResponse.json({ tareas_fallidas: [], tareas_pendientes: 0, ultimo_cierre: "2026-11-16", configuracion: {} })),
);

describe("indicadores", () => {
  it("avisa cuando hay citas pasadas sin desenlace y enlaza a Pendientes", async () => {
    usar(resumen({ sin_desenlace: 5 }));
    montar("/indicadores", AUX);
    expect(await screen.findByText(/Hay 5 citas pasadas sin desenlace en este periodo/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cerrarlas" })).toHaveAttribute("href", "/bandejas?b=sin-desenlace");
  });

  it("no avisa cuando todo tiene desenlace, y compara con el periodo anterior", async () => {
    usar(resumen());
    montar("/indicadores", AUX);
    expect(await screen.findByText("Asistencia")).toBeInTheDocument();
    expect(screen.queryByText(/sin desenlace en este periodo/)).not.toBeInTheDocument();
    expect(screen.getByText(/\+5\.0 pp/)).toBeInTheDocument();   // inasistencia 20 % contra 15 % antes
  });

  it("una fila de la tabla abre las citas perdidas detrás de la cifra", async () => {
    usar(resumen());
    montar("/indicadores", AUX);
    await userEvent.click(await screen.findByRole("button", { name: "Ver citas perdidas de Dra. Uno" }));
    const d = await screen.findByRole("dialog");
    expect(await within(d).findByRole("link", { name: "Ana Pérez" })).toHaveAttribute("href", expect.stringContaining("cita=55"));
    expect(within(d).getByText("No ha vuelto a agendar")).toBeInTheDocument();
  });
});
