// Invoked by qualifier.py while the disposable services are running.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

const input = JSON.parse(readFileSync(0, "utf8"));
const require = createRequire(join(input.root, "apps/console/package.json"));
const { chromium } = require("playwright");
const origin = new URL(input.base).origin;
const authorization = `Basic ${Buffer.from(`admin:${input.password}`).toString("base64")}`;
const browser = await chromium.launch({ headless: true });
const checks = [];
try {
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    reducedMotion: "reduce",
  });
  // Keep browser-side traffic inside the same synthetic fixture as well.
  await context.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      await route.abort();
      return;
    }
    await route.continue({
      headers: { ...route.request().headers(), authorization },
    });
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const dashboard of input.dashboards) {
    const response = await page.goto(input.base + dashboard.url, {
      waitUntil: "domcontentloaded",
    });
    assert(response?.ok(), dashboard.uid);
    const panels = page.locator('[data-testid="data-testid panel content"]');
    try {
      await panels.first().waitFor({ state: "visible", timeout: 30000 });
    } catch (error) {
      await page.screenshot({
        path: join(input.output, "browser-failure.png"),
        fullPage: true,
      });
      writeFileSync(
        join(input.output, "browser-failure.json"),
        JSON.stringify({
          url: page.url(),
          text: await page.locator("body").innerText(),
          testids: await page
            .locator("[data-testid]")
            .evaluateAll((nodes) =>
              nodes.map((node) => node.getAttribute("data-testid")),
            ),
          errors,
        }),
      );
      throw error;
    }
    assert.equal(
      await page.getByText("If you're seeing this Grafana has failed").count(),
      0,
    );
    assert.equal(await panels.count(), dashboard.content_panels, dashboard.uid);
    await panels.last().scrollIntoViewIfNeeded();
    await panels.first().scrollIntoViewIfNeeded();
    await page.screenshot({
      path: join(input.output, `${dashboard.uid}.png`),
      fullPage: true,
    });
    checks.push({ uid: dashboard.uid, renderedPanels: await panels.count() });
  }
  assert.equal(errors.length, 0, JSON.stringify(errors));
  await context.close();
} finally {
  await browser.close();
}
process.stdout.write(
  JSON.stringify({
    engine: "chromium",
    scope: "synthetic dashboards; screenshot and JavaScript error checks",
    dashboards: checks,
  }),
);
