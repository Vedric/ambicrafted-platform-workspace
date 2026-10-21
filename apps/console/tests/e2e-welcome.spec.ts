import { expect, test } from "@playwright/test";

test("public welcome offers keyboard entry and an automatically animated decorative ticker", async ({
  page,
}) => {
  await page.goto("/welcome");
  await expect(
    page.getByRole("heading", { name: /Intelligence/ }),
  ).toBeVisible();
  const enter = page.getByRole("link", {
    name: "Enter workspace",
    exact: true,
  });
  await enter.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#workspace-access")).toBeFocused();
  await expect(page.getByLabel("Welcome back")).toBeEditable();
  const ticker = page.locator(".landing-marquee");
  await expect(ticker).toHaveAttribute("aria-hidden", "true");
  const running = () =>
    ticker.evaluate(
      (element) =>
        element
          .getAnimations({ subtree: true })
          .filter(
            (animation) =>
              animation.playState === "running" &&
              animation.effect?.getComputedTiming().endTime === Infinity,
          ).length,
    );
  await expect.poll(running).toBeGreaterThan(0);
  // Decorative motion follows live accessibility preferences.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(running).toBe(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect.poll(running).toBeGreaterThan(0);
  await expect(page.locator(".motion-control")).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(running).toBe(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("an authenticated operator can revisit the welcome page and rejoin without signing in again", async ({
  page,
}) => {
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
  const menu = page.getByRole("button", { name: "Open navigation" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("link", { name: "Ambicrafted home", exact: true })
    .filter({ visible: true })
    .click();
  await expect(page).toHaveURL(/\/welcome$/);
  await expect(
    page.getByRole("heading", { name: /Intelligence/ }),
  ).toBeVisible();
  await expect(page.getByLabel("Welcome back")).not.toBeVisible();
  await page
    .getByRole("link", { name: "Rejoin workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Your intelligence, in motion.",
      exact: true,
    }),
  ).toBeVisible();
});

for (const language of ["en", "fr"])
  test(`password entry from welcome opens the workspace directly (${language})`, async ({
    page,
  }) => {
    await page.addInitScript((language) => {
      localStorage.setItem("ambicrafted-language", language);
      localStorage.setItem("ambicrafted-welcome-audio", "off");
    }, language);
    await page.goto("/welcome");
    await page
      .locator("#connexion-privee")
      .fill(process.env.PLATFORM_E2E_PASSWORD!);
    await page.locator("#workspace-access form button[type=submit]").click();
    await expect(page).toHaveURL("http://127.0.0.1:8789/");
    await expect(page.locator(".insights")).toBeVisible();
    const session = await page.request.get("/api/auth");
    expect((await session.json()).connecte).toBe(true);
    // Password entry keeps the same session/CSRF path as the CLI one-use ticket.
    await page.goto("/assistant");
    await expect(page.locator(".chat-panel textarea")).toBeEditable();
  });

test("a CLI session without a password points to browser setup without weakening authentication", async ({
  page,
}) => {
  await page.route("**/api/auth", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, mot_de_passe: false } });
  });
  await page.goto("/welcome");
  await expect(
    page.getByText(
      "Open your workspace once from the CLI, then choose a password in Settings. After that, sign in directly here.",
    ),
  ).toBeVisible();
  await expect(page.locator("#connexion-privee")).toHaveCount(0);
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  await page.goto("/#session=" + (await response.json()).ticket);
  await page.locator(".browser-access-notice a").click();
  await expect(page).toHaveURL(/\/parametres#browser-access$/);
  await expect(page.locator("#browser-access")).toBeInViewport();
  await expect(page.locator("#browser-access input").first()).toBeEditable();
});
