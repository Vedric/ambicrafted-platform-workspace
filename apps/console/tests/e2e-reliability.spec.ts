import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  const ticket = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(ticket.ok()).toBe(true);
  await page.goto("/assistant#session=" + (await ticket.json()).ticket);
  await expect(page.getByLabel("Your message")).toBeEditable();
}

async function revokeSession(page: Page, discovery = false) {
  const session = await (await page.request.get("/api/auth")).json();
  const revoked = await page.request.post("/api/auth/deconnexion", {
    headers: {
      Origin: new URL(page.url()).origin,
      "X-CSRF-Token": session.csrf,
    },
    data: {},
  });
  expect(revoked.ok()).toBe(true);
  if (discovery) {
    // The public guide needs no protected data. Its real SPA navigation
    // revalidates the session even while the previous query is still fresh.
    const response = page.waitForResponse(
      (value) => new URL(value.url()).pathname === "/api/auth",
    );
    const menu = page.getByRole("button", { name: "Open navigation" });
    if (await menu.isVisible()) await menu.click();
    await page.locator('a[href="/guide"]').filter({ visible: true }).click();
    const discovered = await response;
    expect(discovered.status()).toBe(200);
    expect((await discovered.json()).connecte).toBe(false);
    await expect(page.locator(".public-guide")).toBeVisible();
  } else {
    expect((await page.request.get("/api/conversations")).status()).toBe(401);
    // Let an ordinary real API fetch notify the active application of revocation.
    await page
      .getByRole("button", { name: "Conversation history", exact: true })
      .click();
  }
  await expect(page.getByLabel("Your message")).toHaveCount(0);
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test("lost completion retries the exact committed operation without duplicating history", async ({
  page,
}) => {
  await login(page);
  const operations: string[] = [];
  let conversation = "";
  await page.route("**/api/conversations/*/messages", async (route) => {
    operations.push(route.request().postDataJSON().operation_id);
    conversation = new URL(route.request().url()).pathname.split("/")[3];
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    if (operations.length === 1) await route.abort("connectionreset");
    else await route.fulfill({ response });
  });
  const message = `Synthetic uncertain completion ${test.info().project.name}`;
  await page.getByLabel("Your message").fill(message);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByLabel("Your message")).toHaveValue(message);
  await expect(
    page.getByRole("button", { name: "Send", exact: true }),
  ).toBeEnabled();
  await expect(page.locator(".chat-messages")).not.toContainText(
    "Synthetic reply",
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".chat-messages")).toContainText("Synthetic reply");
  expect(operations).toHaveLength(2);
  expect(operations[1]).toBe(operations[0]);
  const saved = await (
    await page.request.get(`/api/conversations/${conversation}`)
  ).json();
  expect(saved.total_messages).toBe(2);
  expect(
    saved.messages.map((item: { operation_id: string }) => item.operation_id),
  ).toEqual([operations[0], operations[0]]);
});

test("revocation discards a late streamed completion and private workspace", async ({
  page,
}) => {
  await login(page);
  const ready = deferred(),
    release = deferred(),
    released = deferred();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/conversations/*/messages", async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    ready.resolve();
    await release.promise;
    try {
      await route.fulfill({ response });
    } finally {
      released.resolve();
    }
  });
  try {
    await page
      .getByLabel("Your message")
      .fill("Synthetic late private completion");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await ready.promise;
    await revokeSession(page);
    release.resolve();
    await released.promise;
    await expect(page.locator(".chat-messages")).toHaveCount(0);
    await expect(
      page.getByText("Synthetic late private completion", { exact: true }),
    ).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    release.resolve();
  }
});

test("revocation cancels an in-flight authenticated export before any stale download", async ({
  page,
}) => {
  await login(page);
  await page.getByLabel("Response format").selectOption("report");
  await page
    .getByLabel("Your message")
    .fill("Synthetic report for revoked export");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".artifact-card")).toHaveCount(1);
  const downloads: string[] = [];
  page.on("download", (download) =>
    downloads.push(download.suggestedFilename()),
  );
  const ready = deferred(),
    release = deferred(),
    released = deferred();
  await page.route("**/artefacts/*/export?format=json", async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    ready.resolve();
    await release.promise;
    try {
      await route.fulfill({ response });
    } finally {
      released.resolve();
    }
  });
  try {
    await page
      .getByRole("button", { name: "Download JSON", exact: true })
      .click();
    await ready.promise;
    await revokeSession(page);
    release.resolve();
    await released.promise;
    // Observe the browser event after its network/DOM work settles, including
    // any incorrectly queued download from the now-unmounted document card.
    await page.waitForTimeout(300);
    expect(downloads).toEqual([]);
  } finally {
    release.resolve();
  }
});

for (const discovery of [false, true])
  test(`revocation through ${discovery ? "session discovery" : "HTTP401"} cancels native PNG before any stale download`, async ({
    page,
  }) => {
    await page.addInitScript(() => {
      const native = HTMLCanvasElement.prototype.toBlob;
      HTMLCanvasElement.prototype.toBlob = function (callback, type, quality) {
        native.call(
          this,
          (blob) => {
            const pending = window as typeof window & {
              completeSyntheticExport?: () => void;
            };
            pending.completeSyntheticExport = () => callback(blob);
          },
          type,
          quality,
        );
      };
    });
    await login(page);
    await page.getByLabel("Response format").selectOption("diagram");
    await page
      .getByLabel("Your message")
      .fill("Synthetic diagram for revoked PNG export");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const card = page.locator(".artifact-card");
    await expect(card).toHaveCount(1);
    await card.scrollIntoViewIfNeeded();
    await expect(card.locator("svg.document-diagram")).toBeAttached();
    const downloads: string[] = [];
    page.on("download", (download) =>
      downloads.push(download.suggestedFilename()),
    );
    await card
      .getByRole("button", { name: "Download PNG", exact: true })
      .click();
    await page.waitForFunction(() => "completeSyntheticExport" in window);
    const unauthorized: string[] = [];
    page.on("response", (response) => {
      if (response.status() === 401) unauthorized.push(response.url());
    });
    await revokeSession(page, discovery);
    if (discovery) expect(unauthorized).toEqual([]);
    await page.evaluate(() => {
      const pending = window as typeof window & {
        completeSyntheticExport?: () => void;
      };
      pending.completeSyntheticExport?.();
      delete pending.completeSyntheticExport;
    });
    await page.waitForTimeout(300);
    expect(downloads).toEqual([]);
  });

test("rapid double submission creates one operation and one persisted pair", async ({
  page,
}) => {
  await login(page);
  const ready = deferred(),
    release = deferred();
  const operations: string[] = [];
  let conversation = "";
  await page.route("**/api/conversations/*/messages", async (route) => {
    operations.push(route.request().postDataJSON().operation_id);
    conversation = new URL(route.request().url()).pathname.split("/")[3];
    const response = await route.fetch();
    ready.resolve();
    await release.promise;
    await route.fulfill({ response });
  });
  try {
    await page
      .getByLabel("Your message")
      .fill("Synthetic rapid double submission");
    await page.getByRole("button", { name: "Send", exact: true }).dblclick();
    await ready.promise;
    expect(operations).toHaveLength(1);
    release.resolve();
    await expect(page.locator(".chat-messages")).toContainText(
      "Synthetic reply",
    );
    const saved = await (
      await page.request.get(`/api/conversations/${conversation}`)
    ).json();
    expect(saved.total_messages).toBe(2);
    expect(operations).toHaveLength(1);
  } finally {
    release.resolve();
  }
});
