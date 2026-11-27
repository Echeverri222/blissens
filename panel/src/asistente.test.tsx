import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { montar } from "@/pruebas/montar";
import { AUX, ESP, enviadas, error, registrar, servidor } from "@/pruebas/servidor";
import type { Propuesta } from "@/api/tipos";

const API = "*/api/v1";
const estado = (o: object = {}) => http.get(`${API}/asistente/estado`, () => HttpResponse.json({ disponible: true, perfil: "auxiliar", mensajes_restantes: 100, ...o }));
const responder = (respuesta: string, propuestas: Propuesta[] = [], id: number | null = 5) =>
  http.post(`${API}/asistente/mensajes`, async ({ request }) => { await registrar(request); return HttpResponse.json({ conversacion_id: id, respuesta, propuestas }); });
const ok = (extra: object = {}) => async ({ request }: { request: Request }) => { await registrar(request); return HttpResponse.json({ ok: true, ...extra }); };

async function abrirYPreguntar(pregunta = "Hola") {
  await userEvent.click(await screen.findByRole("button", { name: "Asistente" }));
  const caja = await screen.findByRole("textbox", { name: "Escribe tu mensaje" });
  await userEvent.type(caja, pregunta);
  await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
}

const pr = (tipo: Propuesta["tipo"], parametros: Propuesta["parametros"], resumen = "Resumen de prueba"): Propuesta => ({ tipo, parametros, resumen });
const llamadas = () => enviadas.filter((e) => e.metodo === "POST" && !e.ruta.includes("/asistente/"));

describe("disponibilidad", () => {
  it("sin la ruta (404) no hay botón", async () => {
    montar("/agenda", AUX);
    await screen.findByRole("heading", { name: /Agenda/ });
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole("button", { name: "Asistente" })).not.toBeInTheDocument();
  });
  it("con disponible:false no hay botón", async () => {
    servidor.use(estado({ disponible: false }));
    montar("/agenda", AUX);
    await screen.findByRole("heading", { name: /Agenda/ });
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole("button", { name: "Asistente" })).not.toBeInTheDocument();
  });
  it("disponible: el especialista también lo ve, y el foco va al cuadro de texto", async () => {
    servidor.use(estado({ perfil: "especialista" }));
    montar("/agenda", ESP);
    await userEvent.click(await screen.findByRole("button", { name: "Asistente" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Escribe tu mensaje" })).toHaveFocus());
    expect(screen.getByText(/Puede equivocarse/)).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Escribe tu mensaje" })).not.toBeInTheDocument());
  });
});

describe("conversación", () => {
  it("envía el mensaje y muestra la respuesta; la conversación sobrevive a cerrar y reabrir", async () => {
    servidor.use(estado(), responder("Mañana tienes 3 citas."));
    montar("/agenda", AUX);
    await abrirYPreguntar("¿Qué tengo mañana?");
    expect(await screen.findByText("Mañana tienes 3 citas.")).toBeInTheDocument();
    expect(enviadas.find((e) => e.ruta.endsWith("/asistente/mensajes"))?.cuerpo).toEqual({ texto: "¿Qué tengo mañana?", conversacion_id: null });
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Asistente" }));
    expect(await screen.findByText("Mañana tienes 3 citas.")).toBeInTheDocument();
    // El siguiente mensaje continúa la misma conversación.
    await userEvent.type(screen.getByRole("textbox", { name: "Escribe tu mensaje" }), "Gracias");
    await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(enviadas.filter((e) => e.ruta.endsWith("/asistente/mensajes"))).toHaveLength(2));
    expect(enviadas.filter((e) => e.ruta.endsWith("/asistente/mensajes"))[1].cuerpo).toEqual({ texto: "Gracias", conversacion_id: 5 });
    // "Nueva conversación" la reinicia.
    await userEvent.click(await screen.findByRole("button", { name: /Nueva conversación/ }));
    expect(screen.queryByText("Mañana tienes 3 citas.")).not.toBeInTheDocument();
  });

  it("mientras espera muestra «Pensando…» y no deja enviar otro mensaje", async () => {
    let soltar: () => void = () => {};
    servidor.use(estado(), http.post(`${API}/asistente/mensajes`, async () => {
      await new Promise<void>((r) => { soltar = r; });
      return HttpResponse.json({ conversacion_id: 1, respuesta: "Listo", propuestas: [] });
    }));
    montar("/agenda", AUX);
    await abrirYPreguntar("Hola");
    expect(await screen.findByText("Pensando…")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: "Escribe tu mensaje" }), "otro");
    expect(screen.getByRole("button", { name: "Enviar" })).toBeDisabled();
    soltar();
    expect(await screen.findByText("Listo")).toBeInTheDocument();
    expect(screen.queryByText("Pensando…")).not.toBeInTheDocument();
  });

  it("la respuesta es texto plano: sin HTML, sin enlaces", async () => {
    const texto = "Mira <b>esto</b>\nhttps://ejemplo.invalid/x y <img src=x onerror=alert(1)> **no negrita**";
    servidor.use(estado(), responder(texto));
    montar("/agenda", AUX);
    await abrirYPreguntar();
    const log = await screen.findByRole("log");
    const burbuja = await within(log).findByText((_, el) => el?.textContent === texto && el.children.length === 0);
    expect(burbuja).toBeInTheDocument();
    expect(log.querySelector("b, img, a, strong")).toBeNull();
    expect(within(log).queryByRole("link")).not.toBeInTheDocument();
  });

  it("avisa cuando quedan pocos mensajes", async () => {
    servidor.use(estado({ mensajes_restantes: 3 }));
    montar("/agenda", AUX);
    await userEvent.click(await screen.findByRole("button", { name: "Asistente" }));
    expect(screen.getByText("Te quedan 3 mensajes hoy.")).toBeInTheDocument();
  });
});

