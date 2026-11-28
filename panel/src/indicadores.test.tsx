import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { montar } from "@/pruebas/montar";
import { AUX, servidor } from "@/pruebas/servidor";
import type { Resumen } from "@/api/tipos";

const API = "*/api/v1";
const resumen = (o: Partial<Resumen> = {}): Resumen => ({
  citas: 40, atendidas: 24, no_asistio: 6, atencion_efectiva: 0.6, asistencia: 0.8, inasistencia: 0.2, inasistencia_por_depurar: 0, inasistencia_con_pendientes: 0.2, cancelaciones: 4, cancelaciones_tardias: 1,
  cancelaciones_recuperadas: 2, recuperacion: 0.5, confirmacion: 0.7, sin_desenlace: 0, capacidad_aplica: true, ocupacion: 0.5,
  minutos_disponibles: 1000, minutos_atendidos: 500, cupos_liberados: 3, cupos_ocupados_oferta: 1, cupos_ocupados_agendamiento: 1, cupos_vacios: 1,
  valor_perdido: 1_200_000, valor_perdido_inasistencia: 900_000, valor_perdido_tardias: 300_000, citas_sin_valor: 0, metas: {},
  desde_anterior: "2026-09-17", hasta_anterior: "2026-10-16",
  anterior: { ...resumenBase(), inasistencia: 0.15 }, ...o,
});
function resumenBase() {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- se descartan las claves de comparación
  const { anterior: _a, desde_anterior: _d, hasta_anterior: _h, ...base } = baseFija;
  return base;
}
const baseFija = {
  citas: 30, atendidas: 20, no_asistio: 3, atencion_efectiva: 0.6, asistencia: 0.85, inasistencia: 0.13, inasistencia_por_depurar: 0, inasistencia_con_pendientes: 0.13, cancelaciones: 2, cancelaciones_tardias: 0,
  cancelaciones_recuperadas: 1, recuperacion: 0.5, confirmacion: 0.6, sin_desenlace: 0, capacidad_aplica: true, ocupacion: 0.4, minutos_disponibles: 900,
  minutos_atendidos: 400, cupos_liberados: 1, cupos_ocupados_oferta: 0, cupos_ocupados_agendamiento: 0, cupos_vacios: 1,
  anterior: null, desde_anterior: null, hasta_anterior: null,
  valor_perdido: 1_500_000, valor_perdido_inasistencia: 1_000_000, valor_perdido_tardias: 500_000, citas_sin_valor: 0, metas: {},
};

const SERVICIOS = [{ id: 1, nombre: "Valoración", duracion_min: 60, autoagendable: true, valor: 80_000 }];
const usar = (r: Resumen, servicios: object[] = SERVICIOS) => servidor.use(
  http.get(`${API}/servicios`, () => HttpResponse.json(servicios)),
  http.get(`${API}/indicadores/pendientes`, () => HttpResponse.json({
    cierre_citas: { resueltos: 8, mediana_horas: 3, p90_horas: 9, abiertos_hoy: 5, vencidos: 2 },
    mensajes: { resueltos: 4, mediana_horas: 60, p90_horas: 70, abiertos_hoy: 1, vencidos: 0 },
    seguimientos: { resueltos: 0, mediana_horas: null, p90_horas: null, abiertos_hoy: 2, vencidos: 1 },
    por_usuario: [{ usuario_id: 3, usuario: "Recepción", resueltos: 9, mediana_horas: 4 }, { usuario_id: null, usuario: null, resueltos: 3, mediana_horas: 30 }],
    registro_desde: "2026-11-25" })),
  http.get(`${API}/indicadores/planes`, () => HttpResponse.json({ entregados: 4, con_siguiente_paso: 3, conversion_pct: 75, valor_sin_siguiente_paso: 2_500_000 })),
  http.get(`${API}/indicadores/reagendamiento`, () => HttpResponse.json({
    mediana_dias: 3, total: 10, buckets: { mismo_dia: 1, "1_3": 3, "4_14": 2, "15_60": 1, no_reagendo: 3 } })),
  http.get(`${API}/indicadores/resumen`, () => HttpResponse.json(r)),
  http.get(`${API}/indicadores/tendencia`, () => HttpResponse.json([])),
  http.get(`${API}/indicadores/por-profesional`, () => HttpResponse.json([{ id: 1, nombre: "Dra. Uno", citas: 20, atendidas: 12, no_asistio: 4, canceladas: 1, inasistencia: 0.25, valor_perdido: 400_000 }])),
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
  http.get(`${API}/sistema`, () => HttpResponse.json({ tareas_fallidas: [], tareas_pendientes: 0, tareas_atrasadas: 0, ultimo_cierre: "2026-11-16", configuracion: {} })),
);

