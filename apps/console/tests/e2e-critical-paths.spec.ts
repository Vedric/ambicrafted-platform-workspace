import { expect, test, type Page } from "@playwright/test";

// Cross-engine acceptance: the API/session/SQLite/process wiring is real;
// inference remains the explicit synthetic replacement in server.py.
const errors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const collected: string[] = [];
  errors.set(page, collected);
  page.on("pageerror", (error) => collected.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem("ambicrafted-welcome-audio", "off");
    localStorage.setItem("ambicrafted-language", "en");
  });
});
test.afterEach(async ({ page }) => {
  expect(
    errors.get(page),
    "No uncaught exception in a critical journey",
  ).toEqual([]);
});

async function login(page: Page, route = "/") {
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.status()).toBe(200);
  const { ticket } = await response.json();
  await page.goto(route + "#session=" + ticket, {
    waitUntil: "domcontentloaded",
  });
  await expect
    .poll(
      async () => (await (await page.request.get("/api/auth")).json()).connecte,
    )
    .toBe(true);
  await expect(page).toHaveURL("http://127.0.0.1:8789" + route);
}

async function create(page: Page, title: string, slow = false) {
  // Follow the real SPA control. Repeated document-level goto calls during
  // query invalidation abort an unloading page's fetches in WebKit.
  await page.getByRole("link", { name: "New analysis", exact: true }).click();
  await page.getByLabel(/Analysis title/).fill(title);
  await page
    .getByLabel(/Alert & context/)
    .fill(
      slow
        ? "SLOW synthetic cancellation fixture."
        : "PostgreSQL synthetic connection rejection.",
    );
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  return page.url().split("/").at(-1)!;
}

