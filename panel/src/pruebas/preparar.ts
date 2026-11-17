import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { servidor } from "./servidor";

// El `fetch` de Node no acepta rutas relativas; el navegador sí.
const fetchOriginal = globalThis.fetch;
globalThis.fetch = ((u: RequestInfo | URL, i?: RequestInit) =>
  fetchOriginal(typeof u === "string" && u.startsWith("/") ? `http://localhost${u}` : u, i)) as typeof fetch;

beforeAll(() => servidor.listen({ onUnhandledFrame: "error" }));
afterEach(() => { cleanup(); servidor.resetHandlers(); });
afterAll(() => servidor.close());
