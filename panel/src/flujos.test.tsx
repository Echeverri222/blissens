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
    for (const t of ["Bandejas", "Pacientes", "Indicadores", "Sistema"]) expect(within(menu).queryByText(t)).not.toBeInTheDocument();
  });
  it("la auxiliar ve todas sus secciones, el contador de bandejas y el enlace al simulador en modo demo", async () => {
    montar("/agenda", AUX);
    const menu = (await screen.findAllByRole("navigation", { name: "Secciones" }))[0];
    for (const t of ["Agenda", "Bandejas", "Pacientes", "Indicadores", "Sistema"]) expect(within(menu).getByText(t)).toBeInTheDocument();
    expect(await within(menu).findByLabelText("3 pendientes")).toBeInTheDocument();
    expect(screen.getByText("Modo demo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Simulador/ })).toHaveAttribute("target", "_blank");
    expect(screen.getByLabelText("Hora del sistema")).toHaveTextContent(/16 de nov.*10:30/);
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
    expect(await screen.findByText("ESCALADO")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Aceptó" }));
    await waitFor(() => expect(enviadas[0]).toMatchObject({ ruta: "/api/v1/seguimientos/5/gestion", cuerpo: { resultado: "acepto", detalle: "Gestión telefónica" } }));
  });
  it("una bandeja vacía explica qué significa", async () => {
    servidor.use(http.get(`${API}/bandejas/no-confirmadas`, () => HttpResponse.json([])));
    montar("/bandejas", AUX);
    expect(await screen.findByText("Todas las citas próximas están confirmadas.")).toBeInTheDocument();
  });
});

describe("indicadores", () => {
  it("vuelve a consultar con los filtros elegidos", async () => {
    const pedidos: string[] = [];
    const vacio = (ruta: string, cuerpo: unknown) => http.get(`${API}/indicadores/${ruta}`, ({ request }) => { if (ruta === "resumen") pedidos.push(new URL(request.url).search); return HttpResponse.json(cuerpo as never); });
    servidor.use(
      vacio("resumen", { citas: 3, atendidas: 2, no_asistio: 1, atencion_efectiva: 0.5, inasistencia: 0.25, cancelaciones: 1, cancelaciones_tardias: 0, cancelaciones_recuperadas: 0, recuperacion: null, confirmacion: null, ocupacion: null, minutos_disponibles: 0, minutos_atendidos: 0, cupos_liberados: 0, cupos_ocupados_oferta: 0, cupos_ocupados_agendamiento: 0, cupos_vacios: 0 }),
      vacio("tendencia", []), vacio("por-profesional", []), vacio("por-servicio", []), vacio("motivos", []), vacio("tiempo-entre-citas", { por_servicio: [], por_paciente_dias: null }),
      http.get(`${API}/sistema`, () => HttpResponse.json({ tareas_fallidas: [], tareas_pendientes: 0, ultimo_cierre: null, configuracion: {} })));
    montar("/indicadores", AUX);
    expect(await screen.findByText("25.0 %")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Profesional"), "Dr. Dos");
    await waitFor(() => expect(pedidos.at(-1)).toContain("profesional_id=2"));
    await userEvent.selectOptions(screen.getByLabelText("Servicio"), "Valoración");
    await waitFor(() => expect(pedidos.at(-1)).toMatch(/profesional_id=2.*servicio_id=1|servicio_id=1.*profesional_id=2/));
    expect(pedidos[0]).toContain("desde=2026-09-17");
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
  it("la semana muestra un profesional a la vez y permite navegar", async () => {
    const pedidos: string[] = [];
    servidor.use(http.get(`${API}/agenda`, ({ request }) => { pedidos.push(new URL(request.url).search); return HttpResponse.json(agenda([], { desde: "2026-11-16", hasta: "2026-11-22" })); }));
    montar("/agenda?vista=semana", AUX);
    await waitFor(() => expect(pedidos.at(-1)).toBe("?desde=2026-11-16&hasta=2026-11-22&profesional_id=1"));
    await userEvent.click(screen.getByRole("button", { name: "Semana siguiente" }));
    await waitFor(() => expect(pedidos.at(-1)).toBe("?desde=2026-11-23&hasta=2026-11-29&profesional_id=1"));
  });
});
