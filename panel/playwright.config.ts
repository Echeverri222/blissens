import { defineConfig } from "@playwright/test";

// Los recorridos usan una base propia (estudia_e2e) y un puerto aparte: nunca tocan los datos de desarrollo.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: { baseURL: "http://localhost:8100", locale: "es-CO", timezoneId: "America/Bogota", trace: "retain-on-failure" },
  webServer: { command: "./e2e/levantar.sh", url: "http://localhost:8100/panel", reuseExistingServer: false, timeout: 120_000 },
});