async function remove(page: Page) {
  await page
    .getByRole("button", { name: "Delete analysis", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Delete analysis" })
    .getByRole("button", { name: "Delete analysis", exact: true })
    .click();
  await expect(page).toHaveURL(/\/analyses$/);
}

test("critical: password entry, cookie boundary, locale, theme and logout", async ({
  page,
}) => {
  await page.goto("/welcome", { waitUntil: "domcontentloaded" });
  expect((await page.request.get("/api/analyses")).status()).toBe(401);
  await page
    .getByLabel("Welcome back")
    .fill(process.env.PLATFORM_E2E_PASSWORD!);
  await page.getByLabel("Welcome back").press("Enter");
  await expect(
    page.getByRole("heading", {
      name: "Your intelligence, in motion.",
      exact: true,
    }),
  ).toBeVisible();
  const cookie = (await page.context().cookies()).find(
    (entry) => entry.name === "ambicrafted_session",
  );
  expect(cookie).toMatchObject({ httpOnly: true, sameSite: "Strict" });
  const csrfMissing = await page.evaluate(
    async () =>
      (
        await fetch("/api/analyses", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            titre: "Must not exist",
            alerte: "Synthetic denied mutation",
          }),
        })
      ).status,
  );
  expect(csrfMissing).toBe(403);
  await page.goto("/parametres", { waitUntil: "domcontentloaded" });
  await expect(
    page.getByRole("heading", { name: "Settings & help", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page
    .locator("select[aria-label]")
    .filter({ has: page.locator('option[value="fr"]') })
    .first()
    .selectOption("fr");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(
    page.getByRole("heading", { name: "Paramètres et aide", exact: true }),
  ).toBeVisible();
  await page
    .locator("select[aria-label]")
    .filter({ has: page.locator('option[value="en"]') })
    .first()
    .selectOption("en");
  for (const width of [360, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      `No settings overflow at ${width}px`,
    ).toBe(true);
  }
  await page
    .getByRole("button", { name: "Sign out", exact: true })
    .filter({ visible: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Intelligence/ }),
  ).toBeVisible();
  expect((await page.request.get("/api/analyses")).status()).toBe(401);
});

test("critical: native scope and runbook filename constraints reject invalid input", async ({
  page,
}) => {
  // Exercise the browser's pattern validation, not a copy of the expression.
  // HTML patterns use Unicode v mode, where a literal hyphen must be escaped.
  await login(page, "/memoire");
  const scope = page.getByLabel("Memory scope", { exact: true });
  for (const value of ["a", "team-platform_2", "0" + "a".repeat(63)]) {
    await scope.fill(value);
    expect(
      await scope.evaluate((element: HTMLInputElement) =>
        element.checkValidity(),
      ),
      `Accept valid memory scope: ${value}`,
    ).toBe(true);
  }
  for (const value of [
    "Team",
    "-team",
    "_team",
    "team/client",
    "team space",
    "équipe",
  ]) {
    await scope.fill(value);
    expect(
      await scope.evaluate(
        (element: HTMLInputElement) => element.validity.patternMismatch,
      ),
      `Reject invalid memory scope: ${value}`,
    ).toBe(true);
  }

  const menu = page.getByRole("button", { name: "Open navigation" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("link", { name: "Runbooks", exact: true })
    .filter({ visible: true })
    .click();
  await page.getByRole("link", { name: "New runbook", exact: true }).click();
  const filename = page.getByLabel("File name", { exact: true });
  for (const value of ["a.md", "Team-platform_2.md"]) {
    await filename.fill(value);
    expect(
      await filename.evaluate((element: HTMLInputElement) =>
        element.checkValidity(),
      ),
      `Accept valid runbook filename: ${value}`,
    ).toBe(true);
  }
  for (const value of [
    "../runbook.md",
    "dir/runbook.md",
    "runbook.txt",
    "runbook.MD",
    "-runbook.md",
  ]) {
    await filename.fill(value);
    expect(
      await filename.evaluate(
        (element: HTMLInputElement) => element.validity.patternMismatch,
      ),
      `Reject invalid runbook filename: ${value}`,
    ).toBe(true);
  }
});

test("critical: human approval, portable export, refusal and cancellation", async ({
  page,
}, info) => {
  await login(page, "/analyses");
  const id = await create(page, "Cross-engine approval " + info.project.name);
  await expect(page.getByText("Ready for your review")).toBeVisible();
  await expect(
    page.getByText("Pattern estimated as familiar; cause not established.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Synthetic test data.", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Triage does not authorize intervention.", {
      exact: false,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Approve proposal", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Approve proposal" });
  const confirm = dialog.getByRole("button", {
    name: "Approve proposal",
    exact: true,
  });
  await expect(confirm).toBeDisabled();
  await dialog.getByRole("checkbox").check();
  await confirm.click();
  await expect(
    page.getByRole("heading", { name: "Completed diagnosis", exact: true }),
  ).toBeVisible();
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "JSON", exact: true }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe(`analyse-${id}.json`);
  const chunks: Buffer[] = [];
  const stream = await download.createReadStream();
  for await (const chunk of stream!) chunks.push(chunk);
  expect(JSON.parse(Buffer.concat(chunks).toString()).statut).toBe("complet");
  await remove(page);
  await create(page, "Cross-engine refusal " + info.project.name);
  await page
    .getByRole("button", { name: "Reject proposal", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Reject proposal" })
    .getByRole("button", { name: "Reject proposal", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Proposal rejected", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Completed diagnosis", exact: true }),
  ).toHaveCount(0);
  await remove(page);
  await create(page, "Cross-engine cancellation " + info.project.name, true);
  await page.getByRole("button", { name: "Cancel run", exact: true }).click();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await remove(page);
  // Prove the serial worker actually accepts fresh work after cancellation.
  // The synthetic engine releases its sleep at the next cooperative boundary.
  await create(page, "Cross-engine recovery " + info.project.name);
  await expect(page.getByText("Ready for your review")).toBeVisible();
  await remove(page);
});

test("critical: streamed dialogue, document grounding choice and persisted history", async ({
  page,
}, info) => {
  await login(page, "/assistant");
  const title = "Cross-engine conversation " + info.project.name;
  const input = page.getByLabel("Your message");
  await page.locator('input[type="file"]').setInputFiles({
    name: "synthetic-metrics.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("service,p95_ms\nsynthetic,125\n"),
  });
  await expect(
    page.getByRole("checkbox", { name: "synthetic-metrics.csv" }),
  ).toBeChecked();
  await input.fill(title);
  const submission = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      /\/conversations\/[^/]+\/messages$/.test(request.url()),
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  expect((await submission).postDataJSON().pieces).toHaveLength(1);
  await expect(page.locator(".chat-messages")).toContainText("Synthetic reply");
  await expect(input).toBeEditable();
  await page.reload({ waitUntil: "domcontentloaded" });
  await page
    .getByRole("button", { name: "Conversation history", exact: true })
    .click();
  await page.getByLabel("Search conversations").fill(title);
  await page
    .locator(".history-list")
    .getByRole("button", { name: new RegExp(`^${title}`) })
    .click();
  await expect(page.locator(".chat-messages")).toContainText(title);
  await expect(
    page.getByRole("checkbox", { name: "synthetic-metrics.csv" }),
  ).not.toBeChecked();
  await page
    .getByRole("button", { name: "Conversation history", exact: true })
    .click();
  await page
    .getByRole("button", { name: `Delete conversation ${title}`, exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete conversation", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(input).toHaveValue("");
});