describe("indicadores", () => {
  it("bajo la inasistencia muestra la cifra si las citas sin cerrar hubieran sido inasistencias", async () => {
    usar(resumen({ inasistencia_por_depurar: 7, inasistencia_con_pendientes: 0.4375 }));
    montar("/indicadores", AUX);
    expect(await screen.findByText("Si las 7 citas sin cerrar fueron inasistencias: 43.8 %")).toBeInTheDocument();
  });

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

  it("la tarjeta de dinero perdido muestra el monto, su desglose y la comparación con el periodo anterior", async () => {
    usar(resumen({ citas_sin_valor: 3 }));
    montar("/indicadores", AUX);
    const tarjeta = (await screen.findByText("Dinero perdido")).closest("div")!;
    expect(within(tarjeta).getByText(/1\.200\.000/)).toBeInTheDocument();
    expect(within(tarjeta).getByText(/900\.000.*por inasistencias.*300\.000.*por cancelaciones tardías/)).toBeInTheDocument();
    expect(within(tarjeta).getByText(/vs\..*1\.500\.000.*antes/).parentElement).toHaveClass("text-emerald-700");   // perdió menos: mejora
    expect(within(tarjeta).getByText("3 citas sin valor configurado no se cuentan")).toBeInTheDocument();
  });

  it("sin valores de servicio explica cómo configurarlos, y solo enlaza a quien administra", async () => {
    usar(resumen(), [{ ...SERVICIOS[0], valor: null }]);
    montar("/indicadores", AUX);
    expect(await screen.findByText("Sin valores")).toBeInTheDocument();
    expect(screen.getByText(/Pide a quien administra que configure/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Administración" })).not.toBeInTheDocument();
  });

  it("un administrador ve el enlace a Administración cuando faltan los valores", async () => {
    usar(resumen(), [{ ...SERVICIOS[0], valor: null }]);
    montar("/indicadores", { ...AUX, administrador: true });
    expect(await screen.findByText("Sin valores")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Administración" }).some((l) => l.getAttribute("href") === "/administracion")).toBe(true);
  });

  it("muestra la meta de cada indicador con Cumple o No cumple", async () => {
    usar(resumen({ metas: { inasistencia: { max: 0.15 }, asistencia: { min: 0.8 }, dinero_perdido: { max: 2_000_000 } } }));
    montar("/indicadores", AUX);
    expect(await screen.findByText("Meta ≤ 15 %")).toBeInTheDocument();           // inasistencia 20 %: no cumple
    expect(screen.getByText("Meta ≤ 15 %").parentElement).toHaveTextContent("No cumple");
    expect(screen.getByText("Meta ≥ 80 %").parentElement).toHaveTextContent("Cumple");   // asistencia 80 %
    expect(screen.getByText(/Meta ≤ .*2\.000\.000/).parentElement).toHaveTextContent("Cumple");
    expect(screen.queryByText(/Meta ≥ 60 %/)).not.toBeInTheDocument();             // confirmación sin meta
  });

  it("sin valor no hay veredicto de meta", async () => {
    usar(resumen({ inasistencia: null, metas: { inasistencia: { max: 0.15 } } }));
    montar("/indicadores", AUX);
    expect(await screen.findByText("Meta ≤ 15 %")).toBeInTheDocument();
    expect(screen.queryByText("Cumple")).not.toBeInTheDocument();
    expect(screen.queryByText("No cumple")).not.toBeInTheDocument();
  });

  it("la tabla por profesional muestra lo perdido y puede ordenarse por esa columna", async () => {
    usar(resumen());
    servidor.use(http.get(`${API}/indicadores/por-profesional`, () => HttpResponse.json([
      { id: 1, nombre: "Dra. Alta", citas: 20, atendidas: 12, no_asistio: 4, canceladas: 1, inasistencia: 0.25, valor_perdido: 100_000 },
      { id: 2, nombre: "Dr. Caro", citas: 20, atendidas: 15, no_asistio: 1, canceladas: 1, inasistencia: 0.06, valor_perdido: 900_000 }])));
    montar("/indicadores", AUX);
    const tabla = await screen.findByRole("table", { name: "Por profesional" });
    expect(within(tabla).getByRole("columnheader", { name: "Perdido" })).toBeInTheDocument();
    const nombres = () => within(tabla).getAllByRole("rowheader").map((r) => r.textContent);
    expect(nombres()).toEqual(["Dra. Alta", "Dr. Caro"]);                           // por % de inasistencia
    await userEvent.selectOptions(screen.getByLabelText("Ordenar por profesional por"), "perdido");
    expect(nombres()).toEqual(["Dr. Caro", "Dra. Alta"]);
  });

  it("muestra qué tan rápido cierra el equipo sus pendientes y quién", async () => {
    usar(resumen());
    montar("/indicadores", AUX);
    const tabla = await screen.findByRole("table", { name: "Pendientes resueltos por el equipo" });
    expect(within(within(tabla).getByRole("row", { name: /Desenlace de citas/ })).getByText("3 h")).toBeInTheDocument();
    expect(within(tabla).getByRole("row", { name: /Mensajes atendidos/ })).toHaveTextContent("3 días");   // 60 h
    expect(within(tabla).getByRole("row", { name: /Seguimientos cerrados/ })).toHaveTextContent("—");
    const personas = screen.getByRole("list", { name: "Pendientes resueltos por persona" });
    expect(within(personas).getByText("Recepción")).toBeInTheDocument();
    expect(within(personas).getByText("Sin registrar")).toBeInTheDocument();
    expect(screen.getByText(/Antes del .*25 de noviembre de 2026 no se registraba quién resolvía/)).toBeInTheDocument();
  });

  it("dentro de Más indicadores cuenta cuánto tardan en volver a agendar", async () => {
    usar(resumen());
    montar("/indicadores", AUX);
    await userEvent.click(await screen.findByText("Más indicadores"));
    expect(await screen.findByText(/La mitad reagenda/)).toHaveTextContent("La mitad reagenda en 3 días");
    const lista = screen.getByRole("list", { name: "Cancelaciones por tiempo hasta volver a agendar" });
    expect(within(lista).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["1Mismo día", "31–3 días", "24–14 días", "115–60 días", "3No reagendó"]);
  });

  it("dentro de Más indicadores muestra los planes entregados y los que quedaron sin siguiente paso", async () => {
    usar(resumen());
    montar("/indicadores", AUX);
    await userEvent.click(await screen.findByText("Más indicadores"));
    expect(await screen.findByText(/4/, { selector: "b" })).toBeInTheDocument();
    expect(await screen.findByText(/75.0 % con cita o abono/)).toBeInTheDocument();
    expect(screen.getByText(/Valor de los planes sin siguiente paso/)).toHaveTextContent("2.500.000");
  });
});
