import { describe, expect, it } from "vitest";
import type { Agenda } from "@/api/tipos";
import { columnaDia, posicion, rangoVisible, unir } from "./calendario";
import { comportamientoDe } from "./errores";
import { nombreCorto, profesionalCorto } from "./nombres";
import { totalLlamadas } from "./pendientes";
import { digitosWhatsApp, esSolicitudWeb, separarNombre, tamanoLegible, tipoDeSolicitud } from "./solicitudes";
import { ahoraSistema, aIso, fechaDe, fechaHora, horaDe, lunesDe, sumarDias } from "./tiempo";
import { agenda, cita } from "@/pruebas/servidor";

describe("tiempo", () => {
  it("muestra la misma fecha y hora en Bogotá sin importar la zona del navegador", () => {
    const t = "2026-11-16T23:30:00-05:00"; // ya es 17-nov en UTC
    expect(fechaDe(t)).toBe("2026-11-16");
    expect(horaDe(t)).toBe("23:30");
    expect(fechaHora(t)).toMatch(/16 de nov.*23:30/);
  });
  it("calcula semanas y días en fechas de calendario", () => {
    expect(lunesDe("2026-11-22")).toBe("2026-11-16");
    expect(lunesDe("2026-11-16")).toBe("2026-11-16");
    expect(sumarDias("2026-12-31", 1)).toBe("2027-01-01");
    expect(aIso("2026-11-16", "08:00")).toBe("2026-11-16T08:00:00-05:00");
  });
  it("«ahora» sigue a la hora del sistema y no a la del navegador", () => {
    const leida = Date.parse("2030-01-01T00:00:00Z"); // el navegador cree estar en 2030
    const ahora = ahoraSistema("2026-11-16T10:30:00-05:00", leida, leida + 90_000);
    expect(fechaDe(ahora)).toBe("2026-11-16");
    expect(horaDe(ahora)).toBe("10:31");
  });
});

describe("rejilla de calendario", () => {
  const col = (a: Agenda, fecha = "2026-11-16", pro: number | null = 1) => columnaDia(fecha, pro, a);
  it("coloca citas contiguas una tras otra sin cruzarse", () => {
    const a = agenda([cita({ id: 1 }), cita({ id: 2, inicio: "2026-11-16T10:00:00-05:00", fin: "2026-11-16T11:00:00-05:00" })]);
    expect(col(a).citas.map((x) => [x.desde, x.hasta])).toEqual([[540, 600], [600, 660]]);
  });
  it("une bloqueos cruzados en una sola zona", () => {
    const b = (id: number, i: string, f: string, motivo: string) => ({ id, profesional_id: 1, inicio: `2026-11-16T${i}:00-05:00`, fin: `2026-11-16T${f}:00-05:00`, motivo, creado_por: null });
    const c = col(agenda([], { bloqueos: [b(1, "09:00", "11:00", "Reunión"), b(2, "10:00", "12:00", "Curso"), b(3, "14:00", "15:00", "")] }));
    expect(c.bloqueos.map((x) => [x.desde, x.hasta, x.motivos])).toEqual([[540, 720, ["Reunión", "Curso"]], [840, 900, []]]);
  });
  it("recorta una cita que cruza el borde del día", () => {
    const a = agenda([cita({ inicio: "2026-11-15T23:00:00-05:00", fin: "2026-11-16T01:00:00-05:00" })]);
    expect(col(a).citas[0]).toMatchObject({ desde: 0, hasta: 60 });
    expect(col(a, "2026-11-15").citas[0]).toMatchObject({ desde: 1380, hasta: 1440 });
  });
  it("amplía el rango visible si una cita cruza el borde del horario", () => {
    const a = agenda([cita({ inicio: "2026-11-16T18:30:00-05:00", fin: "2026-11-16T19:30:00-05:00" })]);
    const v = rangoVisible([col(a)]);
    expect(v).toEqual({ desde: 420, hasta: 20 * 60 });
    expect(posicion({ desde: 18 * 60 + 30, hasta: 19 * 60 + 30 }, v)).not.toBeNull();
    expect(posicion({ desde: 0, hasta: 60 }, v)).toBeNull();
  });
  it("en la semana, un día sin atención no tiene franjas", () => {
    const a = agenda([], { desde: "2026-11-16", hasta: "2026-11-22" });
    expect(col(a, "2026-11-17").franjas).toEqual([]);
    expect(col(a, "2026-11-16").franjas).toEqual([{ desde: 480, hasta: 1020 }]);
  });
  it("saca de la rejilla las canceladas y las citas sin hora", () => {
    const a = agenda([cita({ id: 1 }), cita({ id: 2, estado: "cancelada", acciones: [] })], { citas_sin_hora: [cita({ id: 3, inicio: null, fin: null })] });
    const c = col(a);
    expect(c.citas.map((x) => x.cita.id)).toEqual([1]);
    expect(c.canceladas.map((x) => x.id)).toEqual([2]);
    expect(c.sinHora.map((x) => x.id)).toEqual([3]);
  });
  it("unir fusiona tramos que se tocan", () => {
    expect(unir([{ desde: 0, hasta: 10 }, { desde: 10, hasta: 20 }, { desde: 30, hasta: 40 }])).toEqual([{ desde: 0, hasta: 20 }, { desde: 30, hasta: 40 }]);
  });
});

