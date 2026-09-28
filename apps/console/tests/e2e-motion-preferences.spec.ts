import { expect, test, type Page } from "@playwright/test";

async function open(page: Page, legacy = "enabled", route = "/welcome") {
  await page.addInitScript((value) => {
    localStorage.setItem("ambicrafted-welcome-audio", "off");
    localStorage.setItem("ambicrafted-motion", value);
  }, legacy);
  if (route === "/welcome") return page.goto(route);
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  await page.goto(route + "#session=" + (await response.json()).ticket);
}

async function coreState(page: Page) {
  return page
    .locator(".neural-core")
    .first()
    .evaluate(async (element) => {
      const animations = element.getAnimations({ subtree: true });
      await Promise.all(animations.map((animation) => animation.ready));
      return {
        running: animations.filter(
          (animation) =>
            animation.playState === "running" &&
            animation.effect?.getComputedTiming().endTime === Infinity,
        ).length,
        ring: getComputedStyle(element.querySelector(".track-one")!).transform,
      };
    });
}

test("the same explicit choice drives architecture flows and operator pause", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page, "enabled", "/architecture");
  const canvas = page.locator(".architecture-canvas");
  if (page.viewportSize()!.width <= 900) {
    // Phones use the accessible component list, not an invisible SVG flow.
    await expect(page.locator(".architecture-mobile-list")).toBeVisible();
    await expect(canvas).toBeHidden();
    await page.setViewportSize({ width: 1024, height: 900 });
  }
  await canvas.scrollIntoViewIfNeeded();
  await expect(canvas).toHaveAttribute("data-motion", "off");
  await page
    .getByRole("button", { name: "Enable animations", exact: true })
    .click();
  await canvas.scrollIntoViewIfNeeded();
  await expect(canvas).toHaveAttribute("data-motion", "on");
  const flow = page.locator(".architecture-flow").first();
  const offset = () =>
    flow.evaluate((element) => getComputedStyle(element).strokeDashoffset);
  const first = await offset();
  await expect.poll(offset).not.toBe(first);
  await expect(flow).toHaveCSS("animation-play-state", "running");
  await page
    .getByRole("button", { name: "Pause animations", exact: true })
    .click();
  await expect(canvas).toHaveAttribute("data-motion", "off");
  await expect
    .poll(() =>
      flow.evaluate(
        (element) =>
          element
            .getAnimations()
            .filter((animation) => animation.playState === "running").length,
      ),
    )
    .toBe(0);
});

test("the actual motion state is visible and Enable overrides device reduction across reloads", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page);
  const enable = page.getByRole("button", {
    name: "Enable animations",
    exact: true,
  });
  await expect(enable).toHaveText("Motion off");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "paused");
  await expect.poll(async () => (await coreState(page)).running).toBe(0);
  await enable.focus();
  await page.keyboard.press("Enter");
  const core = page.locator(".neural-core").first();
  await core.scrollIntoViewIfNeeded();
  await expect
    .poll(async () => (await coreState(page)).running)
    .toBeGreaterThanOrEqual(8);
  const before = await coreState(page);
  await expect
    .poll(async () => (await coreState(page)).ring)
    .not.toBe(before.ring);
  await expect(
    page.getByRole("button", { name: "Pause animations", exact: true }),
  ).toHaveText("Motion on");
  await page.reload();
  await core.scrollIntoViewIfNeeded();
  await expect(page.locator("html")).toHaveAttribute(
    "data-motion-mode",
    "full",
  );
  await expect
    .poll(async () => (await coreState(page)).running)
    .toBeGreaterThanOrEqual(8);
  await page
    .getByRole("button", { name: "Pause animations", exact: true })
    .click();
  await page.reload();
  await expect(enable).toHaveText("Motion off");
  await expect.poll(async () => (await coreState(page)).running).toBe(0);
  expect(errors).toEqual([]);
});

