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
const externalRequests = new Set();
const blockedRequests = [];
try {
  for (const theme of ["dark", "light"]) {
    for (const [device, viewport] of [
      ["desktop", { width: 1600, height: 1000 }],
      ["mobile", { width: 430, height: 932 }],
    ]) {
      const context = await browser.newContext({
        viewport,
        colorScheme: theme,
      });
      // No requests can leave the disposable fixture, including link prefetch.
      await context.route("**/*", async (route) => {
        if (new URL(route.request().url()).origin !== origin) {
          const blocked = new URL(route.request().url());
          externalRequests.add(blocked.origin);
          blockedRequests.push({
            origin: blocked.origin,
            path: blocked.pathname,
            resourceType: route.request().resourceType(),
          });
          writeFileSync(
            join(input.output, "browser-blocked-requests.json"),
            JSON.stringify(blockedRequests, null, 2),
          );
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
        const key = `${dashboard.uid}-${theme}-${device}`;
        try {
          const url = new URL(input.base + dashboard.url);
          url.searchParams.set("theme", theme);
          url.searchParams.set("from", "now-5m");
          url.searchParams.set("to", "now");
          url.searchParams.set("refresh", "");
          const response = await page.goto(url.href, {
            waitUntil: "domcontentloaded",
          });
          assert(response?.ok(), key);
          const panels = page.locator(
            '[data-testid="data-testid panel content"]',
          );
          await panels.first().waitFor({ state: "visible", timeout: 30000 });
          await page.waitForFunction(
            (count) =>
              document.querySelectorAll(
                '[data-testid="data-testid panel content"]',
              ).length === count,
            dashboard.content_panels,
          );
          assert.equal(
            await page
              .getByText("If you're seeing this Grafana has failed")
              .count(),
            0,
          );
          // Scroll through lazy panels before checking geometry and taking evidence.
          for (let index = 0; index < (await panels.count()); index++) {
            await panels.nth(index).scrollIntoViewIfNeeded();
          }
          await panels.first().scrollIntoViewIfNeeded();
          await page.waitForTimeout(300);
          const geometry = await panels.evaluateAll((nodes) => {
            const boxes = nodes.map((node) => {
              const box = node.getBoundingClientRect();
              return { x: box.x, y: box.y, w: box.width, h: box.height };
            });
            const overlaps = [];
            for (let i = 0; i < boxes.length; i++) {
              for (let j = i + 1; j < boxes.length; j++) {
                const a = boxes[i],
                  b = boxes[j];
                if (
                  Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 1 &&
                  Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 1
                )
                  overlaps.push([i, j]);
              }
            }
            return {
              overlaps,
              clipped: boxes.filter(
                (box) =>
                  box.x < -1 ||
                  box.x + box.w > innerWidth + 1 ||
                  box.w < 100 ||
                  box.h < 20,
              ),
              overflow: document.documentElement.scrollWidth > innerWidth + 1,
              background: getComputedStyle(document.body).backgroundColor,
              themeClass: `${document.documentElement.className} ${document.body.className}`,
            };
          });
          assert.deepEqual(geometry.overlaps, [], key + " panels overlap");
          assert.deepEqual(geometry.clipped, [], key + " panels clipped");
          assert.equal(geometry.overflow, false, key + " horizontal overflow");
          assert(
            geometry.themeClass.includes(`theme-${theme}`),
            key + " wrong theme",
          );
          assert.equal(errors.length, 0, JSON.stringify(errors));
          await page.screenshot({
            path: join(input.output, `${key}.png`),
            fullPage: true,
          });
          checks.push({
            uid: dashboard.uid,
            theme,
            device,
            renderedPanels: await panels.count(),
            geometry,
          });
        } catch (error) {
          await page.screenshot({
            path: join(input.output, `${key}-failure.png`),
            fullPage: true,
          });
          writeFileSync(
            join(input.output, `${key}-failure.json`),
            JSON.stringify(
              {
                error: String(error),
                url: page.url(),
                text: await page.locator("body").innerText(),
                errors,
              },
              null,
              2,
            ),
          );
          throw error;
        }
      }
      await context.close();
    }
  }
  writeFileSync(
    join(input.output, "browser-render-checks.json"),
    JSON.stringify(checks, null, 2),
  );
  assert.equal(
    externalRequests.size,
    0,
    "Unexpected requests outside the fixture",
  );
} finally {
  await browser.close();
}
process.stdout.write(
  JSON.stringify({
    engine: "chromium",
    scope: `${input.dashboards.length * 4} synthetic dashboard/theme/viewport variants; panel geometry and JavaScript checks`,
    externalRequests: [...externalRequests],
    dashboards: checks,
  }),
);