describe("tabla de errores", () => {
  it.each([
    ["no_autenticado", "iniciar_sesion"], ["credenciales_invalidas", "mensaje_inicio"], ["inicio_bloqueado", "mensaje_inicio"],
    ["sin_permiso", "no_disponible"], ["no_existe", "no_disponible"], ["espacio_ocupado", "recargar_espacios"],
    ["bloqueo_con_citas", "conflicto_bloqueo"], ["desenlace_anticipado", "recargar_dato"], ["no_reversible", "recargar_dato"],
    ["transicion_invalida", "recargar_dato"], ["bloqueo_pasado", "recargar_dato"], ["datos_invalidos", "mensaje_formulario"],
    ["bloqueo_invalido", "mensaje_formulario"], ["clave_invalida", "mensaje_formulario"], ["documento_existente", "mensaje_formulario"],
    ["algo_raro", "generico"], ["red", "generico"],
  ])("%s → %s", (codigo, esperado) => expect(comportamientoDe(codigo)).toBe(esperado));
});

describe("solicitudes del sitio web", () => {
  it("reconoce las solicitudes web por su origen", () => {
    expect(esSolicitudWeb({ origen: "sitio" })).toBe(true);
    expect(esSolicitudWeb({ origen: "paciente" })).toBe(false);
  });
  it("nombra el tipo con el paquete", () => {
    expect(tipoDeSolicitud({ interes: "experiencia", paquete: "premium" })).toBe("Experiencia · Premium (hotel)");
    expect(tipoDeSolicitud({ interes: "evaluacion_virtual", paquete: null })).toBe("Evaluación virtual");
    expect(tipoDeSolicitud({ interes: null, paquete: null })).toBe("Contacto");
  });
  it("prepara contacto, tamaños y nombre para la ficha", () => {
    expect(digitosWhatsApp("+1 305 555 0100")).toBe("13055550100");
    expect(digitosWhatsApp("")).toBeNull();
    expect(tamanoLegible(1536 * 1024)).toBe("1,5 MB");
    expect(tamanoLegible(300)).toBe("1 KB");
    expect(separarNombre("Ana")).toEqual({ nombres: "Ana", apellidos: "" });
    expect(separarNombre("Ana López")).toEqual({ nombres: "Ana", apellidos: "López" });
    expect(separarNombre("Ana María López Buitrago")).toEqual({ nombres: "Ana María", apellidos: "López Buitrago" });
  });
});

describe("llamadas pendientes", () => {
  it("el total solo suma lo que se resuelve llamando", () => {
    const conteo = { seguimientos: 2, contactos: 1, sin_interpretar: 3, no_confirmadas: 4, dados_de_baja: 1, sin_desenlace: 9, en_riesgo: 7, cupos_libres: 5 };
    expect(totalLlamadas(conteo as never)).toBe(11);
  });
});

describe("nombres cortos", () => {
  it("deja el nombre y el primer apellido", () => {
    expect(nombreCorto("Ana María Pérez Gómez")).toBe("Ana Pérez");
    expect(nombreCorto("Ana Pérez")).toBe("Ana Pérez");
    expect(profesionalCorto("Dra. Uno")).toContain("Uno");
  });
});
