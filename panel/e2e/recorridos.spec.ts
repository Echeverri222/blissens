import { expect, test, type Page } from "@playwright/test";

const CLAVE = "demo-blissens"; // usuarios de demostración con datos ficticios

async function entrar(page: Page, usuario: string, ruta = "/panel/") {
  await page.goto(ruta);
  await page.getByLabel("Usuario").fill(usuario);
  await page.getByLabel("Contraseña").fill(CLAVE);
  await page.getByRole("button", { name: "Entrar" }).click();
}
const menu = (page: Page) => page.getByRole("navigation", { name: "Secciones" }).first();

test("especialista: ve solo su agenda y su horario, y no puede abrir los pendientes", async ({ page }) => {
  await entrar(page, "especialista1");
  await expect(page.getByRole("heading", { name: /Mi agenda/ })).toBeVisible();
  await expect(menu(page).getByText("Mi horario")).toBeVisible();
  for (const t of ["Pendientes", "Pacientes", "Indicadores", "Sistema"]) await expect(menu(page).getByText(t)).toHaveCount(0);

  await page.goto("/panel/bandejas");
  await expect(page.getByRole("heading", { name: /Mi agenda/ })).toBeVisible();

  await menu(page).getByText("Mi horario").click();
  await expect(page.getByRole("heading", { name: /Mi horario/ })).toBeVisible();
});

test("auxiliar: recorre agenda, pendientes, pacientes, indicadores y sistema", async ({ page }) => {
  await page.goto("/panel/pacientes");
  await expect(page.getByRole("heading", { name: "Iniciar sesión" })).toBeVisible(); // sin sesión no hay datos
  await entrar(page, "auxiliar", "/panel/pacientes"); // y al entrar vuelve a donde iba
  await expect(page.getByRole("heading", { name: "Pacientes" })).toBeVisible();

  for (const t of ["Agenda", "Pendientes", "Pacientes", "Indicadores", "Sistema"]) await expect(menu(page).getByText(t)).toBeVisible();

  await menu(page).getByText("Pendientes").click();
  await expect(page.getByRole("tab").first()).toBeVisible();
  await menu(page).getByText("Indicadores").click();
  await expect(page.getByRole("heading", { name: "Indicadores" })).toBeVisible();
  await menu(page).getByText("Sistema").click();
  await expect(page.getByRole("heading", { name: "Sistema" })).toBeVisible();
  await menu(page).getByText("Agenda", { exact: true }).click();
  await expect(page.getByRole("heading", { name: /Agenda/ })).toBeVisible();
});
