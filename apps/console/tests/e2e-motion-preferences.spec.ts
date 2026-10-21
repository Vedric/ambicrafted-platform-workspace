import { expect, test, type Page } from "@playwright/test";

async function open(page: Page, legacy = "enabled", route = "/welcome") {
  await page.addInitScript((value) => {
    localStorage.setItem("ambicrafted-welcome-audio", "off");
    localStorage.setItem("ambicrafted-motion", value);
  }, legacy);
  // Motion readiness is asserted through real clocks, visibility and opacity
  // below. Firefox can leave window.load pending after the UI has rendered.
  if (route === "/welcome")
    return page.goto(route, { waitUntil: "domcontentloaded" });
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  await page.goto(route + "#session=" + (await response.json()).ticket, {
    waitUntil: "domcontentloaded",
  });
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

test("architecture flows animate automatically and follow live device reduction", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await open(page, "paused", "/architecture");
  const canvas = page.locator(".architecture-canvas");
  if (page.viewportSize()!.width <= 900) {
    await expect(page.locator(".architecture-mobile-list")).toBeVisible();
    await expect(canvas).toBeHidden();
    await page.setViewportSize({ width: 1024, height: 900 });
  }
  await canvas.scrollIntoViewIfNeeded();
  await expect(canvas).toHaveAttribute("data-motion", "on");
  const flow = page.locator(".architecture-flow").first();
  const offset = () =>
    flow.evaluate((element) => getComputedStyle(element).strokeDashoffset);
  const first = await offset();
  await expect.poll(offset).not.toBe(first);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(canvas).toHaveAttribute("data-motion", "off");
  await expect
    .poll(() =>
      flow.evaluate(
        (element) =>
          element.getAnimations().filter((a) => a.playState === "running")
            .length,
      ),
    )
    .toBe(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(canvas).toHaveAttribute("data-motion", "on");
  await expect(flow).toHaveCSS("animation-play-state", "running");
});

test("old pause preferences migrate to automatic motion across reloads", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.addInitScript(() =>
    localStorage.setItem("ambicrafted-motion-mode", "paused"),
  );
  await open(page, "paused");
  const core = page.locator(".neural-core").first();
  for (let visit = 0; visit < 2; visit++) {
    if (visit) await page.reload({ waitUntil: "domcontentloaded" });
    await core.scrollIntoViewIfNeeded();
    await expect(page.locator("html")).toHaveAttribute(
      "data-motion",
      "enabled",
    );
    await expect
      .poll(async () => (await coreState(page)).running)
      .toBeGreaterThanOrEqual(8);
    const before = await coreState(page);
    await expect
      .poll(async () => (await coreState(page)).ring)
      .not.toBe(before.ring);
    await expect(page.locator(".motion-control")).toHaveCount(0);
    expect(
      await page.evaluate(() => [
        localStorage.getItem("ambicrafted-motion-mode"),
        localStorage.getItem("ambicrafted-motion"),
      ]),
    ).toEqual([null, null]);
  }
  expect(errors).toEqual([]);
});

test("old full preferences cannot override reduced motion or hide content", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() =>
    localStorage.setItem("ambicrafted-motion-mode", "full"),
  );
  await open(page);
  const core = page.locator(".neural-core").first();
  await core.scrollIntoViewIfNeeded();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "paused");
  await expect.poll(async () => (await coreState(page)).running).toBe(0);
  await expect(page.locator(".landing-copy h1")).toHaveCSS("opacity", "1");
  await expect(page.locator(".scroll-progress")).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect
    .poll(async () => (await coreState(page)).running)
    .toBeGreaterThanOrEqual(8);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(async () => (await coreState(page)).running).toBe(0);
});

test("settings retain theme, language and responsive controls without a motion toggle", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 1000 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await open(page, "paused", "/parametres");
  await expect(page.locator("#appearance")).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Animation settings", exact: true }),
  ).toHaveCount(0);
  for (const [language, theme] of [
    ["en", "light"],
    ["fr", "dark"],
  ]) {
    await page.locator(".topbar .language-selector").selectOption(language);
    await page
      .locator(".theme-option-" + (theme === "light" ? "day" : "night"))
      .click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.locator("html")).toHaveAttribute(
      "data-motion",
      "enabled",
    );
    await expect(
      page.locator(".motion-control, .motion-mode-select"),
    ).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.locator("#cli-settings").scrollIntoViewIfNeeded();
  await expect(page.locator(".scroll-progress")).toBeVisible();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".scroll-progress")).toHaveCount(0);
});

test("native scroll fades run automatically despite old paused preferences", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
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
        // WebKit can resolve ready after much of a short animation has elapsed.
        // Read its computed starting style immediately, then sample frames;
        // keep the independent finished assertion to prove real progression.
        const measure = () => {
          sample.opacity = Math.min(
            sample.opacity,
            Number(getComputedStyle(this).opacity),
          );
          if (animation.playState === "running" || animation.pending)
            requestAnimationFrame(measure);
        };
        measure();
        void animation.finished
          .then(() => {
            sample.finished = true;
          })
          .catch(() => {});
      }
      return animation;
    };
  });
  await open(page, "paused");
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
  try {
    await expect.poll(() => finished("down")).toBe(true);
    await page.locator(".landing-copy h1").scrollIntoViewIfNeeded();
    await expect.poll(() => finished("up")).toBe(true);
  } finally {
    await test.info().attach("rendered-scroll-fades", {
      body: JSON.stringify(
        await page.evaluate(() => {
          const samples = (window as unknown as { __motionSamples: unknown })
            .__motionSamples;
          return {
            samples,
            scrollY,
            hidden: document.hidden,
            mode: document.documentElement.dataset.motionMode,
            targets: [...document.querySelectorAll("[data-reveal-state]")].map(
              (node) => ({
                tag: node.tagName,
                state: (node as HTMLElement).dataset.revealState,
                direction: (node as HTMLElement).dataset.revealDirection,
              }),
            ),
          };
        }),
      ),
      contentType: "application/json",
    });
  }
});
