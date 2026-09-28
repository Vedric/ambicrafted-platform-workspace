import { expect, test, type Locator, type Page } from "@playwright/test";

declare global {
  interface Window {
    __auraFades: {
      target: HTMLElement;
      direction: string;
      before: number;
      after?: number;
      y: number;
      endY?: number;
    }[];
  }
}

async function open(page: Page, route: string) {
  await page.addInitScript(() => {
    localStorage.setItem("ambicrafted-welcome-audio", "off");
    localStorage.setItem("ambicrafted-motion", "enabled");
  });
  if (route === "/welcome") return page.goto(route);
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  await page.goto(route + "#session=" + (await response.json()).ticket);
}

function snapshot(core: Locator) {
  return core.evaluate(async (element) => {
    // A CSS pause is pending until the next animation frame. Its playState can
    // already be "paused" while the hold time has not yet been committed.
    await Promise.all(
      element
        .getAnimations({ subtree: true })
        .map((animation) => animation.ready),
    );
    const style = (selector: string) =>
      getComputedStyle(element.querySelector(selector)!);
    return {
      ring: style(".track-one").transform,
      lens: style(".core-lens").transform,
      wave: style(".core-waves circle").opacity,
      signal: (element as HTMLElement).style.getPropertyValue("--signal"),
      running: element
        .getAnimations({ subtree: true })
        .filter(
          (animation) =>
            animation.playState === "running" &&
            animation.effect?.getComputedTiming().endTime === Infinity,
        ).length,
    };
  });
}

for (const route of ["/welcome", "/", "/assistant"]) {
  test(`AURA keeps visibly moving at rest on ${route}, then honors pause and reduced motion`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await open(page, route);
    const core = page.locator(".neural-core").first();
    await core.scrollIntoViewIfNeeded();
    await expect(core).toHaveAttribute("data-resting", "false");
    await expect(core).toHaveAttribute("data-phase", "idle");
    const first = await snapshot(core);
    expect(first.running).toBeGreaterThanOrEqual(8);
    // Go beyond a complete pulse cycle: motion must continue after arrival.
    await page.waitForTimeout(4900);
    const later = await snapshot(core);
    expect(later.ring).not.toBe(first.ring);
    expect(later.lens).not.toBe(first.lens);
    expect(later.wave).not.toBe(first.wave);
    expect(later.running).toBe(first.running);
    expect(later.signal).toBe("0"); // Decorative motion is not fabricated audio.

    await page
      .getByRole("button", { name: "Pause animations", exact: true })
      .click();
    await core.scrollIntoViewIfNeeded();
    await expect(core).toHaveAttribute("data-resting", "true");
    await expect.poll(async () => (await snapshot(core)).running).toBe(0);
    const paused = await snapshot(core);
    await page.waitForTimeout(250);
    expect(await snapshot(core)).toEqual(paused);

    await page
      .getByRole("button", { name: "Enable animations", exact: true })
      .click();
    await core.scrollIntoViewIfNeeded();
    await expect
      .poll(async () => (await snapshot(core)).running)
      .toBe(first.running);
    await expect
      .poll(async () => (await snapshot(core)).ring)
      .not.toBe(paused.ring);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(core).toHaveAttribute("data-resting", "true");
    await expect.poll(async () => (await snapshot(core)).running).toBe(0);
    expect(errors).toEqual([]);
  });
}

test("AURA suspends offscreen motion and resumes its clocks when visible again", async ({
  page,
}) => {
  await open(page, "/assistant");
  const core = page.locator(".neural-core").first();
  await core.scrollIntoViewIfNeeded();
  await expect(core).toHaveAttribute("data-resting", "false");
  await page.locator(".app-footer").scrollIntoViewIfNeeded();
  await expect(core).toHaveAttribute("data-resting", "true");
  const paused = await snapshot(core);
  expect(paused.running).toBe(0);
  await page.waitForTimeout(250);
  expect(await snapshot(core)).toEqual(paused);
  await core.scrollIntoViewIfNeeded();
  await expect(core).toHaveAttribute("data-resting", "false");
  await expect
    .poll(async () => (await snapshot(core)).ring)
    .not.toBe(paused.ring);
});

for (const [route, lower, upper] of [
  ["/welcome", ".landing-guide-link", ".landing-copy h1"],
  ["/assistant", ".audio-devices", ".aura-identity"],
  ["/guide", ".guide-faq > details", ".page-title"],
  ["/parametres", "#cli-settings", ".page-title"],
]) {
  test(`actual page fades remain visible in both scroll directions on ${route}`, async ({
    page,
  }) => {
    const session = await page.context().newCDPSession(page);
    await session.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    await page.addInitScript(() => {
      window.__auraFades = [];
      const native = HTMLElement.prototype.animate;
      HTMLElement.prototype.animate = function (frames, options) {
        const animation = native.call(this, frames, options);
        if (typeof options === "object" && options.duration === 520) {
          const entry: Window["__auraFades"][number] = {
            target: this,
            direction: this.dataset.revealDirection || "",
            before: Infinity,
            y: Infinity,
          };
          window.__auraFades.push(entry);
          // The native timeline starts after a rendering opportunity, then
          // applies its stagger. A wall-clock sample at 850 ms can still catch
          // the last frame on a busy runner. Observe actual lifecycle promises.
          void animation.ready
            .then(() => {
              entry.before = Number(getComputedStyle(this).opacity);
              entry.y = this.getBoundingClientRect().y + window.scrollY;
            })
            .catch(() => {});
          void animation.finished
            .then(() =>
              Object.assign(entry, {
                after: Number(getComputedStyle(this).opacity),
                // Scroll changes viewport coordinates, not document geometry.
                endY: this.getBoundingClientRect().y + window.scrollY,
              }),
            )
            .catch(() => {});
        }
        return animation;
      };
    });
    await open(page, route);
    await expect(page.locator(upper).first()).toBeVisible();
    if (route === "/welcome")
      await expect(page.locator("#connexion-privee")).toBeAttached();
    await page.evaluate(() => document.fonts.ready);
    const faded = (selector: string, direction: string) =>
      page.evaluate(
        ({ selector, direction }) =>
          window.__auraFades.some(
            (entry) =>
              entry.target.matches(selector) &&
              entry.direction === direction &&
              entry.before < 0.5 &&
              entry.after === 1 &&
              Math.abs(entry.y - (entry.endY ?? Infinity)) < 1,
          ),
        { selector, direction },
      );
    await page.locator(lower).first().scrollIntoViewIfNeeded();
    try {
      await expect.poll(() => faded(lower, "down")).toBe(true);
    } catch (error) {
      console.log(
        await page.evaluate(
          (selector) =>
            window.__auraFades
              .filter((entry) => entry.target.matches(selector))
              .map(({ target, ...entry }) => ({
                ...entry,
                connected: target.isConnected,
              })),
          lower,
        ),
      );
      throw error;
    }
    await page.evaluate(() =>
      scrollTo({
        top: document.documentElement.scrollHeight,
        behavior: "instant",
      }),
    );
    await page.waitForTimeout(100);
    await page.locator(upper).first().scrollIntoViewIfNeeded();
    await expect.poll(() => faded(upper, "up")).toBe(true);
  });
}
