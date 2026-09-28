import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { ambientState, observeAudio } from "./audio-observer";

declare global {
  interface Window {
    __auraSynthetic: { starts: number; stops: number; gains: GainNode[] };
    __audioDevices: {
      removed: boolean;
      denied: boolean;
      captures: MediaStreamConstraints[];
    };
  }
}

const browserErrors = new WeakMap<Page, string[]>();
test.beforeEach(({ page }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
});

async function selectableDevices(page: Page) {
  await syntheticSpeech(page);
  await observeAudio(page);
  await page.addInitScript(() => {
    window.__audioDevices = { removed: false, denied: false, captures: [] };
    const capture = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices,
    );
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      configurable: true,
      value: (constraints: MediaStreamConstraints) => {
        window.__audioDevices.captures.push(constraints);
        if (window.__audioDevices.denied)
          return Promise.reject(
            new DOMException("Synthetic permission denial", "NotAllowedError"),
          );
        return capture(constraints);
      },
    });
    Object.defineProperty(navigator.mediaDevices, "enumerateDevices", {
      configurable: true,
      value: async () => [
        ...(window.__audioDevices.removed
          ? []
          : [
              {
                kind: "audioinput",
                deviceId: "usb-mic",
                label: "Synthetic USB microphone",
              },
            ]),
        {
          kind: "audioinput",
          deviceId: "camera-mic",
          label: "Synthetic camera microphone",
        },
        {
          kind: "audiooutput",
          deviceId: "headset",
          label: "Synthetic headset",
        },
        {
          kind: "audiooutput",
          deviceId: "display",
          label: "Synthetic display speakers",
        },
      ],
    });
    // Virtual IDs exercise routing; actual decoding/playback uses the native
    // default sink. These tests do not certify physical peripheral switching.
    const native = HTMLMediaElement.prototype.setSinkId;
    const routed = new WeakMap<HTMLMediaElement, string>();
    Object.defineProperty(HTMLMediaElement.prototype, "sinkId", {
      configurable: true,
      get() {
        return routed.get(this) || "";
      },
    });
    HTMLMediaElement.prototype.setSinkId = async function (id) {
      if (native) await native.call(this, "");
      routed.set(this, id);
    };
  });
}

for (const language of ["en", "fr"] as const) {
  test(`audio device choices persist and route real capture/playback (${language})`, async ({
    page,
  }) => {
    await selectableDevices(page);
    await login(page);
    await page.evaluate(
      (lang) => localStorage.setItem("ambicrafted-language", lang),
      language,
    );
    await page.goto("/assistant");
    const input = page.getByLabel(
      language === "fr" ? "Entrée microphone" : "Microphone input",
      { exact: true },
    );
    const output = page.getByLabel(
      language === "fr" ? "Sortie audio" : "Speaker output",
      { exact: true },
    );
    await input.selectOption("usb-mic");
    await output.selectOption("headset");
    await page.reload();
    await expect(input).toHaveValue("usb-mic");
    await expect(output).toHaveValue("headset");
    await page
      .getByText(
        language === "fr"
          ? "Vérifier le microphone et le son"
          : "Check microphone & sound",
        { exact: true },
      )
      .click();
    await page
      .getByRole("button", {
        name: language === "fr" ? "Tester le microphone" : "Test microphone",
        exact: true,
      })
      .click();
    await expect(page.getByRole("meter")).toHaveAttribute("value", /0\.[1-9]/);
    expect(
      await page.evaluate(() => window.__audioDevices.captures.at(-1)?.audio),
    ).toMatchObject({ deviceId: { exact: "usb-mic" } });
    await expect(input).toBeDisabled();
    await page.waitForTimeout(600);
    await page
      .getByRole("button", {
        name: language === "fr" ? "Arrêter le test" : "Stop test",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", {
        name:
          language === "fr"
            ? "Écouter l’enregistrement"
            : "Listen to the sample",
        exact: true,
      })
      .click();
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            window.__nativeAudio.find((a) => a.src.startsWith("blob:"))
              ?.currentTime,
        ),
      )
      .toBeGreaterThan(0.1);
    expect(
      await page.evaluate(
        () =>
          window.__nativeAudio.find((a) => a.src.startsWith("blob:"))?.sinkId,
      ),
    ).toBe("headset");
    await page.keyboard.press("Escape");
    await accessible(page);
    const layout = await page.locator(".aura-stage").evaluate((stage) => {
      const core = stage.querySelector(".neural-core")!.getBoundingClientRect();
      const title = stage
        .querySelector(".aura-identity")!
        .getBoundingClientRect();
      return {
        vertical: title.top >= core.bottom - 1,
        overflow: document.documentElement.scrollWidth > innerWidth,
      };
    });
    expect(layout).toEqual({ vertical: true, overflow: false });
  });
}

