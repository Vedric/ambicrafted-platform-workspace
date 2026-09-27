import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const browserErrors = new WeakMap<Page, string[]>();
test.beforeEach(({ page }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(({ page }) => expect(browserErrors.get(page)).toEqual([]));

async function login(page: Page) {
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  const { ticket } = await response.json();
  await page.goto("/#session=" + ticket);
  await expect(
    page.getByRole("heading", {
      name: "Your intelligence, in motion.",
      exact: true,
    }),
  ).toBeVisible();
}

async function accessible(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.allSettled(
      document
        .getAnimations()
        .filter((animation) =>
          Number.isFinite(animation.effect?.getComputedTiming().endTime),
        )
        .map((animation) => animation.finished),
    );
  });
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    result.violations.map(({ id, nodes }) => ({
      id,
      targets: nodes.map((node) => node.target),
    })),
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}

test("KPI charts expose precise data, keyboard inspection and translated labels", async ({
  page,
}) => {
  await page.route("**/api/vue-ensemble", (route) =>
    route.fulfill({
      json: {
        total: 105,
        statuts: {
          complet: 70,
          en_attente_humain: 20,
          erreur: 10,
          future_state: 5,
        },
        activite: Array.from({ length: 14 }, (_, index) => ({
          date: "2026-09-" + String(index + 14),
          total: index + 1,
        })),
        sante: {
          ok: false,
          services: [
            { id: "litellm", nom: "Gateway", ok: true, latence_ms: 8 },
            { id: "qdrant", nom: "Store", ok: false, latence_ms: 3000 },
          ],
          modeles: [],
          index: {},
        },
        runbooks: 2,
        journal: [],
        version: "synthetic",
      },
    }),
  );
  await login(page);
  const activity = page.getByRole("region", { name: "Created runs" });
  await expect(activity.getByText("105", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "7 days", exact: true }).click();
  await expect(activity.getByText("77", { exact: true })).toBeVisible();
  const slider = page.getByRole("slider", { name: "Inspect a day" });
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(slider).toHaveAttribute("aria-valuetext", "Sep 21, 2026: 8");
  await page.getByText("View chart data", { exact: true }).click();
  await expect(
    page.getByRole("table", { name: "Created runs" }).getByRole("row"),
  ).toHaveCount(8);
  const services = page.getByRole("region", { name: "Service response" });
  await expect(
    services.getByText("1 of 2 service checks passed"),
  ).toBeVisible();
  await expect(services.getByText("Probe failed")).toBeVisible();
  await expect(services).not.toContainText("3000");
  await accessible(page);
  await page.getByLabel("Interface language").selectOption("fr");
  await expect(
    page.getByRole("region", { name: "États des exécutions" }),
  ).toBeVisible();
  await expect(
    page.getByRole("slider", { name: "Examiner une journée" }),
  ).toHaveAttribute("aria-valuetext", "21 sept. 2026: 8");
  await accessible(page);
});

test("architecture journeys explain actual dependencies and keep unmeasured state explicit", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Explore the architecture" }).click();
  await expect(
    page.getByRole("heading", { name: "See how your intelligence connects." }),
  ).toBeInViewport();
  await expect(
    page.getByText(
      "Arrows explain dependencies, not live traffic. Animation never indicates an active task.",
    ),
  ).toBeVisible();
  const journeys = page.getByRole("group", { name: "Architecture journeys" });
  const nodes = page.locator(".architecture-node").filter({ visible: true });
  await nodes.filter({ hasText: "Human review" }).click();
  await expect(
    page.getByRole("complementary", { name: "Component details" }),
  ).toContainText("Approving a proposal does not run remediation.");
  await journeys.getByRole("button", { name: "Voice", exact: true }).click();
  await nodes.filter({ hasText: "Local speech" }).click();
  await expect(
    page.getByRole("complementary", { name: "Component details" }),
  ).toContainText("female voice locally");
  await journeys
    .getByRole("button", { name: "Knowledge", exact: true })
    .click();
  await nodes.filter({ hasText: "Vector memory" }).click();
  await expect(
    page.getByRole("complementary", { name: "Component details" }),
  ).toContainText("versioned alias");
  await journeys
    .getByRole("button", { name: "Telemetry", exact: true })
    .click();
  const database = nodes.filter({ hasText: "Gateway database" });
  await database.focus();
  await page.keyboard.press("Enter");
  const details = page.getByRole("complementary", {
    name: "Component details",
  });
  await expect(details).toContainText("No direct health probe");
  await expect(details).toContainText("PostgreSQL has no independent probe");
  await accessible(page);
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await accessible(page);
  await page.getByLabel("Interface language").selectOption("fr");
  await expect(
    page.getByRole("heading", {
      name: "Comprenez les connexions de votre IA.",
    }),
  ).toBeVisible();
  await accessible(page);
});

test("architecture health fails closed while its explanatory map remains usable", async ({
  page,
}) => {
  await page.route("**/api/sante", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Synthetic health failure" },
    }),
  );
  await login(page);
  await page.goto("/architecture");
  await expect(page.getByRole("status")).toContainText(
    "current availability is unknown",
  );
  await expect(page.locator(".architecture-health-grid .probe-up")).toHaveCount(
    0,
  );
  await expect(
    page.locator(".architecture-health-grid .probe-unknown"),
  ).toHaveCount(6);
  await page
    .getByRole("group", { name: "Architecture journeys" })
    .getByRole("button", { name: "Knowledge", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "From reviewed procedures to grounded retrieval",
    }),
  ).toBeVisible();
  await accessible(page);
});

test("scroll entrances run in both directions and respect pause and reduced motion", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const native = HTMLElement.prototype.animate;
    const entries: string[] = [];
    Object.assign(window, { __scrollEntries: entries });
    HTMLElement.prototype.animate = function (frames, options) {
      if (
        typeof options === "object" &&
        options.duration === 720 &&
        Array.isArray(frames)
      )
        entries.push(String(frames[0]?.transform));
      return native.call(this, frames, options);
    };
  });
  await login(page);
  const entries = () =>
    page.evaluate(
      () =>
        (window as unknown as { __scrollEntries: string[] }).__scrollEntries,
    );
  await expect.poll(entries).toContain("translateY(28px)");
  await page.evaluate(() =>
    scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: "instant",
    }),
  );
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(500);
  await page.waitForTimeout(100); // allow the native intersection observer to record exit
  await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
  await expect.poll(entries).toContain("translateY(-28px)");
  await page.getByRole("button", { name: "Pause animations" }).click();
  await expect(page.locator(".scroll-progress")).toHaveCount(0);
  const pausedCount = (await entries()).length;
  await page.evaluate(() =>
    scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: "instant",
    }),
  );
  await page.waitForTimeout(100);
  expect((await entries()).length).toBe(pausedCount);
  await page.getByRole("button", { name: "Enable animations" }).click();
  await expect(page.locator(".scroll-progress")).toHaveCount(1);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".scroll-progress")).toHaveCount(0);
  await expect(page.locator(".insights")).toBeVisible();
});
