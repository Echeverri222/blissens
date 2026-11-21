import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { montar } from "@/pruebas/montar";
import { servidor } from "@/pruebas/servidor";

const API = "*/api/v1";

describe("portal público del paciente en React", () => {
  it("la ruta /portal muestra el formulario de identificación de Blissens", async () => {
    montar("/portal", null);
    expect(await screen.findByRole("heading", { name: "Agenda tu cita" })).toBeInTheDocument();
    expect(screen.getByLabelText("Documento de identidad")).toBeInTheDocument();
    expect(screen.getByLabelText("Celular WhatsApp")).toBeInTheDocument();
  });

  it("al ingresar datos de paciente nuevo despliega nombre, apellido y autorización", async () => {
    servidor.use(
      http.post(`${API}/publico/identificar`, () =>
        HttpResponse.json({ estado: "requiere_registro" })
      )
    );
    montar("/portal", null);
    await userEvent.type(screen.getByLabelText("Documento de identidad"), "100200300");
    await userEvent.type(screen.getByLabelText("Celular WhatsApp"), "3001234567");
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));

    expect(await screen.findByLabelText("Nombres")).toBeInTheDocument();
    expect(screen.getByLabelText("Apellidos")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
  });

  it("la ruta /p/:token carga las citas del paciente", async () => {
    servidor.use(
      http.get(`${API}/publico/citas`, () =>
        HttpResponse.json({
          paciente: { id: 1, nombres: "Laura", apellidos: "Gómez" },
          citas: [
            {
              id: 10,
              estado: "confirmada",
              dia: "2026-11-20",
              inicio: "2026-11-20T10:00:00-05:00",
              fin: "2026-11-20T10:30:00-05:00",
              profesional: "Dra. Carolina Martínez",
              servicio: "Diseño de Sonrisa",
            },
          ],
        })
      )
    );
    montar("/p/token-valido", null);
    expect(await screen.findByRole("heading", { name: /Hola,\s+Laura/ })).toBeInTheDocument();
    expect(screen.getByText("Diseño de Sonrisa")).toBeInTheDocument();
    expect(screen.getByText("Dra. Carolina Martínez")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cambiar fecha" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cancelar" })).toBeInTheDocument();
  });

  it("la ruta /p/:token/cancelar/:id muestra los motivos de cancelación", async () => {
    servidor.use(
      http.get(`${API}/publico/motivos-cancelacion`, () =>
        HttpResponse.json([
          { id: 1, etiqueta: "Inconveniente laboral" },
          { id: 2, etiqueta: "Salud / Calamidad" },
        ])
      )
    );
    montar("/p/token-valido/cancelar/10", null);
    expect(await screen.findByRole("heading", { name: "¿Deseas cancelar tu cita?" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Inconveniente laboral" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salud / Calamidad" })).toBeInTheDocument();
  });

  it("la ruta /correo/baja/:token muestra la confirmación de desuscripción", async () => {
    montar("/correo/baja/token-baja", null);
    expect(await screen.findByRole("heading", { name: "¿Dejar de recibir correos?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sí, dar de baja mi correo" })).toBeInTheDocument();
  });
});