test("audio discovery handles denied permission, removal and an explicit replacement", async ({
  page,
}) => {
  await selectableDevices(page);
  await login(page);
  await page.goto("/assistant");
  await page.evaluate(() => {
    window.__audioDevices.denied = true;
  });
  await page.getByRole("button", { name: "Detect devices" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Microphone access was denied",
  );
  await page.evaluate(() => {
    window.__audioDevices.denied = false;
  });
  await page.getByRole("button", { name: "Detect devices" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(await page.evaluate(() => window.__auraSynthetic.stops)).toBe(1);
  await page.getByLabel("Microphone input").selectOption("usb-mic");
  await page.evaluate(() => {
    window.__audioDevices.removed = true;
    navigator.mediaDevices.dispatchEvent(new Event("devicechange"));
  });
  await expect(page.getByLabel("Microphone input")).toContainText(
    "Saved microphone unavailable",
  );
  await page.getByLabel("Microphone input").selectOption("camera-mic");
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Finish recording", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => window.__audioDevices.captures.at(-1)?.audio),
  ).toMatchObject({ deviceId: { exact: "camera-mic" } });
  await page.keyboard.press("Escape");
});

test("welcome, music and guides share the chosen output without recording", async ({
  page,
}) => {
  await selectableDevices(page);
  await page.addInitScript(() =>
    localStorage.setItem("ambicrafted-welcome-audio", "off"),
  );
  await page.goto("/welcome");
  await page.locator(".welcome-device-settings > summary").click();
  await page.getByLabel("Speaker output").selectOption("display");
  await page.getByRole("button", { name: "Test speakers" }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          window.__nativeAudio.find((a) => a.src.endsWith("speaker-check.wav"))
            ?.currentTime,
      ),
    )
    .toBeGreaterThan(0.1);
  expect(
    await page.evaluate(
      () =>
        window.__nativeAudio.find((a) => a.src.endsWith("speaker-check.wav"))
          ?.sinkId,
    ),
  ).toBe("display");
  expect(await page.evaluate(() => window.__audioDevices.captures)).toEqual([]);
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Play ambient music", exact: true })
    .click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          window.__nativeAudio.find((a) => a.src.endsWith("orbital-drift.mp3"))
            ?.sinkId,
      ),
    )
    .toBe("display");
  await page
    .getByRole("button", { name: "Listen to my welcome", exact: true })
    .click();
  await expect(
    page.getByText("AURA is speaking", { exact: true }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          window.__nativeAudio.find((a) => a.src.includes("welcome-en"))
            ?.sinkId,
      ),
    )
    .toBe("display");
  await page.getByLabel("Speaker output").selectOption("headset");
  await expect
    .poll(() =>
      page.evaluate(() =>
        window.__nativeAudio
          .filter((a) => !a.paused)
          .every((a) => a.sinkId === "headset"),
      ),
    )
    .toBe(true);
  await page.keyboard.press("Escape");
  await login(page);
  await page.goto("/guide");
  const video = page.locator("video");
  await expect
    .poll(() => video.evaluate((v) => (v as HTMLVideoElement).sinkId))
    .toBe("headset");
  await video.evaluate((v) => (v as HTMLVideoElement).play());
  await expect
    .poll(() => video.evaluate((v) => (v as HTMLVideoElement).currentTime))
    .toBeGreaterThan(0.1);
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
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every(
        (animation) =>
          !Number.isFinite(animation.effect?.getComputedTiming().endTime) ||
          animation.playState === "finished" ||
          animation.playState === "idle",
      ),
  );
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
  await page
    .getByRole("button", { name: "Play ambient music", exact: true })
    .click();
  await expect
    .poll(async () => (await ambientState(page))?.time)
    .toBeGreaterThan(0.1);
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
  await expect
    .poll(async () => (await ambientState(page))?.volume)
    .toBeLessThan(0.01);
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
  await expect(page.locator(".chat-status")).toContainText("Listening");
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

