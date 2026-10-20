import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

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

test("all twelve walkthroughs play their 1080p video", async ({ page }) => {
  await login(page);
  for (const language of ["en", "fr"])
    for (const lesson of [
      "first-steps",
      "voice",
      "investigation",
      "documents",
      "recovery",
      "observability",
    ]) {
      const result = await page.evaluate(
        async ({ language, lesson }) => {
          const video = document.createElement("video");
          video.muted = true;
          video.src = `/guides/${lesson}-${language}.mp4`;
          document.body.append(video);
          try {
            await video.play();
            await new Promise<void>((resolve, reject) => {
              const timer = setTimeout(
                () => reject(new Error("Video playback did not progress")),
                4000,
              );
              video.ontimeupdate = () => {
                if (video.currentTime > 0.1) {
                  clearTimeout(timer);
                  resolve();
                }
              };
            });
            return {
              width: video.videoWidth,
              height: video.videoHeight,
              duration: video.duration,
              progressed: video.currentTime > 0.1,
            };
          } finally {
            video.pause();
            video.removeAttribute("src");
            video.load();
            video.remove();
          }
        },
        { language, lesson },
      );
      expect(result).toMatchObject({
        width: 1920,
        height: 1080,
        progressed: true,
      });
      expect(result.duration).toBeGreaterThanOrEqual(60);
      expect(result.duration).toBeLessThan(240);
    }
});

test("missing captions retain an accessible transcript and usable video", async ({
  page,
}) => {
  await page.route("**/guides/first-steps-en.vtt", (route) => route.abort());
  await login(page);
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

test("French guides remain readable in the light theme on a narrow screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
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
  const accessibility = await new AxeBuilder({ page })
    .include(".guide-walkthrough")
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

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
