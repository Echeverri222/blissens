import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// El panel se sirve desde FastAPI en /panel (mismo origen). `vite` solo se usa como opción de desarrollo con API redirigida.
export default defineConfig({
  base: "/panel/",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  server: { port: 5173, proxy: { "/api": "http://localhost:8000", "/simulador": "http://localhost:8000" } },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/pruebas/preparar.ts"], css: false, exclude: ["e2e/**", "node_modules/**"] },
});
