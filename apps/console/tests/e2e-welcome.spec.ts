import { expect, test } from "@playwright/test";

test("public welcome offers keyboard entry and a pausable decorative ticker", async ({
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
  await page.getByRole("button", { name: "Pause animations" }).click();
  await expect.poll(running).toBe(0);
  await page.getByRole("button", { name: "Enable animations" }).click();
  await expect.poll(running).toBeGreaterThan(0);
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
