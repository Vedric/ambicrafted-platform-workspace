import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

// One ephemeral password shared with the disposable server and its test workers.
process.env.PLATFORM_E2E_PASSWORD ||= randomBytes(36).toString("base64url");
process.env.PLATFORM_E2E_KEY ||= randomBytes(36).toString("base64url");
const uvUtilisateur = `${process.env.HOME}/.local/bin/uv`;
const uv =
  process.env.PLATFORM_TEST_UV ||
  (existsSync(uvUtilisateur) ? uvUtilisateur : "uv");
const executable = "'" + uv.replaceAll("'", "'\"'\"'") + "'";

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  outputDir: "test-results",
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8789",
    locale: "fr-FR",
    timezoneId: "Europe/Paris",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    serviceWorkers: "block",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["iPhone 13"], browserName: "chromium" },
    },
  ],
  webServer: {
    command: `${executable} run --locked --project ../control-api python tests/server.py`,
    url: "http://127.0.0.1:8789/api/ping",
    timeout: 30_000,
    reuseExistingServer: false,
    env: {
      PLATFORM_E2E_PASSWORD: process.env.PLATFORM_E2E_PASSWORD,
      PLATFORM_E2E_KEY: process.env.PLATFORM_E2E_KEY,
    },
    stdout: "ignore",
    stderr: "pipe",
  },
});