test("local microphone check measures capture and plays a real encoded sample without uploading", async ({
  page,
}) => {
  await syntheticSpeech(page);
  await observeAudio(page);
  await login(page);
  await page.goto("/assistant");
  await expect(
    page.getByRole("button", { name: "Start conversation" }),
  ).toBeEnabled();
  const uploads: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST")
      uploads.push(new URL(request.url()).pathname);
  });
  await page.getByText("Check microphone & sound", { exact: true }).click();
  await page
    .getByRole("button", { name: "Test microphone", exact: true })
    .click();
  await expect(
    page.getByRole("meter", { name: "Test input level" }),
  ).toHaveAttribute("value", /0\.[1-9]/);
  await expect(
    page.getByRole("button", { name: "Record", exact: true }),
  ).toBeDisabled();
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: "Stop test", exact: true }).click();
  await page.getByRole("button", { name: "Listen to the sample" }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          window.__nativeAudio.find((a) => a.src.startsWith("blob:"))
            ?.currentTime,
      ),
    )
    .toBeGreaterThan(0.1);
  expect(await page.evaluate(() => window.__auraSynthetic.stops)).toBe(1);
  expect(uploads).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Record", exact: true }),
  ).toBeEnabled();
});

test("spoken conversation waits for model preparation and can recover from a busy engine", async ({
  page,
}) => {
  await syntheticSpeech(page);
  let ready!: () => void;
  const pending = new Promise<void>((resolve) => {
    ready = resolve;
  });
  let attempts = 0;
  await page.route("**/api/assistant/preparer", async (route) => {
    attempts++;
    if (attempts === 1) {
      await pending;
      await route.fulfill({
        status: 503,
        json: { detail: "Synthetic unavailable engine" },
      });
    } else await route.fulfill({ json: { pret: true, local: true } });
  });
  await login(page);
  await page.goto("/assistant");
  await expect(
    page.getByText(/Preparing the local model before/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start conversation" }),
  ).toBeDisabled();
  expect(await page.evaluate(() => window.__auraSynthetic.starts)).toBe(0);
  ready();
  await page.getByRole("button", { name: "Prepare conversation" }).click();
  await expect(
    page.getByRole("button", { name: "Start conversation" }),
  ).toBeEnabled();
  expect(await page.evaluate(() => window.__auraSynthetic.starts)).toBe(0);
});

test("retrying an uncertain spoken reply through Send does not duplicate history", async ({
  page,
}) => {
  await syntheticSpeech(page);
  await login(page);
  await page.goto("/assistant");
  const bodies: { vocal: boolean; operation_id: string }[] = [];
  let conversationUrl = "";
  await page.route("**/api/conversations/*/messages", async (route) => {
    bodies.push(route.request().postDataJSON());
    conversationUrl = route
      .request()
      .url()
      .replace(/\/messages$/, "");
    if (bodies.length === 1) {
      const completed = await route.fetch();
      expect(completed.ok()).toBe(true);
      await completed.body(); // The server saved the pair, but the browser did not receive it.
      await route.abort("failed");
    } else await route.continue();
  });
  await page.getByRole("button", { name: "Start conversation" }).click();
  await expect
    .poll(() => page.evaluate(() => window.__auraSynthetic.starts))
    .toBe(1);
  await page.waitForTimeout(750);
  await page.evaluate(() => {
    window.__auraSynthetic.gains.at(-1)!.gain.value = 0;
  });
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Your message")).toHaveValue(
    "Synthetic browser question.",
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".chat-messages")).toContainText("Synthetic reply");
  expect(bodies).toHaveLength(2);
  expect(bodies[1].vocal).toBe(true);
  expect(bodies[1].operation_id).toBe(bodies[0].operation_id);
  const thread = await (await page.request.get(conversationUrl)).json();
  expect(thread.total_messages).toBe(2);
});
