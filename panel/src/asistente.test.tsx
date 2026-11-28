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
  await userEvent.click(await screen.findByRole("button", { name: "Bliss" }));
  const caja = await screen.findByRole("textbox", { name: "Escribe tu mensaje" });
  await userEvent.type(caja, pregunta);
  await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
}

const pr = (tipo: Propuesta["tipo"], parametros: Propuesta["parametros"], resumen = "Resumen de prueba"): Propuesta => ({ tipo, parametros, resumen });
const llamadas = () => enviadas.filter((e) => e.metodo !== "GET" && !e.ruta.includes("/asistente/"));

describe("disponibilidad", () => {
  it("sin la ruta (404) no hay botón", async () => {
    montar("/agenda", AUX);
    await screen.findByRole("heading", { name: /Agenda/ });
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole("button", { name: "Bliss" })).not.toBeInTheDocument();
  });
  it("con disponible:false no hay botón", async () => {
    servidor.use(estado({ disponible: false }));
    montar("/agenda", AUX);
    await screen.findByRole("heading", { name: /Agenda/ });
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole("button", { name: "Bliss" })).not.toBeInTheDocument();
  });
  it("disponible: el especialista también lo ve, y el foco va al cuadro de texto", async () => {
    servidor.use(estado({ perfil: "especialista" }));
    montar("/agenda", ESP);
    await userEvent.click(await screen.findByRole("button", { name: "Bliss" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Bliss" }));
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

  it("en escritorio queda fijo a la derecha: no tapa el panel y sigue abierto al cambiar de página", async () => {
    servidor.use(estado(), responder("Llama a Ana Pérez.", [], 5));
    montar("/agenda", AUX);
    await abrirYPreguntar("¿A quién llamo?");
    expect(await screen.findByText("Llama a Ana Pérez.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(within(screen.getAllByRole("navigation", { name: "Secciones" })[0]).getByRole("link", { name: /Pacientes/ }));
    expect(await screen.findByRole("heading", { name: /Pacientes/ })).toBeInTheDocument();
    expect(within(screen.getByRole("complementary", { name: "Bliss" })).getByText("Llama a Ana Pérez.")).toBeInTheDocument();
  });

  it("avisa cuando quedan pocos mensajes", async () => {
    servidor.use(estado({ mensajes_restantes: 3 }));
    montar("/agenda", AUX);
    await userEvent.click(await screen.findByRole("button", { name: "Bliss" }));
    expect(screen.getByText("Te quedan 3 mensajes hoy.")).toBeInTheDocument();
  });
});

describe("propuestas", () => {
  const casos: [string, Propuesta, string, string, unknown][] = [
    ["agendar", pr("agendar", { paciente_id: 7, profesional_id: 1, servicio_id: 1, inicio: "2026-11-17T09:00:00-05:00" }), "POST", "/citas",
      { paciente_id: 7, profesional_id: 1, servicio_id: 1, inicio: "2026-11-17T09:00:00-05:00" }],
    ["agendar con duración", pr("agendar", { paciente_id: 7, profesional_id: 1, servicio_id: 1, inicio: "2026-11-17T09:00:00-05:00", duracion_min: 60 }), "POST", "/citas",
      { paciente_id: 7, profesional_id: 1, servicio_id: 1, inicio: "2026-11-17T09:00:00-05:00", duracion_min: 60 }],
    ["cambiar_fecha", pr("cambiar_fecha", { cita_id: 10, inicio: "2026-11-18T10:00:00-05:00" }), "POST", "/citas/10/cambiar-fecha", { inicio: "2026-11-18T10:00:00-05:00" }],
    ["cancelar", pr("cancelar", { cita_id: 10, motivo_id: 3, texto: "Viaje" }), "POST", "/citas/10/cancelar", { motivo_id: 3, texto: "Viaje" }],
    ["confirmar_telefono", pr("confirmar_telefono", { cita_id: 10 }), "POST", "/citas/10/confirmar", {}],
    ["desenlace", pr("desenlace", { cita_id: 10, desenlace: "no_asistio" }), "POST", "/citas/10/desenlace", { desenlace: "no_asistio" }],
    ["bloqueo", pr("bloqueo", { profesional_id: 1, inicio: "2026-11-20T14:00:00-05:00", fin: "2026-11-20T18:00:00-05:00", motivo: "Reunión" }), "POST", "/bloqueos",
      { profesional_id: 1, inicio: "2026-11-20T14:00:00-05:00", fin: "2026-11-20T18:00:00-05:00", motivo: "Reunión" }],
    ["eliminar_bloqueo", pr("eliminar_bloqueo", { bloqueo_id: 4 }), "DELETE", "/bloqueos/4", undefined],
    ["segmentos", pr("segmentos", { paciente_id: 7, internacional: true, deportista: false }), "PUT", "/pacientes/7/segmentos", { internacional: true, deportista: false }],
    ["gestion_seguimiento", pr("gestion_seguimiento", { caso_id: 8, resultado: "sin_respuesta", detalle: "Buzón" }), "POST", "/seguimientos/8/gestion",
      { resultado: "sin_respuesta", detalle: "Buzón" }],
    ["gestionar_mensaje", pr("gestionar_mensaje", { mensaje_id: 9 }), "POST", "/mensajes/9/gestionar", undefined],
    ["gestionar_contacto", pr("gestionar_contacto", { solicitud_id: 6 }), "POST", "/contactos/6/gestionar", undefined],
    ["vincular_contacto", pr("vincular_contacto", { solicitud_id: 6, paciente_id: 7 }), "POST", "/contactos/6/paciente", { paciente_id: 7 }],
    ["revertir", pr("revertir", { historial_id: 12 }), "POST", "/historial/12/revertir", undefined],
    ["no_contactar", pr("no_contactar", { paciente_id: 7, motivo: "cobro", nota: "En cartera" }), "PUT", "/pacientes/7/no-contactar", { motivo: "cobro", nota: "En cartera" }],
    ["quitar_no_contactar", pr("quitar_no_contactar", { paciente_id: 7 }), "DELETE", "/pacientes/7/no-contactar", undefined],
  ];

  it.each(casos)("«%s» llama al endpoint existente solo después de confirmar", async (_n, propuesta, metodo, ruta, cuerpo) => {
    servidor.use(estado(), responder("Preparé esto.", [propuesta]),
      http.post(`${API}/citas`, ok({ cita_id: 99 })), http.post(`${API}/citas/:id/cambiar-fecha`, ok({ cita_id: 99 })),
      http.post(`${API}/citas/:id/cancelar`, ok()), http.post(`${API}/citas/:id/confirmar`, ok()),
      http.post(`${API}/citas/:id/desenlace`, ok()), http.post(`${API}/bloqueos`, ok()),
      http.delete(`${API}/bloqueos/:id`, ok()), http.put(`${API}/pacientes/:id/segmentos`, ok({ internacional: true, deportista: false })),
      http.put(`${API}/pacientes/:id/no-contactar`, ok({ no_contactar: "cobro", no_contactar_en: null, no_contactar_nota: null })),
      http.delete(`${API}/pacientes/:id/no-contactar`, ok({ no_contactar: null, no_contactar_en: null, no_contactar_nota: null })),
      http.post(`${API}/seguimientos/:id/gestion`, ok()), http.post(`${API}/mensajes/:id/gestionar`, ok()),
      http.post(`${API}/contactos/:id/gestionar`, ok()), http.post(`${API}/contactos/:id/paciente`, ok()),
      http.post(`${API}/historial/:id/revertir`, ok({ historial_id: 13 })));
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
    expect(llamadas()[0]).toMatchObject({ metodo, ruta: `/api/v1${ruta}`, ...(cuerpo === undefined ? {} : { cuerpo }) });
    expect(await within(tarjeta).findByText("Hecho")).toBeInTheDocument();
  });

  it("«crear_paciente» pide documento, celular y autorización en la tarjeta y los manda solo a la API", async () => {
    servidor.use(estado(), responder("Llena sus datos en la tarjeta.", [pr("crear_paciente", { nombres: "Marta", apellidos: "Ruiz" }, "Crear el paciente Marta Ruiz.")]),
      http.post(`${API}/pacientes`, ok({ paciente_id: 77 })));
    montar("/agenda", AUX);
    await abrirYPreguntar("Crea a Marta Ruiz");
    const tarjeta = await screen.findByTestId("propuesta");
    expect(within(tarjeta).getByLabelText("Nombres")).toHaveValue("Marta");
    expect(within(tarjeta).getByLabelText("Apellidos")).toHaveValue("Ruiz");
    await userEvent.type(within(tarjeta).getByLabelText("Documento"), "10203040");
    await userEvent.type(within(tarjeta).getByLabelText("Celular"), "3001234567");
    await userEvent.click(within(tarjeta).getByRole("checkbox"));
    await userEvent.click(within(tarjeta).getByRole("button", { name: "Crear paciente" }));
    await waitFor(() => expect(llamadas()).toHaveLength(1));
    expect(llamadas()[0]).toMatchObject({ metodo: "POST", ruta: "/api/v1/pacientes",
      cuerpo: { nombres: "Marta", apellidos: "Ruiz", documento: "10203040", celular: "3001234567", consentimiento: true } });
    expect(await within(await screen.findByTestId("propuesta")).findByText("Hecho")).toBeInTheDocument();
    // Lo que se escribió en la tarjeta no vuelve al asistente.
    expect(enviadas.filter((e) => e.ruta.includes("/asistente/mensajes")).map((e) => JSON.stringify(e.cuerpo)).join()).not.toContain("10203040");
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