describe("propuestas", () => {
  const casos: [string, Propuesta, string, string, unknown][] = [
    ["agendar", pr("agendar", { paciente_id: 7, profesional_id: 1, servicio_id: 1, inicio: "2026-11-17T09:00:00-05:00" }), "POST", "/citas",
      { paciente_id: 7, profesional_id: 1, servicio_id: 1, inicio: "2026-11-17T09:00:00-05:00" }],
    ["cambiar_fecha", pr("cambiar_fecha", { cita_id: 10, inicio: "2026-11-18T10:00:00-05:00" }), "POST", "/citas/10/cambiar-fecha", { inicio: "2026-11-18T10:00:00-05:00" }],
    ["cancelar", pr("cancelar", { cita_id: 10, motivo_id: 3, texto: "Viaje" }), "POST", "/citas/10/cancelar", { motivo_id: 3, texto: "Viaje" }],
    ["confirmar_telefono", pr("confirmar_telefono", { cita_id: 10 }), "POST", "/citas/10/confirmar", {}],
    ["desenlace", pr("desenlace", { cita_id: 10, desenlace: "no_asistio" }), "POST", "/citas/10/desenlace", { desenlace: "no_asistio" }],
    ["bloqueo", pr("bloqueo", { profesional_id: 1, inicio: "2026-11-20T14:00:00-05:00", fin: "2026-11-20T18:00:00-05:00", motivo: "Reunión" }), "POST", "/bloqueos",
      { profesional_id: 1, inicio: "2026-11-20T14:00:00-05:00", fin: "2026-11-20T18:00:00-05:00", motivo: "Reunión" }],
  ];

  it.each(casos)("«%s» llama al endpoint existente solo después de confirmar", async (_n, propuesta, metodo, ruta, cuerpo) => {
    servidor.use(estado(), responder("Preparé esto.", [propuesta]),
      http.post(`${API}/citas`, ok({ cita_id: 99 })), http.post(`${API}/citas/:id/cambiar-fecha`, ok({ cita_id: 99 })),
      http.post(`${API}/citas/:id/cancelar`, ok()), http.post(`${API}/citas/:id/confirmar`, ok()),
      http.post(`${API}/citas/:id/desenlace`, ok()), http.post(`${API}/bloqueos`, ok()));
    montar("/agenda", AUX);
    await abrirYPreguntar();
    const tarjeta = await screen.findByTestId("propuesta");
    expect(tarjeta).toHaveTextContent("Resumen de prueba");
    await userEvent.click(within(tarjeta).getByRole("button", { name: "Confirmar" }));
    // El cuadro de confirmación aparece y todavía no se envió nada.
    expect(await screen.findByRole("button", { name: "Sí, confirmar" })).toBeInTheDocument();
    expect(llamadas()).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Sí, confirmar" }));
    await waitFor(() => expect(llamadas()).toHaveLength(1));
    expect(llamadas()[0]).toMatchObject({ metodo, ruta: `/api/v1${ruta}`, cuerpo });
    expect(await within(tarjeta).findByText("Hecho")).toBeInTheDocument();
  });

  it("una propuesta confirmada no se puede confirmar otra vez", async () => {
    servidor.use(estado(), responder("Listo.", [pr("confirmar_telefono", { cita_id: 10 })]), http.post(`${API}/citas/:id/confirmar`, ok()));
    montar("/agenda", AUX);
    await abrirYPreguntar();
    const tarjeta = await screen.findByTestId("propuesta");
    await userEvent.click(within(tarjeta).getByRole("button", { name: "Confirmar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmar" }));
    await within(tarjeta).findByText("Hecho");
    expect(within(tarjeta).queryByRole("button", { name: "Confirmar" })).not.toBeInTheDocument();
    expect(within(tarjeta).queryByRole("button", { name: "Descartar" })).not.toBeInTheDocument();
    expect(llamadas()).toHaveLength(1);
  });

  it("«Descartar» no llama a nada", async () => {
    servidor.use(estado(), responder("Listo.", [pr("cancelar", { cita_id: 10, motivo_id: 3, texto: "" })]));
    montar("/agenda", AUX);
    await abrirYPreguntar();
    const tarjeta = await screen.findByTestId("propuesta");
    await userEvent.click(within(tarjeta).getByRole("button", { name: "Descartar" }));
    expect(await within(tarjeta).findByText("Descartada")).toBeInTheDocument();
    expect(within(tarjeta).queryByRole("button", { name: "Confirmar" })).not.toBeInTheDocument();
    expect(llamadas()).toHaveLength(0);
  });

  it("si el endpoint rechaza la acción muestra el mensaje y la tarjeta sigue pendiente", async () => {
    servidor.use(estado(), responder("Listo.", [pr("agendar", { paciente_id: 7, profesional_id: 1, servicio_id: 1, inicio: "2026-11-17T09:00:00-05:00" })]),
      http.post(`${API}/citas`, () => error(422, "datos_invalidos", "Esa hora ya pasó.")));
    montar("/agenda", AUX);
    await abrirYPreguntar();
    const tarjeta = await screen.findByTestId("propuesta");
    await userEvent.click(within(tarjeta).getByRole("button", { name: "Confirmar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmar" }));
    expect(await within(tarjeta).findByText("Esa hora ya pasó.")).toBeInTheDocument();
    expect(within(tarjeta).getByRole("button", { name: "Confirmar" })).toBeEnabled();
  });
});
