import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true, routesDirectory: "./src/pages", generatedRouteTree: "./src/app/routeTree.gen.ts" }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    // The default `forks` pool spawns one OS process per test file; on
    // this machine that intermittently times out starting a worker
    // (a different file fails each run — a pool-startup flake, not a
    // test bug). `threads` runs workers in-process via worker_threads
    // instead, which starts fast and reliably here.
    pool: "threads",
    // Default is 5000ms. The real-router integration tests
    // (src/test/routing.test.tsx) chain multiple async `beforeLoad`
    // hops, an MSW-backed fetch, and a full AppShell render per case —
    // comfortably under 5s in isolation, but this machine's full-suite
    // run (now 16+ files under one `threads` pool) has shown enough
    // contention to occasionally miss a smaller window. Sized generously
    // rather than shaving it to the observed minimum.
    testTimeout: 30_000,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      exclude: ["src/app/routeTree.gen.ts", "src/test/**"],
    },
  },
});
