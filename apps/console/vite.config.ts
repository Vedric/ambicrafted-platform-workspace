import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", proxy: { "/api": "http://127.0.0.1:8787" } },
  // Keep fonts as same-origin files: the runtime CSP deliberately disallows data: fonts.
  build: { sourcemap: false, assetsInlineLimit: 0, chunkSizeWarningLimit: 700 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.ts?(x)"],
  },
});
