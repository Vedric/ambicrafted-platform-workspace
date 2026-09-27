import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { ambientState, observeAudio } from "./audio-observer";

declare global {
  interface Window {
    __auraSynthetic: { starts: number; stops: number; gains: GainNode[] };
  }
}

const browserErrors = new WeakMap<Page, string[]>();
test.beforeEach(({ page }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(({ page }) => expect(browserErrors.get(page)).toEqual([]));

async function login(page: Page) {
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
}

async function accessible(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.allSettled(
      document
        .getAnimations()
        .filter((animation) =>
          Number.isFinite(animation.effect?.getComputedTiming().endTime),
        )
        .map((animation) => animation.finished),
    );
  });
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    result.violations.map((violation) => ({
      id: violation.id,
      nodes: violation.nodes.map((node) => ({
        target: node.target,
        reason: node.failureSummary,
      })),
    })),
  ).toEqual([]);
}

function speechWav() {
  const rate = 8000,
    duration = 3;
  const buffer = Buffer.alloc(44 + rate * duration * 2);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(buffer.length - 8, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(rate, 24);
  buffer.writeUInt32LE(rate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(buffer.length - 44, 40);
  for (let sample = 1600; sample < rate * duration - 1600; sample++)
    buffer.writeInt16LE(
      Math.round(Math.sin((sample * 2 * Math.PI * 220) / rate) * 8192),
      44 + sample * 2,
    );
  return buffer;
}

async function syntheticSpeech(page: Page) {
  // A real browser MediaStream and Analyser, driven by a synthetic oscillator.
  // No physical microphone, model, external speech API or audible feedback.
  await page.addInitScript(() => {
    window.__auraSynthetic = { starts: 0, stops: 0, gains: [] };
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      configurable: true,
      value: async () => {
        const context = new AudioContext();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        const destination = context.createMediaStreamDestination();
        oscillator.frequency.value = 220;
        gain.gain.value = 0.12;
        oscillator.connect(gain);
        gain.connect(destination);
        oscillator.start();
        await context.resume();
        window.__auraSynthetic.starts += 1;
        window.__auraSynthetic.gains.push(gain);
        for (const track of destination.stream.getTracks()) {
          const stop = track.stop.bind(track);
          let stopped = false;
          track.stop = () => {
            if (!stopped) {
              stopped = true;
              window.__auraSynthetic.stops += 1;
              oscillator.stop();
              void context.close();
            }
            stop();
          };
        }
        return destination.stream;
      },
    });
  });
  await page.route("**/api/voix/statut?*", (route) =>
    route.fulfill({
      json: {
        pret: true,
        local: true,
        voix: "voix-feminine-en",
        langue: "en-US",
      },
    }),
  );
  await page.route("**/api/voix/transcrire", (route) =>
    route.fulfill({
      json: { texte: "Synthetic browser question.", local: true },
    }),
  );
  await page.route("**/api/voix/parler", (route) =>
    route.fulfill({ contentType: "audio/wav", body: speechWav() }),
  );
}

