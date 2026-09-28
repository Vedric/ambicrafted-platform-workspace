import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  const response = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(response.ok()).toBe(true);
  await page.goto("/assistant#session=" + (await response.json()).ticket);
  await expect(page.getByLabel("Your message")).toBeEditable();
}

test("saved dialogue retains source selection, history and drafts, then deletes explicitly", async ({
  page,
}) => {
  await login(page);
  const title = `Synthetic context ${test.info().project.name}`;
  const input = page.getByLabel("Your message");
  await page.locator('input[type="file"]').setInputFiles({
    name: "latency.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("service,p95_ms\nsynthetic,125\n"),
  });
  await expect(
    page.getByRole("checkbox", { name: "latency.csv" }),
  ).toBeChecked();
  await input.fill(title);
  const request = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      /\/conversations\/[^/]+\/messages$/.test(request.url()),
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const sent = (await request).postDataJSON();
  expect(sent.message).toBe(title);
  expect(sent.pieces).toHaveLength(1);
  await expect(page.locator(".chat-messages")).toContainText("Synthetic reply");
  await expect(input).toBeEditable();
  await input.fill("Unsent draft stays with this conversation.");
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await expect(input).toHaveValue("");
  await page
    .getByRole("button", { name: "Conversation history", exact: true })
    .click();
  await page.getByLabel("Search conversations").fill(title);
  await page
    .locator(".history-list")
    .getByRole("button", { name: new RegExp(`^${title}`) })
    .click();
  await expect(input).toHaveValue("Unsent draft stays with this conversation.");
  await expect(page.locator(".chat-messages")).toContainText(title);
  await expect(
    page.getByRole("checkbox", { name: "latency.csv" }),
  ).not.toBeChecked();
  // Sources are never silently re-sent after reopening a completed conversation.
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
  await page
    .getByRole("button", { name: "Conversation history", exact: true })
    .click();
  await expect(page.getByText("No saved conversations found.")).toBeVisible();
});

test("all six narrated guides decode audio and advance native playback", async ({
  page,
}) => {
  await login(page);
  for (const language of ["en", "fr"]) {
    for (const topic of ["first-steps", "voice", "investigation"]) {
      const result = await page.evaluate(
        async ({ language, topic }) => {
          const video = document.createElement("video");
          video.muted = true;
          video.src = `/guides/${topic}-${language}.mp4`;
          document.body.append(video);
          try {
            await video.play();
            await new Promise<void>((resolve, reject) => {
              const timeout = setTimeout(
                () => reject(new Error("Playback did not progress")),
                4000,
              );
              video.ontimeupdate = () => {
                if (video.currentTime > 0.1) {
                  clearTimeout(timeout);
                  resolve();
                }
              };
            });
            return {
              duration: video.duration,
              time: video.currentTime,
              width: video.videoWidth,
              audioBytes: (
                video as HTMLVideoElement & {
                  webkitAudioDecodedByteCount: number;
                }
              ).webkitAudioDecodedByteCount,
            };
          } finally {
            video.pause();
            video.removeAttribute("src");
            video.load();
            video.remove();
          }
        },
        { language, topic },
      );
      expect(result.duration).toBeGreaterThan(5);
      expect(result.time).toBeGreaterThan(0);
      expect(result.width).toBeGreaterThan(300);
      expect(result.audioBytes).toBeGreaterThan(0);
    }
  }
});

test("guide playback failure offers a working retry and stops when changing lessons", async ({
  page,
}) => {
  await login(page);
  await page.route("**/guides/first-steps-en.mp4", (route) => route.abort());
  await page.goto("/guide");
  await expect(page.getByRole("alert")).toContainText("Video unavailable");
  await page.unroute("**/guides/first-steps-en.mp4");
  await page.getByRole("button", { name: "Reload video" }).click();
  const video = page.locator("video");
  await expect
    .poll(() => video.evaluate((v) => (v as HTMLVideoElement).readyState))
    .toBeGreaterThan(1);
  await video.evaluate((v) => (v as HTMLVideoElement).play());
  await expect
    .poll(() => video.evaluate((v) => (v as HTMLVideoElement).currentTime))
    .toBeGreaterThan(0.1);
  await page.getByRole("button", { name: /Talk with AURA/ }).click();
  await expect(video).toHaveAttribute("src", "/guides/voice-en.mp4");
  expect(await video.evaluate((v) => (v as HTMLVideoElement).paused)).toBe(
    true,
  );
});
