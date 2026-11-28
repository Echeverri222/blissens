import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { montar } from "@/pruebas/montar";
import { AUX, ESP, agenda, cita, detalle, enviadas, error, registrar, servidor } from "@/pruebas/servidor";

const API = "*/api/v1";
const ok = (extra: object = {}) => async ({ request }: { request: Request }) => { await registrar(request); return HttpResponse.json({ ok: true, ...extra }); };

describe("inicio de sesión", () => {
  it("sin sesión lleva a iniciar sesión, sin mostrar datos, y vuelve al origen al entrar", async () => {
    montar("/pacientes", null);
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
    expect(screen.queryByText("Pacientes")).not.toBeInTheDocument();
    servidor.use(http.post(`${API}/sesion`, () => { servidor.use(http.get(`${API}/sesion`, () => HttpResponse.json(AUX))); return HttpResponse.json(AUX); }));
    await userEvent.type(screen.getByLabelText("Usuario"), "recepcion");
    await userEvent.type(screen.getByLabelText("Contraseña"), "clave-de-prueba");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await screen.findByRole("heading", { name: "Pacientes" });
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.getByRole("heading", { name: "Pacientes" })).toBeInTheDocument();
  });

  it.each([
    [401, "credenciales_invalidas", "Usuario o contraseña incorrectos."],
    [429, "inicio_bloqueado", "Demasiados intentos fallidos. Intenta de nuevo en unos minutos."],
  ])("muestra el mensaje de la API (%s)", async (status, codigo, mensaje) => {
    montar("/agenda", null);
    servidor.use(http.post(`${API}/sesion`, () => error(status, codigo, mensaje)));
    await userEvent.type(await screen.findByLabelText("Usuario"), "x");
    await userEvent.type(screen.getByLabelText("Contraseña"), "mala");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(mensaje);
    expect(screen.getByLabelText("Contraseña")).toHaveValue("");
  });

  it("un 401 a mitad de uso lleva a iniciar sesión", async () => {
    montar("/agenda", AUX);
    expect(await screen.findByRole("heading", { name: /Agenda/ })).toBeInTheDocument();
    servidor.use(http.get(`${API}/agenda`, () => error(401, "no_autenticado", "Inicia sesión para continuar.")),
      http.get(`${API}/sesion`, () => error(401, "no_autenticado", "Inicia sesión para continuar.")));
    await userEvent.click(screen.getByRole("button", { name: "Día siguiente" }));
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
  });
});