test("mission templates remain editable and readiness explains a missing prerequisite", async ({
  page,
}) => {
  await page.route("**/api/preparation", (route) =>
    route.fulfill({
      json: {
        schema_version: 1,
        checked_at: "2026-09-27T10:15:00Z",
        duration_ms: 12,
        scope: "local-private",
        ready: false,
        summary: { pass: 1, warn: 0, fail: 1, unknown: 0 },
        capabilities: {},
        limits: ["One trusted local operator; no tenant isolation."],
        checks: [
          {
            id: "uv",
            group: "runtime",
            status: "pass",
            required: true,
            label: "uv runtime",
            message: "Pinned runtime available.",
            evidence: { version: "synthetic" },
            action: null,
          },
          {
            id: "index",
            group: "knowledge",
            status: "fail",
            required: true,
            label: "Reviewed index",
            message: "Synthetic missing index.",
            evidence: {},
            action: {
              label: "Build the local index",
              command: "./plateforme operation indexer --attendre",
            },
          },
        ],
      },
    }),
  );
  await login(page);
  await page.goto("/missions");
  await expect(
    page.getByRole("heading", { name: "Give your next move a direction." }),
  ).toBeVisible();
  await page.getByLabel("Find a mission").fill("no-such-synthetic-mission");
  await expect(page.getByRole("status")).toContainText("No matching mission");
  await page.getByLabel("Find a mission").fill("latency");
  await page.getByRole("link", { name: /Trace a slowdown/ }).click();
  await expect(page.getByLabel(/Analysis title/)).toHaveValue(
    "Latency investigation",
  );
  await expect(page.getByLabel(/Alert & context/)).toHaveValue(
    /Normal latency/,
  );
  await expect(
    page.getByText(
      "Replace the prompts with observed facts before launching. This draft has not been submitted.",
    ),
  ).toBeVisible();
  await page
    .getByLabel(/Alert & context/)
    .fill("Synthetic facts entered by the operator.");
  await page.goto("/preparation");
  await expect(
    page.getByRole("heading", { name: "Your workspace needs attention." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "1 Failed" }).click();
  await expect(page.getByText("uv runtime", { exact: true })).not.toBeVisible();
  await page.getByText("Reviewed index", { exact: true }).click();
  await expect(
    page.getByText("./plateforme operation indexer --attendre", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Required for core operations", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Show all checks" }).click();
  await expect(page.getByText("uv runtime", { exact: true })).toBeVisible();
  await accessible(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("interface language persists and leaves operator input and speech language independent", async ({
  page,
}) => {
  await login(page);
  await page.goto("/analyses/nouvelle");
  await page
    .getByLabel(/Analysis title/)
    .fill("Keep this English customer title");
  await page
    .getByLabel(/Alert & context/)
    .fill("Keep this original evidence unchanged.");
  await page.getByLabel("Interface language").selectOption("fr");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByLabel("Titre de l’analyse")).toHaveValue(
    "Keep this English customer title",
  );
  await expect(page.getByLabel("Alerte et contexte")).toHaveValue(
    "Keep this original evidence unchanged.",
  );
  await expect(
    page.getByRole("button", { name: "Lancer l’analyse" }),
  ).toBeVisible();
  await accessible(page);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Nouvelle analyse", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Langue de l’interface")).toHaveValue("fr");
  await page.goto("/assistant");
  await expect(
    page.getByRole("heading", { name: "Assistante vocale", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#voice-language")).toHaveValue("fr");
  await page.locator("#voice-language").selectOption("en");
  await expect(page.getByLabel("Votre message")).toBeEditable();
  await accessible(page);
  await page.getByLabel("Langue de l’interface").selectOption("en");
  await expect(page.locator("#voice-language")).toHaveValue("en");
  await expect(
    page.getByRole("heading", { name: "Voice assistant", exact: true }),
  ).toBeVisible();
});

test("AURA measures a real synthetic microphone, supports motion pause and reviews manual transcription", async ({
  page,
}) => {
  await syntheticSpeech(page);
  await observeAudio(page);
  await login(page);
  await page.goto("/assistant");
  await expect(
    page.getByRole("button", { name: "Record", exact: true }),
  ).toBeEnabled();
  expect(await page.evaluate(() => window.__auraSynthetic.starts)).toBe(0);
  await page.getByRole("button", { name: "Play ambient music", exact: true }).click();
  await expect.poll(async () => (await ambientState(page))?.time).toBeGreaterThan(.1);
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await expect.poll(async () => (await ambientState(page))?.volume).toBe(0);
  const core = page.locator(".aura-stage .neural-core");
  await core.scrollIntoViewIfNeeded();
  await expect(core).toHaveAttribute("data-signal", "measured");
  await expect
    .poll(() =>
      core.evaluate((element) =>
        Number((element as HTMLElement).style.getPropertyValue("--signal")),
      ),
    )
    .toBeGreaterThan(0.1);
  await page.getByRole("button", { name: "Pause animations" }).click();
  await expect(core).toHaveAttribute("data-resting", "true");
  await expect(
    page.getByRole("button", { name: "Stop recording", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Enable animations" }).click();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(core).toHaveAttribute("data-resting", "true");
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await expect(page.getByLabel("Your message")).toHaveValue(
    "Synthetic browser question.",
  );
  await expect(
    page.getByRole("button", { name: "Listen", exact: true }),
  ).not.toBeVisible();
  expect(await page.evaluate(() => window.__auraSynthetic.stops)).toBe(1);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await core.scrollIntoViewIfNeeded();
  await expect(page.locator(".chat-status")).toContainText("Speaking");
  await expect.poll(async () => (await ambientState(page))?.volume).toBeLessThan(.01);
  await expect(core).toHaveAttribute("data-signal", "measured");
  await expect
    .poll(() =>
      core.evaluate((element) =>
        Number((element as HTMLElement).style.getPropertyValue("--signal")),
      ),
    )
    .toBeGreaterThan(0.1);
  await page.keyboard.press("Escape");
  await expect(page.locator(".chat-status")).toContainText(
    "Ready when you are",
  );
});

test("AURA hands-free speech advances after silence and stops on Escape", async ({
  page,
}) => {
  await syntheticSpeech(page);
  await login(page);
  await page.goto("/assistant");
  const transcripts: unknown[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/voix/transcrire"))
      transcripts.push(request.postDataJSON());
  });
  await page.getByRole("button", { name: "Start conversation" }).click();
  await expect
    .poll(() => page.evaluate(() => window.__auraSynthetic.starts))
    .toBe(1);
  await expect(page.locator(".chat-status")).toContainText("Recording");
  await page.waitForTimeout(750); // Let VAD observe actual nonzero analyser samples.
  await page.evaluate(() => {
    window.__auraSynthetic.gains.at(-1)!.gain.value = 0;
  });
  await expect(page.locator(".chat-status")).toContainText("Speaking");
  expect(transcripts).toHaveLength(1);
  expect(transcripts[0]).toMatchObject({ langue: "en" });
  await expect
    .poll(() => page.evaluate(() => window.__auraSynthetic.starts))
    .toBe(2);
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Start conversation" }),
  ).toBeEnabled();
  expect(await page.evaluate(() => window.__auraSynthetic.stops)).toBe(2);
  await page.waitForTimeout(1000);
  expect(await page.evaluate(() => window.__auraSynthetic.starts)).toBe(2);
  expect(transcripts).toHaveLength(1);
});
