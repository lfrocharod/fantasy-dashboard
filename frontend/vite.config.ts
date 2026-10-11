/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// The API runs on :8000 in development (`fantasy serve --reload`); in
// production FastAPI serves this build itself, so /api is always same-origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // the same "@/…" → src/ alias tsconfig declares, for the dev server and vitest
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { sourcemap: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
