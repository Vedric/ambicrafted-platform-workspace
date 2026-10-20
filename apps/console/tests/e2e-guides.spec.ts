import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import chapterStarts from "../src/guide-chapters.json" with { type: "json" };

async function login(page: Page) {
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  await page.goto("/guide#session=" + (await response.json()).ticket);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}
const captionMode = (page: Page) =>
  page
    .locator("video")
    .evaluate((video) => (video as HTMLVideoElement).textTracks[0]?.mode);

test("captions are optional and remembered across lessons and reloads without autoplay", async ({
  page,
}) => {
  await login(page);
  await expect(page.locator(".guide-lessons button")).toHaveCount(6);
  const toggle = page.getByRole("button", { name: "Captions", exact: true });
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => captionMode(page)).toBe("showing");
  await toggle.focus();
  await page.keyboard.press("Space");
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect.poll(() => captionMode(page)).toBe("disabled");
  await page.getByRole("button", { name: /Talk with AURA/ }).click();
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect.poll(() => captionMode(page)).toBe("disabled");
  await page.reload();
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect.poll(() => captionMode(page)).toBe("disabled");
  expect(
    await page
      .locator("video")
      .evaluate((video) => (video as HTMLVideoElement).paused),
  ).toBe(true);
  await page.locator(".guide-transcript summary").click();
  await expect(page.locator(".guide-transcript li")).toHaveCount(4);
  await toggle.click();
  await expect.poll(() => captionMode(page)).toBe("showing");
  // Native caption controls must update the same persisted preference.
  await page.locator("video").evaluate((video) => {
    (video as HTMLVideoElement).textTracks[0].mode = "disabled";
  });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  expect(
    await page.evaluate(() =>
      localStorage.getItem("ambicrafted-guide-captions"),
    ),
  ).toBe("off");
  const accessibility = await new AxeBuilder({ page })
    .include(".guide-walkthrough")
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

for (const language of ["en", "fr"]) {
  for (const [lesson, id] of [
    "first-steps",
    "voice",
    "investigation",
    "documents",
    "recovery",
    "observability",
  ].entries()) {
    test(`${language}/${id}: the visible 1080p player plays, pauses and seeks`, async ({
      page,
    }) => {
      await login(page);
      await page.getByRole("combobox").first().selectOption(language);
      await page.locator(".guide-lessons button").nth(lesson).click();
      const player = page.locator("video");
      await player.scrollIntoViewIfNeeded();
      // Use the actual visible player: WebKit can suspend offscreen media.
      await player.evaluate(async (element) => {
        const video = element as HTMLVideoElement;
        video.muted = true;
        await video.play();
      });
      await expect
        .poll(() =>
          player.evaluate(
            (element) => (element as HTMLVideoElement).currentTime,
          ),
        )
        .toBeGreaterThan(0.1);
      const media = await player.evaluate((element) => {
        const video = element as HTMLVideoElement;
        video.pause();
        return {
          width: video.videoWidth,
          height: video.videoHeight,
          duration: video.duration,
          paused: video.paused,
          source: video.currentSrc,
        };
      });
      expect(media).toMatchObject({ width: 1920, height: 1080, paused: true });
      expect(media.source).toMatch(new RegExp(`/${id}-${language}\\.mp4$`));
      expect(media.duration).toBeGreaterThanOrEqual(60);
      expect(media.duration).toBeLessThan(240);
      await player.evaluate((element) => {
        const video = element as HTMLVideoElement;
        video.currentTime = video.duration / 2;
      });
      await expect
        .poll(() =>
          player.evaluate((element) => {
            const video = element as HTMLVideoElement;
            return (
              video.readyState >= 2 &&
              Math.abs(video.currentTime - video.duration / 2) < 0.2
            );
          }),
        )
        .toBe(true);
    });
  }
}

for (const language of ["en", "fr"] as const) {
  test(`${language}: chapter navigation seeks before playback and preserves captions`, async ({
    page,
  }) => {
    await login(page);
    await page.getByRole("combobox").first().selectOption(language);
    await page.locator(".guide-lessons button").nth(3).click();
    const video = page.locator("video");
    const chapters = page.locator(".guide-chapters button");
    const toggle = page.getByRole("button", {
      name: language === "fr" ? "Sous-titres" : "Captions",
      exact: true,
    });
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(
      await video.evaluate((element) => (element as HTMLVideoElement).paused),
    ).toBe(true);
    await expect(video).toHaveAttribute("preload", "none");
    await expect(chapters).toHaveCount(4);
    await chapters.nth(2).focus();
    await page.keyboard.press("Enter");
    await expect
      .poll(() =>
        video.evaluate((element) => (element as HTMLVideoElement).currentTime),
      )
      .toBeCloseTo(chapterStarts.documents[language][2], 1);
    expect(
      await video.evaluate((element) => (element as HTMLVideoElement).paused),
    ).toBe(true);
    await expect.poll(() => captionMode(page)).toBe("disabled");
    await video.scrollIntoViewIfNeeded();
    await video.evaluate(async (element) => {
      const player = element as HTMLVideoElement;
      player.muted = true;
      await player.play();
    });
    await expect
      .poll(() =>
        video.evaluate((element) => (element as HTMLVideoElement).currentTime),
      )
      .toBeGreaterThan(chapterStarts.documents[language][2] + 0.1);
    await video.evaluate((element) => (element as HTMLVideoElement).pause());
    await chapters.nth(1).click();
    await expect
      .poll(() =>
        video.evaluate((element) => (element as HTMLVideoElement).currentTime),
      )
      .toBeCloseTo(chapterStarts.documents[language][1], 1);
    expect(
      await video.evaluate((element) => (element as HTMLVideoElement).paused),
    ).toBe(true);
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await toggle.click();
    await expect.poll(() => captionMode(page)).toBe("showing");
    await page.locator(".guide-lessons button").nth(0).click();
    await expect(video).toHaveAttribute("preload", "none");
    await chapters.nth(3).click();
    await expect
      .poll(() =>
        video.evaluate((element) => (element as HTMLVideoElement).currentTime),
      )
      .toBeCloseTo(chapterStarts["first-steps"][language][3], 1);
    expect(
      await video.evaluate((element) => (element as HTMLVideoElement).paused),
    ).toBe(true);
    await expect.poll(() => captionMode(page)).toBe("showing");
  });
}

test("missing captions retain an accessible transcript and usable video", async ({
  page,
}) => {
  await page.route("**/guides/first-steps-en.vtt", (route) => route.abort());
  await login(page);
  await page.locator("video").scrollIntoViewIfNeeded();
  await page.locator("video").evaluate(async (element) => {
    const video = element as HTMLVideoElement;
    video.muted = true;
    await video.play();
  });
  await expect(
    page.getByText(
      "Captions are unavailable. The full transcript remains below.",
    ),
  ).toBeVisible();
  await page.locator(".guide-transcript summary").click();
  await expect(page.locator(".guide-transcript li")).toHaveCount(4);
  await expect
    .poll(() =>
      page
        .locator("video")
        .evaluate((video) => (video as HTMLVideoElement).readyState),
    )
    .toBeGreaterThan(0);
});

for (const width of [390, 1440]) {
  test(`French guides remain readable in the light theme at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(() => {
      localStorage.setItem("ambicrafted-language", "fr");
      localStorage.setItem("ambicrafted-theme", "light");
    });
    await login(page);
    await expect(page.locator(".guide-lessons button")).toHaveCount(6);
    await expect(
      page.getByRole("button", { name: "Sous-titres", exact: true }),
    ).toBeVisible();
    await page.locator(".guide-transcript summary").click();
    await expect(page.locator(".guide-transcript li")).toHaveCount(4);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await page
      .locator(".guide-chapters button")
      .first()
      .scrollIntoViewIfNeeded();
    const accessibility = await new AxeBuilder({ page })
      .include(".guide-walkthrough")
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page
      .getByRole("button", { name: "Sous-titres", exact: true })
      .click();
    const withoutCaptions = await new AxeBuilder({ page })
      .include(".guide-walkthrough")
      .analyze();
    expect(withoutCaptions.violations).toEqual([]);
  });
}

test("the browser decodes audible narration through Web Audio", async ({
  page,
}) => {
  await login(page);
  const result = await page.evaluate(async () => {
    // Decode the actual MP4 audio track without depending on physical speakers.
    const context = new OfflineAudioContext(1, 24000, 24000);
    const response = await fetch("/guides/documents-en.mp4");
    if (!response.ok) throw new Error("Guide media could not be loaded");
    const audio = await context.decodeAudioData(await response.arrayBuffer());
    const samples = audio.getChannelData(0);
    let energy = 0;
    for (const sample of samples) energy += sample * sample;
    return {
      rms: Math.sqrt(energy / samples.length),
      duration: audio.duration,
      channels: audio.numberOfChannels,
    };
  });
  expect(result.channels).toBe(1);
  expect(result.duration).toBeGreaterThan(60);
  expect(Number.isFinite(result.rms)).toBe(true);
  expect(result.rms).toBeGreaterThan(0.005);
});