describe("navegación por rol", () => {
  it("el especialista no ve secciones de recepción y, si escribe la dirección, vuelve a su agenda", async () => {
    montar("/bandejas", ESP);
    expect(await screen.findByRole("heading", { name: /Mi agenda/ })).toBeInTheDocument();
    const menu = screen.getAllByRole("navigation", { name: "Secciones" })[0];
    expect(within(menu).getByText("Mi agenda")).toBeInTheDocument();
    expect(within(menu).getByText("Mi horario")).toBeInTheDocument();
    for (const t of ["Pendientes", "Pacientes", "Indicadores", "Sistema"]) expect(within(menu).queryByText(t)).not.toBeInTheDocument();
  });
  it("la auxiliar ve todas sus secciones, el contador de bandejas y el enlace al simulador en modo demo", async () => {
    montar("/agenda", AUX);
    const menu = (await screen.findAllByRole("navigation", { name: "Secciones" }))[0];
    for (const t of ["Agenda", "Pendientes", "Pacientes", "Indicadores", "Sistema"]) expect(within(menu).getByText(t)).toBeInTheDocument();
    expect(await within(menu).findByLabelText("3 pendientes")).toBeInTheDocument();
    expect(screen.getByText("Modo demo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Simulador/ })).toHaveAttribute("target", "_blank");
    expect(screen.getByLabelText("Hora del sistema")).toHaveTextContent(/16 de nov.*10:30/);
  });
  it("el menú se contrae a solo íconos (con su nombre para lectores y al pasar el ratón) y lo recuerda", async () => {
    localStorage.removeItem("panel.menu_contraido");
    const { unmount } = montar("/agenda", AUX);
    await userEvent.click(await screen.findByRole("button", { name: "Contraer menú" }));
    const menu = screen.getAllByRole("navigation", { name: "Secciones" })[0];
    expect(within(menu).getByRole("link", { name: /Pacientes/ })).toHaveAttribute("title", "Pacientes");
    expect(within(menu).getByText("Pacientes")).toHaveClass("sr-only");
    unmount();
    montar("/agenda", AUX);
    expect(await screen.findByRole("button", { name: "Expandir menú" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Expandir menú" }));
    expect(within(screen.getAllByRole("navigation", { name: "Secciones" })[0]).getByText("Pacientes")).not.toHaveClass("sr-only");
  });
  it("la auxiliar no puede abrir Mi horario", async () => {
    montar("/horario", AUX);
    expect(await screen.findByRole("heading", { name: /Agenda/ })).toBeInTheDocument();
  });
});

describe("hoja de cita", () => {
  const abrir = async (sesion = ESP) => { montar("/agenda?cita=10", sesion); return await screen.findByRole("dialog"); };

  it("muestra paciente, celular, servicio, estado e historial; sin enlace a la ficha para el especialista", async () => {
    const d = await abrir(ESP);
    expect(await within(d).findByRole("heading", { name: "Ana Pérez" })).toBeInTheDocument();
    expect(within(d).getByRole("link", { name: /\+573001112233/ })).toHaveAttribute("href", "tel:+573001112233");
    expect(within(d).getByText("Valoración")).toBeInTheDocument();
    expect(within(d).getByText(/Creada como programada/)).toBeInTheDocument();
    expect(within(d).queryByText("Ver ficha del paciente")).not.toBeInTheDocument();
  });

  it("muestra los botones según las acciones permitidas, no según el estado", async () => {
    servidor.use(http.get(`${API}/citas/:id`, () => HttpResponse.json(detalle({ estado: "programada", acciones: [] }))));
    const d = await abrir();
    await within(d).findByRole("heading", { name: "Ana Pérez" });
    for (const t of ["Atendida", "No asistió", "Cancelar cita", "Cambiar fecha"]) expect(within(d).queryByRole("button", { name: t })).not.toBeInTheDocument();
  });

  it("registra atendida y confirma antes de no asistió", async () => {
    servidor.use(http.post(`${API}/citas/10/desenlace`, ok()));
    const d = await abrir();
    await userEvent.click(await within(d).findByRole("button", { name: "Atendida" }));
    expect(enviadas).toHaveLength(0); // un clic por error no registra nada
    await userEvent.click(await screen.findByRole("button", { name: "Sí, fue atendida" }));
    await waitFor(() => expect(enviadas).toContainEqual({ metodo: "POST", ruta: "/api/v1/citas/10/desenlace", cuerpo: { desenlace: "atendida" } }));
    enviadas.length = 0;
    await userEvent.click(within(d).getByRole("button", { name: "No asistió" }));
    expect(enviadas).toHaveLength(0); // pide confirmación primero
    await userEvent.click(await screen.findByRole("button", { name: "Sí, continuar" }));
    await waitFor(() => expect(enviadas[0]?.cuerpo).toEqual({ desenlace: "no_asistio" }));
  });

  it("un desenlace anticipado muestra el mensaje de la API y recarga el dato", async () => {
    servidor.use(http.post(`${API}/citas/10/desenlace`, () => error(409, "desenlace_anticipado", "Solo se puede registrar el desenlace desde la hora de inicio de la cita.")));
    const d = await abrir();
    await userEvent.click(await within(d).findByRole("button", { name: "Atendida" }));
    await userEvent.click(await screen.findByRole("button", { name: "Sí, fue atendida" }));
    expect((await screen.findAllByText(/desde la hora de inicio/)).length).toBeGreaterThan(0);
  });

  it("revierte un movimiento reversible, con confirmación", async () => {
    servidor.use(
      http.get(`${API}/citas/:id`, () => HttpResponse.json(detalle({ estado: "no_asistio", acciones: [], historial: [
        ...detalle().historial,
        { id: 2, estado_anterior: "programada", estado_nuevo: "no_asistio", actor: "especialista", usuario: "Dra. Uno", detalle: "Desenlace registrado", momento: "2026-11-16T10:00:00-05:00", revierte_id: null, revertido: false, reversible: true }] }))),
      http.post(`${API}/historial/2/revertir`, ok({ historial_id: 3 })));
    const d = await abrir();
    expect(await within(d).findAllByText(/Dra\. Uno \(/)).not.toHaveLength(0);
    await userEvent.click(await within(d).findByRole("button", { name: "Revertir" }));
    await userEvent.click(await screen.findByRole("button", { name: "Sí, continuar" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/historial/2/revertir" }));
  });

  it("«Confirmó» registra la confirmación por teléfono y la hoja pasa a Confirmada", async () => {
    let confirmada = false;
    servidor.use(
      http.get(`${API}/citas/:id`, () => HttpResponse.json(confirmada ? detalle({ estado: "confirmada", acciones: ["cancelar", "cambiar_fecha"] }) : detalle({ acciones: ["confirmar", "cancelar", "cambiar_fecha"] }))),
      http.post(`${API}/citas/10/confirmar`, async ({ request }) => { await registrar(request); confirmada = true; return HttpResponse.json({ ok: true }); }));
    const d = await abrir(AUX);
    await userEvent.click(await within(d).findByRole("button", { name: "Confirmó" }));
    expect(enviadas).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmó" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ metodo: "POST", ruta: "/api/v1/citas/10/confirmar" }));
    expect(await within(d).findByText("Confirmada")).toBeInTheDocument();
    expect(within(d).queryByRole("button", { name: "Confirmó" })).not.toBeInTheDocument();
  });

  it("la auxiliar cancela eligiendo un motivo", async () => {
    servidor.use(http.get(`${API}/citas/:id`, () => HttpResponse.json(detalle({ acciones: ["cancelar", "cambiar_fecha"] }))), http.post(`${API}/citas/10/cancelar`, ok()));
    const d = await abrir(AUX);
    expect(await within(d).findByText("Ver ficha del paciente")).toBeInTheDocument();
    await userEvent.click(within(d).getByRole("button", { name: "Cancelar cita" }));
    const confirmar = within(d).getByRole("button", { name: "Cancelar la cita" });
    expect(confirmar).toBeDisabled();
    await userEvent.selectOptions(within(d).getByLabelText("Motivo de la cancelación"), "Calamidad");
    await userEvent.click(confirmar);
    await userEvent.click(await screen.findByRole("button", { name: "Sí, continuar" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/citas/10/cancelar", cuerpo: { motivo_id: 3, texto: null } }));
  });

  it("la auxiliar cambia la fecha eligiendo entre los espacios de la API", async () => {
    servidor.use(
      http.get(`${API}/citas/:id`, () => HttpResponse.json(detalle({ acciones: ["cancelar", "cambiar_fecha"] }))),
      http.get(`${API}/espacios`, () => HttpResponse.json({ profesional_id: 1, servicio_id: 1, dias: [{ fecha: "2026-11-17", horas: ["2026-11-17T09:00:00-05:00"] }] })),
      http.post(`${API}/citas/10/cambiar-fecha`, async ({ request }) => { await registrar(request); return HttpResponse.json({ cita_id: 11 }); }));
    const d = await abrir(AUX);
    await userEvent.click(await within(d).findByRole("button", { name: "Cambiar fecha" }));
    await userEvent.click(await within(d).findByRole("button", { name: /09:00/ }));
    await userEvent.click(within(d).getByRole("button", { name: "Cambiar a este espacio" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/citas/10/cambiar-fecha", cuerpo: { inicio: "2026-11-17T09:00:00-05:00" } }));
  });
});

describe("bloqueos", () => {
  const conflicto = (citas: object[]) => http.post(`${API}/bloqueos`, () => error(409, "bloqueo_con_citas", "Ese rango tiene citas vivas. Muévelas o cancélalas y vuelve a intentarlo.", { citas }));
  const enConflicto = { id: 10, estado: "programada", inicio: "2026-11-16T11:00:00-05:00", fin: "2026-11-16T12:00:00-05:00", servicio: "Valoración", paciente_id: 7, paciente: "Ana Pérez" };

  it("el especialista crea un bloqueo en un rango libre", async () => {
    servidor.use(http.get(`${API}/profesionales/1/horario`, () => HttpResponse.json({ profesional_id: 1, franjas: [{ dia_semana: 0, desde: "08:00:00", hasta: "12:00:00" }] })),
      http.get(`${API}/bloqueos`, () => HttpResponse.json([])),
      http.post(`${API}/bloqueos`, async ({ request }) => { await registrar(request); return HttpResponse.json({ id: 1, profesional_id: 1, inicio: "2026-11-16T13:00:00-05:00", fin: "2026-11-16T14:00:00-05:00", motivo: "Curso", creado_por: null }, { status: 201 }); }));
    montar("/horario", ESP);
    expect(await screen.findByText("08:00 – 12:00")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Motivo"), "Curso");
    await userEvent.click(screen.getByRole("button", { name: "Crear bloqueo" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/bloqueos", cuerpo: { profesional_id: null, inicio: "2026-11-16T09:00:00-05:00", fin: "2026-11-16T10:00:00-05:00", motivo: "Curso" } }));
  });

  it("el especialista ve las citas en conflicto y la indicación de pedir a recepción que las mueva", async () => {
    servidor.use(http.get(`${API}/profesionales/1/horario`, () => HttpResponse.json({ profesional_id: 1, franjas: [] })), http.get(`${API}/bloqueos`, () => HttpResponse.json([])), conflicto([enConflicto]));
    montar("/horario", ESP);
    await userEvent.click(await screen.findByRole("button", { name: "Crear bloqueo" }));
    expect(await screen.findByText(/tiene citas vivas/)).toBeInTheDocument();
    expect(screen.getByText(/Ana Pérez · Valoración/)).toBeInTheDocument();
    expect(screen.getByText(/Pide a recepción que las mueva/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abrir cita" })).not.toBeInTheDocument();
  });

  it("la auxiliar puede abrir cada cita en conflicto", async () => {
    servidor.use(conflicto([enConflicto]), http.get(`${API}/bloqueos`, () => HttpResponse.json([])));
    montar("/agenda", AUX);
    await userEvent.click(await screen.findByRole("button", { name: /Bloquear tiempo/ }));
    await userEvent.selectOptions(await screen.findByLabelText("Profesional", { selector: "#" + (screen.getAllByLabelText("Profesional").find((e) => e.closest("[role=dialog]"))?.id ?? "") }), "Dra. Uno");
    await userEvent.click(screen.getByRole("button", { name: "Crear bloqueo" }));
    await userEvent.click(await screen.findByRole("button", { name: "Abrir cita" }));
    expect(await screen.findByText("Detalle de la cita")).toBeInTheDocument();
  });
});

describe("agendar", () => {
  it("avisa si el espacio se ocupó y recarga los espacios", async () => {
    let n = 0;
    servidor.use(
      http.get(`${API}/pacientes`, () => HttpResponse.json([{ id: 7, nombres: "Ana", apellidos: "Pérez", documento: "123", celular: "+573001112233" }])),
      http.get(`${API}/espacios`, () => { n++; return HttpResponse.json({ profesional_id: 1, servicio_id: 1, dias: [{ fecha: "2026-11-17", horas: n === 1 ? ["2026-11-17T09:00:00-05:00", "2026-11-17T10:00:00-05:00"] : ["2026-11-17T10:00:00-05:00"] }] }); }),
      http.post(`${API}/citas`, () => error(409, "espacio_ocupado", "Ese espacio ya no está disponible")));
    montar("/agendar", AUX);
    await userEvent.type(await screen.findByLabelText(/Buscar por nombre/), "Ana");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await userEvent.click(await screen.findByRole("button", { name: /Ana Pérez/ }));
    await userEvent.selectOptions(screen.getByLabelText("Servicio"), "Valoración (60 min)");
    await userEvent.selectOptions(screen.getByLabelText("Profesional"), "Dra. Uno");
    await userEvent.click(await screen.findByRole("button", { name: /09:00/ }));
    await userEvent.click(screen.getByRole("button", { name: /Agendar cita ·/ }));
    expect(await screen.findAllByText(/ya no está disponible/)).not.toHaveLength(0);
    await waitFor(() => expect(screen.queryByRole("button", { name: /09:00/ })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /10:00/ })).toBeInTheDocument();
  });

  it("filtra pacientes por segmento sin escribir nada", async () => {
    const pedidas: string[] = [];
    servidor.use(http.get(`${API}/pacientes`, ({ request }) => {
      pedidas.push(new URL(request.url).search);
      return HttpResponse.json([{ id: 9, nombres: "Vera", apellidos: "Díaz", documento: "123", celular: null, etapa: "paciente", internacional: false, deportista: true }]);
    }));
    montar("/pacientes", AUX);
    await userEvent.click(await screen.findByRole("button", { name: "Deportistas" }));
    expect(screen.getByRole("button", { name: "Deportistas" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("button", { name: /Vera Díaz/ })).toHaveTextContent("Deportista");
    expect(pedidas).toEqual(["?segmento=deportista"]);
  });

  it("no pone el texto de búsqueda en la dirección", async () => {
    servidor.use(http.get(`${API}/pacientes`, () => HttpResponse.json([])));
    montar("/pacientes", AUX);
    await userEvent.type(await screen.findByLabelText(/Buscar por nombre/), "1234567890");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText("No encontramos pacientes")).toBeInTheDocument();
  });
});

describe("bandejas", () => {
  it("muestra los contadores de la API y registra la gestión de un seguimiento", async () => {
    servidor.use(
      http.get(`${API}/bandejas/seguimientos`, () => HttpResponse.json([{ id: 5, tipo: "inasistencia", estado: "abierto", escalado: true, abierto_en: "2026-11-15T10:00:00-05:00", paciente_id: 7, paciente: "Ana Pérez", celular: "+573001112233", intentos: 2, ultimo: null }])),
      http.post(`${API}/seguimientos/5/gestion`, ok()));
    montar("/bandejas?b=seguimientos", AUX);
    expect(await screen.findByRole("tab", { name: /No confirmadas\s*2/ })).toBeInTheDocument();
    expect(await screen.findByText("Necesita llamada")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Aceptó" }));
    await userEvent.click(await screen.findByRole("button", { name: "Sí, aceptó" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/seguimientos/5/gestion", cuerpo: { resultado: "acepto", detalle: "Gestión telefónica" } }));
  });
  it("una bandeja vacía explica qué significa", async () => {
    montar("/bandejas?b=no-confirmadas", AUX);
    expect(await screen.findByText("Todas las citas próximas están confirmadas.")).toBeInTheDocument();
  });
});

describe("qué hacer hoy", () => {
  const SEG = { id: 5, tipo: "inasistencia", estado: "abierto", escalado: true, abierto_en: "2026-11-15T10:00:00-05:00", paciente_id: 7, paciente: "Ana Pérez", celular: "+573001112233", intentos: 3, ultimo: null };
  const NC = { cita_id: 10, inicio: "2026-11-17T09:00:00-05:00", paciente_id: 8, paciente: "Luis Gómez", celular: "+573009998877", profesional: "Dra. Uno", id: 10, fin: "2026-11-17T10:00:00-05:00", estado: "programada" };
  it("es la pestaña inicial y ordena por urgencia: escalados antes que citas sin confirmar", async () => {
    servidor.use(
      http.get(`${API}/bandejas/no-confirmadas`, () => HttpResponse.json([NC])),
      http.get(`${API}/bandejas/seguimientos`, () => HttpResponse.json([SEG])));
    montar("/bandejas", AUX);
    expect(await screen.findByRole("tab", { name: /Qué hacer hoy/, selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Aceptó" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmó" })).toBeInTheDocument();
    const panel = screen.getByRole("tabpanel", { name: "Qué hacer hoy" });
    expect(panel.textContent!.indexOf("Ana Pérez")).toBeLessThan(panel.textContent!.indexOf("Luis Gómez"));
    expect(screen.getByText("Necesita llamada")).toBeInTheDocument();
  });
  it("cada fila se resuelve ahí mismo, con confirmación y sin cambiar de página", async () => {
    servidor.use(
      http.get(`${API}/bandejas/seguimientos`, () => HttpResponse.json([SEG])),
      http.post(`${API}/seguimientos/5/gestion`, ok()));
    montar("/bandejas", AUX);
    await userEvent.click(await screen.findByRole("button", { name: "Sin respuesta" }));
    expect(enviadas).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: "Sí, no contestó" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/seguimientos/5/gestion", cuerpo: { resultado: "sin_respuesta" } }));
    expect(screen.getByRole("tab", { name: /Qué hacer hoy/, selected: true })).toBeInTheDocument();
  });
  it("con la misma urgencia, el paciente de alto valor va primero y lleva su marca", async () => {
    const regular = { ...SEG, escalado: false, abierto_en: "2026-11-10T10:00:00-05:00", internacional: false, deportista: false };
    const vip = { ...SEG, id: 6, escalado: false, paciente_id: 9, paciente: "Vera Díaz", internacional: false, deportista: true };
    servidor.use(http.get(`${API}/bandejas/seguimientos`, () => HttpResponse.json([regular, vip])));
    montar("/bandejas", AUX);
    expect(await screen.findByText("Vera Díaz")).toBeInTheDocument();
    const panel = screen.getByRole("tabpanel", { name: "Qué hacer hoy" });
    expect(panel.textContent!.indexOf("Vera Díaz")).toBeLessThan(panel.textContent!.indexOf("Ana Pérez"));
    expect(within(panel).getByTitle(/alto valor/)).toHaveTextContent("Deportista");
  });
  it("sin pendientes dice que todo está al día", async () => {
    montar("/bandejas", AUX);
    expect(await screen.findByText("Todo al día")).toBeInTheDocument();
  });
});

describe("ficha del paciente", () => {
  const FICHA = {
    paciente: { id: 7, nombres: "Ana", apellidos: "Pérez", documento: "123", celular: "+573001112233", correo: null, acepta_mensajes: true,
      etapa: "paciente", internacional: true, deportista: false, segmento_origen: "sitio_en" },
    familia: { responsable: null, familiares: [] }, citas: [], historial: [], casos: [], mensajes: [],
  };
  it("muestra la marca de alto valor, de dónde salió, y la recepción la cambia con una casilla", async () => {
    servidor.use(
      http.get(`${API}/pacientes/7`, () => HttpResponse.json(FICHA)),
      http.put(`${API}/pacientes/7/segmentos`, async ({ request }) => { await registrar(request); return HttpResponse.json({ internacional: true, deportista: true, segmento_origen: "recepcion", segmento_marcado_en: "2026-11-16T10:00:00-05:00" }); }));
    montar("/pacientes/7", AUX);
    expect(await screen.findByTitle(/alto valor/)).toHaveTextContent("Internacional");
    expect(screen.getByText(/se registró en el sitio en inglés/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Internacional" })).toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Deportista de alto nivel" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/pacientes/7/segmentos", cuerpo: { internacional: true, deportista: true } }));
  });
});

describe("prospectos", () => {
  const PROSPECTO = {
    paciente: { id: 8, nombres: "Jane Doe", apellidos: "", documento: null, celular: null, correo: "jane@example.com", acepta_mensajes: false,
      etapa: "prospecto", internacional: true, deportista: false, segmento_origen: "sitio_web" },
    familia: { responsable: null, familiares: [] }, citas: [], historial: [], casos: [], mensajes: [],
  };
  it("se ve como prospecto en la búsqueda", async () => {
    servidor.use(
      http.get(`${API}/pacientes`, () => HttpResponse.json([{ id: 8, nombres: "Jane Doe", apellidos: "", documento: null, celular: null, etapa: "prospecto", internacional: true, deportista: false }])));
    montar("/pacientes", AUX);
    await userEvent.type(await screen.findByLabelText(/Buscar por nombre/), "jane");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByRole("button", { name: /Jane Doe/ })).toHaveTextContent("Prospecto");
  });
  it("la ficha no ofrece agendar y la recepción le registra el documento", async () => {
    servidor.use(
      http.get(`${API}/pacientes/8`, () => HttpResponse.json(PROSPECTO)),
      http.put(`${API}/pacientes/8/identificacion`, async ({ request }) => { await registrar(request); return HttpResponse.json({ id: 8, etapa: "paciente", documento: "1234567", celular: "+573001234567" }); }));
    montar("/pacientes/8", AUX);
    expect(await screen.findByTitle(/aún no tiene documento/)).toHaveTextContent("Prospecto");
    expect(screen.queryByRole("link", { name: "Agendar cita" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Documento"), "1234567");
    await userEvent.type(screen.getByLabelText("Celular"), "3001234567");
    await userEvent.click(screen.getByRole("button", { name: "Registrar documento" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/pacientes/8/identificacion", cuerpo: { documento: "1234567", celular: "3001234567" } }));
  });
  it("muestra el aviso cuando el documento ya es de otro paciente", async () => {
    servidor.use(
      http.get(`${API}/pacientes/8`, () => HttpResponse.json(PROSPECTO)),
      http.put(`${API}/pacientes/8/identificacion`, () => HttpResponse.json({ codigo: "documento_existente", mensaje: "Ya existe un paciente con ese documento" }, { status: 409 })));
    montar("/pacientes/8", AUX);
    await userEvent.type(await screen.findByLabelText("Documento"), "55");
    await userEvent.type(screen.getByLabelText("Celular"), "3001234567");
    await userEvent.click(screen.getByRole("button", { name: "Registrar documento" }));
    expect(await screen.findByText("Ya existe un paciente con ese documento")).toBeInTheDocument();
  });
});

describe("pacientes precargados", () => {
  it("muestra sin buscar las citas de hoy y mañana, los pacientes en riesgo y los dados de baja", async () => {
    servidor.use(
      http.get(`${API}/agenda`, () => HttpResponse.json(agenda([cita({ estado: "no_confirmada" }), cita({ id: 11, dia: "2026-11-17", inicio: "2026-11-17T08:00:00-05:00", paciente_id: 9, paciente: "Marta Ruiz" })]))),
      http.get(`${API}/bandejas/en-riesgo`, () => HttpResponse.json([{ tratamiento_id: 3, paciente_id: 12, paciente: "Pedro Soto", ultima_cita: "2026-08-01", dias_sin_cita: 90, caso_id: null }])),
      http.get(`${API}/bandejas/dados-de-baja`, () => HttpResponse.json([{ cita_id: 20, inicio: "2026-11-18T09:00:00-05:00", paciente_id: 13, paciente: "Rosa Vega", celular: "+573001110000", profesional: "Dra. Uno", id: 20, fin: "2026-11-18T10:00:00-05:00", estado: "programada" }])));
    montar("/pacientes", AUX);
    const hoy = await screen.findByRole("region", { name: "Citas de hoy y mañana" });
    expect(await within(hoy).findByText("Ana Pérez")).toBeInTheDocument();
    expect(within(hoy).getByText("Sin confirmar")).toBeInTheDocument();
    expect(within(hoy).getByText(/Mañana · 08:00/)).toBeInTheDocument();
    expect(await screen.findByText("Pedro Soto")).toBeInTheDocument();
    expect(screen.getByText("90 días sin cita")).toBeInTheDocument();
    expect(await screen.findByText("Rosa Vega")).toBeInTheDocument();
    expect(within(hoy).getByRole("link", { name: /Ana Pérez/ })).toHaveAttribute("href", "/pacientes/7");
  });
});

describe("sistema", () => {
  const SIS = (o: object) => http.get(`${API}/sistema`, () => HttpResponse.json({ tareas_fallidas: [], tareas_pendientes: 162, tareas_atrasadas: 0, ultimo_cierre: "2026-11-16", configuracion: { recordatorios_horas: [48, 24] }, ...o }));
  it("todo bien: dice en palabras que funciona y esconde la configuración en Avanzado", async () => {
    servidor.use(SIS({}));
    montar("/sistema", AUX);
    expect(await screen.findByText("Los mensajes automáticos funcionan")).toBeInTheDocument();
    expect(screen.getByText("Indicadores al día")).toBeInTheDocument();
    expect(screen.getByText(/Tareas pendientes \(162\)/)).toBeInTheDocument();
    expect(screen.getByText("Avanzado: valores del sistema (solo lectura)").closest("details")).not.toHaveAttribute("open");
  });
  const RECORDATORIO = { tipo: "recordatorio", ejecutar_en: "2026-11-15T10:00:00-05:00", intentos: 3, error: "Traceback ...\nKeyError: 'acepta_correo'",
    titulo: "No salió el recordatorio de una cita", titulo_varias: "recordatorios de cita no salieron", causa: "Falla interna del sistema.",
    que_hacer: "Llama al paciente para recordarle la cita y confirmarla.", cita_inicio: "2026-11-17T09:00:00-05:00" };
  it("con tareas fallidas: una alerta en palabras por causa, con a quién llamar; la traza queda escondida", async () => {
    servidor.use(SIS({ ultimo_cierre: "2026-11-10", tareas_fallidas: [
      { ...RECORDATORIO, id: 1, paciente_id: 7, paciente: "Ana Pérez", cita_id: 70 },
      { ...RECORDATORIO, id: 2, paciente_id: 8, paciente: "Luis Mora", cita_id: 80 },
      { id: 3, tipo: "entregar_mensaje", ejecutar_en: "2026-11-15T10:00:00-05:00", intentos: 3, error: "sin saldo", titulo: "No se entregó un WhatsApp",
        titulo_varias: "WhatsApp no se entregaron", causa: "sin saldo", que_hacer: "Llama al paciente.", paciente_id: 7, paciente: "Ana Pérez", cita_id: null, cita_inicio: null },
    ] }));
    montar("/sistema", AUX);
    expect(await screen.findByText("3 avisos no salieron")).toBeInTheDocument();
    expect(screen.getByText("Indicadores atrasados 6 días")).toBeInTheDocument();
    const alertas = within(screen.getByRole("region", { name: "Alertas" }));
    expect(alertas.getByText("2 recordatorios de cita no salieron")).toBeInTheDocument();
    expect(alertas.getByText("No se entregó un WhatsApp")).toBeInTheDocument();
    expect(alertas.getByRole("link", { name: "Luis Mora" })).toHaveAttribute("href", "/pacientes/8");
    expect(alertas.getAllByRole("link", { name: /Cita del/ })[0]).toHaveAttribute("href", "/agenda?fecha=2026-11-17&cita=70");
    expect(screen.getAllByText("Detalle técnico (para quien administra el sistema)")[0].closest("details")).not.toHaveAttribute("open");
  });
  it("con mensajes atrasados avisa que el envío está detenido", async () => {
    servidor.use(SIS({ tareas_atrasadas: 4 }));
    montar("/sistema", AUX);
    expect(await screen.findByText("El envío de mensajes está detenido")).toBeInTheDocument();
    expect(screen.getByText(/4 mensajes debieron salir hace más de 15 minutos/)).toBeInTheDocument();
  });
  it("nunca cerrado se marca como problema", async () => {
    servidor.use(SIS({ ultimo_cierre: null }));
    montar("/sistema", AUX);
    expect(await screen.findByText("Los indicadores nunca se han actualizado")).toBeInTheDocument();
  });
});

const SIN_PENDIENTES = { resueltos: 0, mediana_horas: null, p90_horas: null, abiertos_hoy: 0, vencidos: 0 };
describe("indicadores", () => {
  it("vuelve a consultar con los filtros elegidos", async () => {
    const pedidos: string[] = [];
    const vacio = (ruta: string, cuerpo: unknown) => http.get(`${API}/indicadores/${ruta}`, ({ request }) => { if (ruta === "resumen") pedidos.push(new URL(request.url).search); return HttpResponse.json(cuerpo as never); });
    servidor.use(
      vacio("resumen", { citas: 3, atendidas: 2, no_asistio: 1, atencion_efectiva: 0.5, asistencia: 0.5, inasistencia: 0.25, sin_desenlace: 0, capacidad_aplica: true, cancelaciones: 1, cancelaciones_tardias: 0, cancelaciones_recuperadas: 0, recuperacion: null, confirmacion: null, ocupacion: null, minutos_disponibles: 0, minutos_atendidos: 0, cupos_liberados: 0, cupos_ocupados_oferta: 0, cupos_ocupados_agendamiento: 0, cupos_vacios: 0, valor_perdido: 0, valor_perdido_inasistencia: 0, valor_perdido_tardias: 0, citas_sin_valor: 0, metas: {} }),
      vacio("tendencia", []), vacio("por-profesional", []), vacio("por-servicio", []), vacio("motivos", []), vacio("tiempo-entre-citas", { por_servicio: [], por_paciente_dias: null }),
      vacio("faltas-repetidas", []), vacio("dia-hora", []), vacio("reagendamiento", { mediana_dias: null, total: 0, buckets: { mismo_dia: 0, "1_3": 0, "4_14": 0, "15_60": 0, no_reagendo: 0 } }),
      vacio("pendientes", { cierre_citas: SIN_PENDIENTES, mensajes: SIN_PENDIENTES, seguimientos: SIN_PENDIENTES, por_usuario: [], registro_desde: "2026-11-25" }), vacio("recordatorios", { con_recordatorio: { n: 0, no_asistio: 0, inasistencia: null }, sin_recordatorio: { n: 0, no_asistio: 0, inasistencia: null }, embudo: { citas: 0, con_recordatorio: 0, confirmadas: 0, atendidas: 0 } }),
      http.get(`${API}/sistema`, () => HttpResponse.json({ tareas_fallidas: [], tareas_pendientes: 0, tareas_atrasadas: 0, ultimo_cierre: null, configuracion: {} })));
    montar("/indicadores", AUX);
    expect(await screen.findByText("25.0 %")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Profesional"), "Dr. Dos");
    await waitFor(() => expect(pedidos.at(-1)).toContain("profesional_id=2"));
    await userEvent.selectOptions(screen.getByLabelText("Servicio"), "Valoración");
    await waitFor(() => expect(pedidos.at(-1)).toMatch(/profesional_id=2.*servicio_id=1|servicio_id=1.*profesional_id=2/));
    expect(pedidos[0]).toContain("desde=2026-10-18");   // por defecto: últimos 30 días
  });
});

describe("agenda", () => {
  it("el especialista ve su día con la hora del sistema y sus citas", async () => {
    servidor.use(http.get(`${API}/agenda`, () => HttpResponse.json(agenda([cita(), cita({ id: 11, estado: "cancelada", acciones: [], inicio: "2026-11-16T11:00:00-05:00", fin: "2026-11-16T12:00:00-05:00", paciente: "Luis Gómez" })]))));
    montar("/agenda", ESP);
    expect(await screen.findByRole("button", { name: /09:00 Ana Pérez, Valoración, Programada/ })).toBeInTheDocument();
    expect(screen.getByText("Citas canceladas (1)")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Hora actual del sistema 10:30/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Agendar cita/ })).not.toBeInTheDocument();
  });
  it("el día de hoy marca la hora del sistema y las citas pasadas sin cerrar «Por cerrar»", async () => {
    servidor.use(http.get(`${API}/agenda`, () => HttpResponse.json(agenda([cita({ acciones: ["desenlace"] }), cita({ id: 11, inicio: "2026-11-16T14:00:00-05:00", fin: "2026-11-16T15:00:00-05:00", paciente: "Luis Gómez", acciones: ["confirmar"] })]))));
    montar("/agenda", AUX);
    expect((await screen.findAllByRole("img", { name: /Hora actual del sistema 10:30/ })).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Por cerrar").length).toBeGreaterThan(0);
  });
  it("la auxiliar ve el resumen del día con sus enlaces y oculta los mensajes cuando no hay", async () => {
    servidor.use(http.get(`${API}/resumen-dia`, () => HttpResponse.json({ citas_hoy: 5, sin_confirmar: 2, mensajes: 0, por_cerrar: 3 })));
    montar("/agenda", AUX);
    const r = await screen.findByRole("navigation", { name: "Resumen del día" });
    expect(await within(r).findByRole("link", { name: "5 citas hoy" })).toHaveAttribute("href", "/agenda");
    expect(within(r).getByRole("link", { name: "2 sin confirmar hoy y mañana" })).toHaveAttribute("href", "/bandejas?b=no-confirmadas");
    expect(within(r).getByRole("link", { name: "3 por cerrar" })).toHaveAttribute("href", "/bandejas?b=sin-desenlace");
    expect(within(r).queryByText(/mensaje/)).not.toBeInTheDocument();
  });
  it("con mensajes por responder el resumen los enlaza; el especialista no ve resumen", async () => {
    servidor.use(http.get(`${API}/resumen-dia`, () => HttpResponse.json({ citas_hoy: 1, sin_confirmar: 0, mensajes: 4, por_cerrar: 0 })));
    montar("/agenda", AUX);
    expect(await screen.findByRole("link", { name: "4 mensajes por responder" })).toHaveAttribute("href", "/bandejas?b=sin-interpretar");
  });
  it("el especialista no ve el resumen ni la opción «Todos» en la semana", async () => {
    montar("/agenda?vista=semana", ESP);
    expect(await screen.findByRole("heading", { name: /Mi agenda/ })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Resumen del día" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Todos" })).not.toBeInTheDocument();
  });
  it("la semana muestra a todos los profesionales por defecto, permite elegir uno y navegar", async () => {
    const pedidos: string[] = [];
    servidor.use(http.get(`${API}/agenda`, ({ request }) => { pedidos.push(new URL(request.url).search); return HttpResponse.json(agenda([], { desde: "2026-11-16", hasta: "2026-11-22" })); }));
    montar("/agenda?vista=semana", AUX);
    const filtro = await screen.findByLabelText("Profesional");
    expect(filtro).toHaveValue("");
    expect(within(filtro).getByRole("option", { name: "Todos" })).toBeInTheDocument();
    await waitFor(() => expect(pedidos.at(-1)).toBe("?desde=2026-11-16&hasta=2026-11-22"));
    await userEvent.click(screen.getByRole("button", { name: "Semana siguiente" }));
    await waitFor(() => expect(pedidos.at(-1)).toBe("?desde=2026-11-23&hasta=2026-11-29"));
    await userEvent.selectOptions(filtro, "Dra. Uno");
    await waitFor(() => expect(pedidos.at(-1)).toBe("?desde=2026-11-23&hasta=2026-11-29&profesional_id=1"));
  });
});


describe("negocios, clave temporal y administración", () => {
  const OTRO = { id: 2, nombre_corto: "otra", nombre: "Otra Clínica", zona_horaria: "America/Bogota" };

  it("con varios negocios y ninguno elegido, pide elegir y entra con el elegido", async () => {
    const sin = { ...AUX, rol: null, negocio: null, negocios: [AUX.negocio!, OTRO] } as typeof AUX;
    montar("/agenda", sin);
    servidor.use(http.post(`${API}/sesion/negocio`, async ({ request }) => {
      await registrar(request);
      servidor.use(http.get(`${API}/sesion`, () => HttpResponse.json(AUX)));
      return HttpResponse.json(AUX);
    }));
    await userEvent.click(await screen.findByRole("button", { name: "Blissens Odontología" }));
    expect(await screen.findByRole("heading", { name: /Agenda/ })).toBeInTheDocument();
    expect(enviadas.some((e) => e.ruta.endsWith("/sesion/negocio"))).toBe(true);
  });

  it("con contraseña temporal no deja usar nada hasta cambiarla", async () => {
    montar("/pacientes", { ...AUX, debe_cambiar_clave: true });
    expect(await screen.findByRole("heading", { name: "Elige tu contraseña" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Pacientes" })).not.toBeInTheDocument();
  });

  it("solo los administradores ven Administración", async () => {
    montar("/administracion", AUX);
    expect(await screen.findByRole("heading", { name: /Agenda/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Administración/ })).not.toBeInTheDocument();
  });

  it("un administrador crea un usuario y ve la contraseña temporal una sola vez", async () => {
    const usuario = { acceso_id: 9, id: 9, nombre_usuario: "nueva", nombre: "Nueva", rol: "auxiliar", activo: true, administrador: false, profesional_id: null, ultimo_acceso: null, bloqueado: false };
    servidor.use(
      http.get(`${API}/admin/usuarios`, () => HttpResponse.json([])),
      http.post(`${API}/admin/usuarios`, async ({ request }) => { await registrar(request); return HttpResponse.json({ usuario, clave_temporal: "abcd-efgh-jkmn" }, { status: 201 }); }),
    );
    montar("/administracion", { ...AUX, administrador: true });
    await userEvent.type(await screen.findByLabelText("Usuario"), "nueva");
    await userEvent.type(screen.getByLabelText("Nombre visible"), "Nueva");
    await userEvent.click(screen.getByRole("button", { name: "Crear con contraseña temporal" }));
    expect(await screen.findByLabelText("Contraseña temporal")).toHaveTextContent("abcd-efgh-jkmn");
  });

  it("un administrador fija el valor de un servicio por fila y las metas de los indicadores", async () => {
    const servicios = [
      { id: 1, nombre: "Valoración", duracion_min: 60, autoagendable: true, valor: 80000 },
      { id: 2, nombre: "Limpieza", duracion_min: 30, autoagendable: true, valor: null }];
    servidor.use(
      http.get(`${API}/admin/usuarios`, () => HttpResponse.json([])),
      http.get(`${API}/servicios`, () => HttpResponse.json(servicios)),
      http.get(`${API}/admin/metas`, () => HttpResponse.json({ inasistencia: { max: 0.15 } })),
      http.put(`${API}/admin/servicios/:id`, async ({ request, params }) => { await registrar(request); return HttpResponse.json({ ...servicios[0], id: Number(params.id) }); }),
      http.put(`${API}/admin/metas`, async ({ request }) => { await registrar(request); return HttpResponse.json({}); }),
    );
    montar("/administracion", { ...AUX, administrador: true });
    expect(await screen.findByText(/Es un valor promedio, no una factura/)).toBeInTheDocument();
    expect(await screen.findByText(/Guardado: .*80\.000/)).toBeInTheDocument();
    const fila = screen.getByRole("form", { name: "Valor de Limpieza" });
    expect(within(fila).getByRole("button", { name: "Guardar" })).toBeDisabled();           // sin cambios no hay nada que guardar
    await userEvent.type(within(fila).getByLabelText("Limpieza"), "120000");
    await userEvent.click(within(fila).getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Valor guardado")).toBeInTheDocument();
    expect(enviadas.at(-1)).toMatchObject({ metodo: "PUT", ruta: "/api/v1/admin/servicios/2", cuerpo: { valor: 120000 } });

    const metas = screen.getByRole("form", { name: "Metas de indicadores" });
    expect(within(metas).getByLabelText("Inasistencia máxima (%)")).toHaveValue(15);
    await userEvent.type(within(metas).getByLabelText("Asistencia mínima (%)"), "80");
    await userEvent.clear(within(metas).getByLabelText("Inasistencia máxima (%)"));           // vacío quita la meta
    await userEvent.type(within(metas).getByLabelText("Dinero perdido máximo ($)"), "2000000");
    await userEvent.click(within(metas).getByRole("button", { name: "Guardar metas" }));
    await waitFor(() => expect(enviadas.at(-1)).toMatchObject({ ruta: "/api/v1/admin/metas", cuerpo: { asistencia: { min: 0.8 }, dinero_perdido: { max: 2000000 } } }));
    expect(enviadas.at(-1)?.cuerpo).not.toHaveProperty("inasistencia");
  });
});