test("settings can restore automatic device behavior after an explicit override", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 320, height: 1000 });
  await open(page, "enabled", "/parametres");
  const setting = page.getByRole("combobox", {
    name: "Animation settings",
    exact: true,
  });
  await expect(setting).toHaveValue("system");
  await setting.selectOption("full");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "enabled");
  await expect(page.locator(".scroll-progress")).toHaveCSS("position", "fixed");
  await page.locator("#cli-settings").scrollIntoViewIfNeeded();
  await expect(page.locator(".scroll-progress")).toBeVisible();
  await setting.selectOption("system");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "paused");
  await expect(page.locator(".scroll-progress")).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(page.locator("html")).toHaveAttribute("data-motion", "enabled");
  await setting.selectOption("paused");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(page.locator("html")).toHaveAttribute("data-motion", "paused");
  await expect(setting).toHaveValue("paused");
  for (const language of ["fr", "en"]) {
    await page.locator(".topbar .language-selector").selectOption(language);
    await expect(page.locator(".topbar .motion-control")).toBeInViewport();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("a previous pause is recoverable and the choice reaches other open tabs", async ({
  page,
  context,
}) => {
  await open(page, "paused");
  await expect(
    page.getByRole("button", { name: "Enable animations", exact: true }),
  ).toHaveText("Motion off");
  const other = await context.newPage();
  await other.goto("/welcome");
  await expect(other.locator("html")).toHaveAttribute("data-motion", "paused");
  await page
    .getByRole("button", { name: "Enable animations", exact: true })
    .click();
  await expect(other.locator("html")).toHaveAttribute(
    "data-motion-mode",
    "full",
  );
  await other
    .getByRole("button", { name: "Pause animations", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "paused");
  await other.close();
  await page.setViewportSize({ width: 320, height: 1000 });
  await page
    .getByRole("combobox", { name: "Interface language" })
    .selectOption("fr");
  await expect(page.locator(".motion-control")).toHaveText(
    "Animations en pause",
  );
  await page.locator(".motion-control").click();
  await expect(page.locator(".motion-control")).toHaveText(
    "Animations actives",
  );
  const controls = page.locator(".landing-controls > *");
  for (const control of await controls.all()) {
    if (!(await control.isVisible())) continue;
    const bounds = await control.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(320);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("full mode restores native scroll fades despite a reduced-motion device", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const native = HTMLElement.prototype.animate;
    const samples: { direction: string; opacity: number; finished: boolean }[] =
      [];
    Object.assign(window, { __motionSamples: samples });
    HTMLElement.prototype.animate = function (frames, options) {
      const animation = native.call(this, frames, options);
      if (typeof options === "object" && options.duration === 520) {
        const sample = {
          direction: this.dataset.revealDirection || "",
          opacity: 1,
          finished: false,
        };
        samples.push(sample);
        void animation.ready
          .then(() => {
            sample.opacity = Number(getComputedStyle(this).opacity);
          })
          .catch(() => {});
        void animation.finished
          .then(() => {
            sample.finished = true;
          })
          .catch(() => {});
      }
      return animation;
    };
  });
  await open(page);
  await page
    .getByRole("button", { name: "Enable animations", exact: true })
    .click();
  await expect(page.locator("#connexion-privee")).toBeAttached();
  await page.evaluate(() => document.fonts.ready);
  await page.locator(".landing-guide-link").scrollIntoViewIfNeeded();
  const finished = (direction: string) =>
    page.evaluate((direction) => {
      const samples = (
        window as unknown as {
          __motionSamples: {
            direction: string;
            opacity: number;
            finished: boolean;
          }[];
        }
      ).__motionSamples;
      return samples.some(
        (sample) =>
          sample.direction === direction &&
          sample.opacity < 0.5 &&
          sample.finished,
      );
    }, direction);
  await expect.poll(() => finished("down")).toBe(true);
  await page.locator(".landing-copy h1").scrollIntoViewIfNeeded();
  await expect.poll(() => finished("up")).toBe(true);
});
