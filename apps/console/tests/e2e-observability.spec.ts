import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("ambicrafted-welcome-audio", "off");
    localStorage.setItem("ambicrafted-language", "en");
  });
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  // Establish authentication before loading the measured document.
  const exchange = await page.request.post("/api/auth/connexion", {
    headers: { Origin: "http://127.0.0.1:8789" },
    data: { ticket: (await response.json()).ticket },
  });
  expect(exchange.ok()).toBe(true);
});

test("operational views fill the viewport in both themes and remain accessible", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/observabilite", { waitUntil: "domcontentloaded" });
  await expect(
    page.getByRole("heading", { name: "Observability", exact: true }),
  ).toBeVisible();
  const cards = page.locator(".monitoring-card");
  await expect(cards).toHaveCount(6);
  await expect(page.locator(".targets")).toContainText("Collecting");
  for (const theme of ["dark", "light"] as const) {
    if (theme === "light")
      await page.getByRole("button", { name: "Switch to light theme" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await cards.last().scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    const boxes = await cards.evaluateAll((nodes) =>
      nodes.map((n) => ({
        w: n.getBoundingClientRect().width,
        h: n.getBoundingClientRect().height,
      })),
    );
    expect(
      Math.max(...boxes.map((b) => b.w)) - Math.min(...boxes.map((b) => b.w)),
    ).toBeLessThan(2);
    const axe = await new AxeBuilder({ page })
      .include(".observability-page")
      .analyze();
    expect(axe.violations).toEqual([]);
    // Capture from the document top so fixed mobile navigation remains in its
    // actual viewport position in the full-page image.
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await page.screenshot({
      path: info.outputPath(`observability-${theme}.png`),
      fullPage: true,
      animations: "disabled",
    });
  }
  await page
    .locator("select[aria-label]")
    .filter({ has: page.locator('option[value="fr"]') })
    .selectOption("fr");
  await expect(cards.first()).toHaveAttribute(
    "href",
    "http://localhost:3000/d/plateforme-slo-fr",
  );
  await expect(
    page.getByRole("heading", { name: "Fiabilité, expérience et traces" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("authenticated first-visible-period metrics use the real CSRF endpoint only once", async ({
  page,
}) => {
  const payloads: unknown[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/telemetrie/navigation"))
      payloads.push(request.postDataJSON());
  });
  await page.goto("/observabilite", { waitUntil: "networkidle" });
  await page
    .getByRole("heading", { name: "Observability", exact: true })
    .click();
  // LCP finalization runs at idle after this trusted interaction.
  await page.waitForTimeout(1100);
  const response = page.waitForResponse((r) =>
    r.url().endsWith("/api/telemetrie/navigation"),
  );
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
  });
  expect((await response).status()).toBe(204);
  expect(payloads).toHaveLength(1);
  const payload = payloads[0] as {
    samples: { metric: string; route: string; value: number }[];
  };
  expect(Object.keys(payload)).toEqual(["samples"]);
  expect(payload.samples.length).toBeGreaterThan(0);
  expect(payload.samples.length).toBeLessThanOrEqual(3);
  expect(new Set(payload.samples.map((s) => s.metric)).size).toBe(
    payload.samples.length,
  );
  for (const sample of payload.samples) {
    expect(Object.keys(sample).sort()).toEqual(["metric", "route", "value"]);
    expect(sample.route).toBe("observability");
    expect(Number.isFinite(sample.value)).toBe(true);
  }
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    window.dispatchEvent(
      new PageTransitionEvent("pageshow", { persisted: true }),
    );
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
  });
  await page.waitForTimeout(100);
  expect(payloads).toHaveLength(1);
});
