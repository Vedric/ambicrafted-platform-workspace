import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Assistant from "./Assistant";
import type { SignalReader } from "./audio-signal";
import { setLanguage } from "./i18n";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  audio: vi.fn(),
  notifier: vi.fn(),
  core: vi.fn(),
}));
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  api: mocks.api,
  audioLocal: mocks.audio,
}));
vi.mock("./NeuralCore", () => ({
  NeuralCore: (props: unknown) => {
    mocks.core(props);
    return <div aria-hidden="true" />;
  },
}));
vi.mock("./ui", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./ui")>()),
  useToast: () => mocks.notifier,
  Titre: ({ titre, children }: { titre: string; children: ReactNode }) => (
    <>
      <h1>{titre}</h1>
      {children}
    </>
  ),
  Markdown: ({ texte }: { texte: string }) => <p>{texte}</p>,
}));
let amplitude: number;
let suspendedInitially: boolean;
let recorders: Recorder[];
let contexts: MicrophoneContext[];
let players: Player[];
let playError: Error | null;
const track = { stop: vi.fn() };
const stream = { getTracks: () => [track] };
const revoke = vi.fn();
const originalMedia = Object.getOwnPropertyDescriptor(
  navigator,
  "mediaDevices",
);
const OriginalURL = URL;

class Recorder {
  static isTypeSupported() {
    return true;
  }
  state = "inactive";
  mimeType = "audio/webm;codecs=opus";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    recorders.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    void Promise.resolve().then(() => {
      this.ondataavailable?.({ data: new Blob(["synthetic audio"]) });
      this.onstop?.();
    });
  }
}
class MicrophoneContext {
  state = suspendedInitially ? "suspended" : "running";
  destination = {};
  source = { connect: vi.fn(), disconnect: vi.fn() };
  analyser = {
    fftSize: 1024,
    disconnect: vi.fn(),
    getFloatTimeDomainData: vi.fn((values: Float32Array) =>
      values.fill(amplitude),
    ),
  };
  constructor() {
    contexts.push(this);
  }
  createMediaStreamSource = vi.fn(() => this.source);
  createAnalyser = vi.fn(() => this.analyser);
  createMediaElementSource = vi.fn(() => {
    throw new Error("Playback must remain native");
  });
  resume = vi.fn(async () => {
    this.state = "running";
  });
  close = vi.fn(async () => {
    this.state = "closed";
  });
}
class Player {
  paused = true;
  currentTime = 0;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public src: string) {
    players.push(this);
  }
  play = vi.fn(async () => {
    if (playError) throw playError;
    this.paused = false;
  });
  pause = vi.fn(() => {
    this.paused = true;
  });
  removeAttribute = vi.fn();
}
function pcmBlob() {
  const buffer = new ArrayBuffer(16044);
  const bytes = new Uint8Array(buffer),
    view = new DataView(buffer);
  for (const [offset, tag] of [
    [0, "RIFF"],
    [8, "WAVE"],
    [12, "fmt "],
    [36, "data"],
  ] as const)
    bytes.set(new TextEncoder().encode(tag), offset);
  view.setUint32(4, buffer.byteLength - 8, true);
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true);
  view.setUint32(28, 16000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  view.setUint32(40, 16000, true);
  for (let sample = 2400; sample < 4800; sample++)
    view.setInt16(44 + sample * 2, 4096, true);
  const blob = new Blob([buffer], { type: "audio/wav" });
  Object.defineProperty(blob, "arrayBuffer", { value: async () => buffer });
  return blob;
}
function defaultApi(route: string) {
  return Promise.resolve(
    route.startsWith("/voix/statut")
      ? { pret: true, local: true, voix: "voix-feminine-en", langue: "en-US" }
      : route === "/voix/transcrire"
        ? { texte: "A synthetic question." }
        : { texte: "A synthetic answer." },
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  amplitude = 0.03;
  suspendedInitially = false;
  recorders = [];
  contexts = [];
  players = [];
  playError = null;
  mocks.api.mockImplementation(defaultApi);
  mocks.audio.mockResolvedValue(pcmBlob());
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
  });
  vi.stubGlobal("MediaRecorder", Recorder);
  vi.stubGlobal("AudioContext", MicrophoneContext);
  vi.stubGlobal("Audio", Player);
  let url = 0;
  vi.stubGlobal(
    "URL",
    class extends OriginalURL {
      static createObjectURL() {
        return `blob:synthetic-${++url}`;
      }
      static revokeObjectURL = revoke;
    },
  );
  vi.stubGlobal(
    "FileReader",
    class {
      result = "data:audio/webm;base64,c3ludGhldGlj";
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      readAsDataURL() {
        void Promise.resolve().then(() => this.onload?.());
      }
    },
  );
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  if (originalMedia)
    Object.defineProperty(navigator, "mediaDevices", originalMedia);
  else Reflect.deleteProperty(navigator, "mediaDevices");
});
async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}
async function show() {
  const view = render(
    <MemoryRouter>
      <Assistant />
    </MemoryRouter>,
  );
  await flush();
  return view;
}
async function click(name: string) {
  fireEvent.click(screen.getByRole("button", { name }));
  await flush();
}
async function send(text = "Synthetic input") {
  fireEvent.change(screen.getByLabelText("Your message"), {
    target: { value: text },
  });
  await click("Send");
}
function calls(route: string) {
  return mocks.api.mock.calls.filter(([value]) => value === route);
}
function reader(): SignalReader | null {
  return mocks.core.mock.calls.at(-1)?.[0].signal.current;
}
async function advance(milliseconds: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
  });
}
async function finishPlayback() {
  act(() => {
    const audio = players.at(-1)!;
    audio.paused = true;
    audio.onended?.();
  });
  await flush();
}
async function spokenTurn() {
  amplitude = 0.03;
  await advance(500);
  amplitude = 0;
  await advance(2000);
  expect(screen.getByRole("status")).toHaveTextContent("Speaking");
}

describe("manual speech resources and language", () => {
  it("resumes Web Audio during the click, before microphone permission resolves", async () => {
    suspendedInitially = true;
    let allow!: (value: MediaStream) => void;
    vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(
      new Promise((resolve) => {
        allow = resolve;
      }),
    );
    await show();
    await click("Record");
    expect(contexts).toHaveLength(1);
    expect(contexts[0].resume).toHaveBeenCalledOnce();
    expect(contexts[0].createMediaStreamSource).not.toHaveBeenCalled();
    expect(recorders).toHaveLength(0);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Waiting for microphone permission",
    );
    await act(async () => allow(stream as unknown as MediaStream));
    expect(contexts[0].createMediaStreamSource).toHaveBeenCalledOnce();
    await click("Stop recording");
    expect(contexts[0].close).toHaveBeenCalledOnce();
  });

  it("ignores old device overrides, follows the system input and reports disconnection", async () => {
    localStorage.setItem(
      "ambicrafted-audio-devices",
      JSON.stringify({ inputId: "mic-private-id", outputId: "" }),
    );
    const audioTrack = Object.assign(new EventTarget(), {
      stop: vi.fn(),
      muted: false,
      enabled: true,
    });
    vi.mocked(navigator.mediaDevices.getUserMedia).mockResolvedValue({
      getTracks: () => [audioTrack],
      getAudioTracks: () => [audioTrack],
    } as unknown as MediaStream);
    await show();
    await click("Record");
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
    await act(async () => {
      audioTrack.dispatchEvent(new Event("ended"));
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "microphone was disconnected",
    );
    expect(audioTrack.stop).toHaveBeenCalled();
    expect(calls("/voix/transcrire")).toHaveLength(0);
    expect(calls("/assistant/dialogue")).toHaveLength(0);
  });

  it("reports actual usage, preserves unknown counts and resets the ephemeral ledger", async () => {
    const responses = [
      { prompt_tokens: 400, completion_tokens: 25, total_tokens: 425 },
      undefined,
      { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
    ];
    mocks.api.mockImplementation((route: string) =>
      route === "/assistant/dialogue"
        ? Promise.resolve({
            texte: "A synthetic answer.",
            usage: responses.shift(),
          })
        : defaultApi(route),
    );
    await show();
    const card = screen.getByRole("region", { name: "Reported token usage" });
    expect(within(card).getAllByText("Not reported")).toHaveLength(3);
    await send();
    expect(within(card).getByText("400")).toBeVisible();
    expect(within(card).getByText("25")).toBeVisible();
    expect(within(card).getByText("425")).toBeVisible();
    await send();
    expect(within(card).getAllByText("Not reported")).toHaveLength(2);
    expect(within(card).getByText("425")).toBeVisible();
    expect(
      within(card).getByText("Usage reported for 1 of 2 completed replies."),
    ).toBeVisible();
    await send();
    expect(within(card).getAllByText("0")).toHaveLength(2);
    expect(
      within(card).getByText("Usage reported for 2 of 3 completed replies."),
    ).toBeVisible();
    expect(localStorage.length).toBe(0);
    await click("Clear conversation");
    expect(within(card).getAllByText("Not reported")).toHaveLength(3);
    expect(
      within(card).getByText("Usage reported for 0 of 0 completed replies."),
    ).toBeVisible();
  });
  it("preserves an existing draft and requires clearing it before hands-free capture", async () => {
    await show();
    const input = screen.getByLabelText("Your message");
    const start = screen.getByRole("button", { name: "Start conversation" });
    const draft = "Customer evidence that must not be overwritten.";
    fireEvent.change(input, { target: { value: draft } });
    expect(start).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    fireEvent.click(start);
    await flush();
    expect(input).toHaveValue(draft);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    expect(calls("/assistant/dialogue")).toHaveLength(0);
    fireEvent.change(input, { target: { value: "" } });
    expect(start).toBeEnabled();
    await click("Start conversation");
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledOnce();
    expect(input).toBeDisabled();
    await click("End conversation");
    expect(input).toBeEnabled();
  });

  it("connects only the microphone analyser and releases it after editable transcription", async () => {
    await show();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    await click("Record");
    expect(contexts[0].source.connect).toHaveBeenCalledWith(
      contexts[0].analyser,
    );
    expect(contexts[0].source.connect).toHaveBeenCalledTimes(1);
    expect(reader()?.()?.level).toBeGreaterThan(0);
    await click("Stop recording");
    expect(screen.getByLabelText("Your message")).toHaveValue(
      "A synthetic question.",
    );
    expect(calls("/assistant/dialogue")).toHaveLength(0);
    expect(contexts[0].source.disconnect).toHaveBeenCalled();
    expect(contexts[0].analyser.disconnect).toHaveBeenCalled();
    expect(contexts[0].close).toHaveBeenCalledOnce();
    expect(reader()).toBeNull();
  });
  it("forwards the selected speech language through readiness, transcription, dialogue and synthesis", async () => {
    await show();
    fireEvent.change(screen.getByLabelText("Conversation language"), {
      target: { value: "fr" },
    });
    await flush();
    expect(mocks.api).toHaveBeenCalledWith(
      "/voix/statut?langue=fr",
      "GET",
      undefined,
      expect.any(AbortSignal),
    );
    await click("Record");
    await click("Stop recording");
    await click("Send");
    await click("Listen");
    expect(calls("/voix/transcrire")[0][2]).toMatchObject({ langue: "fr" });
    expect(calls("/assistant/dialogue")[0][2]).toMatchObject({ langue: "fr" });
    expect(mocks.audio).toHaveBeenCalledWith(
      "A synthetic answer.",
      expect.any(AbortSignal),
      "fr",
    );
  });
  it("keeps typed chat available when the speech engine is unavailable", async () => {
    mocks.api.mockImplementation((route: string) =>
      route.startsWith("/voix/statut")
        ? Promise.reject(new Error("Offline"))
        : defaultApi(route),
    );
    await show();
    expect(screen.getByRole("button", { name: "Record" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Start conversation" }),
    ).toBeDisabled();
    await send();
    expect(screen.getByText("A synthetic answer.")).toBeVisible();
  });
  it.each(["escape", "hidden", "unmount"])(
    "stops capture and suppresses transcription after %s",
    async (reason) => {
      const view = await show();
      await click("Record");
      if (reason === "escape") fireEvent.keyDown(window, { key: "Escape" });
      else if (reason === "hidden") {
        vi.spyOn(document, "hidden", "get").mockReturnValue(true);
        fireEvent(document, new Event("visibilitychange"));
      } else view.unmount();
      await flush();
      expect(track.stop).toHaveBeenCalled();
      expect(contexts[0].close).toHaveBeenCalledOnce();
      expect(calls("/voix/transcrire")).toHaveLength(0);
    },
  );
  it("records manually without Web Audio support", async () => {
    vi.stubGlobal("AudioContext", undefined);
    await show();
    await click("Record");
    await click("Stop recording");
    expect(screen.getByLabelText("Your message")).toHaveValue(
      "A synthetic question.",
    );
    expect(contexts).toHaveLength(0);
  });
  it("rejects oversized recordings without uploading them", async () => {
    await show();
    await click("Start conversation");
    act(() =>
      recorders[0].ondataavailable?.({
        data: new Blob([new Uint8Array(8 * 1024 * 1024 + 1)]),
      }),
    );
    await flush();
    expect(screen.getByRole("alert")).toHaveTextContent("exceeds 8 MiB");
    expect(
      screen.getByRole("button", { name: "Start conversation" }),
    ).toBeEnabled();
    expect(contexts[0].close).toHaveBeenCalledOnce();
    expect(calls("/voix/transcrire")).toHaveLength(0);
  });
  it("ends hands-free mode after a recording error", async () => {
    await show();
    await click("Start conversation");
    act(() => recorders[0].onerror?.());
    await flush();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "interrupted the recording",
    );
    expect(
      screen.getByRole("button", { name: "Start conversation" }),
    ).toBeEnabled();
    expect(calls("/voix/transcrire")).toHaveLength(0);
    expect(contexts[0].close).toHaveBeenCalledOnce();
  });
  it("discards a transcription arriving after cancellation", async () => {
    let finish!: (value: unknown) => void;
    mocks.api.mockImplementation((route: string) =>
      route === "/voix/transcrire"
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : defaultApi(route),
    );
    await show();
    await click("Record");
    await click("Stop recording");
    const signal = calls("/voix/transcrire")[0][3] as AbortSignal;
    await click("Stop");
    await act(async () => {
      finish({ texte: "Stale transcription" });
    });
    expect(signal.aborted).toBe(true);
    expect(screen.getByLabelText("Your message")).toHaveValue("");
    expect(calls("/assistant/dialogue")).toHaveLength(0);
  });
  it("preserves an existing draft when a transcript exceeds the message limit", async () => {
    mocks.api.mockImplementation((route: string) =>
      route === "/voix/transcrire"
        ? Promise.resolve({ texte: "x".repeat(4000) })
        : defaultApi(route),
    );
    await show();
    fireEvent.change(screen.getByLabelText("Your message"), {
      target: { value: "Evidence to retain" },
    });
    await click("Record");
    await click("Stop recording");
    expect(screen.getByRole("alert")).toHaveTextContent("4,000-character");
    expect(screen.getByLabelText("Your message")).toHaveValue(
      "Evidence to retain",
    );
  });
});

describe("native PCM playback", () => {
  it("shows a localized French network error when local synthesis fails", async () => {
    mocks.audio.mockRejectedValue(new TypeError("Failed to fetch"));
    await show();
    await send();
    act(() => setLanguage("fr"));
    try {
      await click("Écouter");
      expect(screen.getByRole("alert")).toHaveTextContent("API locale");
      expect(screen.getByRole("alert")).not.toHaveTextContent(
        "Failed to fetch",
      );
      expect(screen.getByRole("alert")).not.toHaveTextContent("The local API");
      expect(players).toHaveLength(0);
    } finally {
      act(() => setLanguage("en"));
    }
  });

  it("aborts pending automatic synthesis when automatic reading is disabled", async () => {
    let finish!: (blob: Blob) => void;
    mocks.audio.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await show();
    fireEvent.click(screen.getByLabelText("Read replies automatically"));
    await send();
    expect(mocks.audio).toHaveBeenCalledOnce();
    const signal = mocks.audio.mock.calls[0][1] as AbortSignal;
    fireEvent.click(screen.getByLabelText("Read replies automatically"));
    await flush();
    expect(signal.aborted).toBe(true);
    await act(async () => {
      finish(pcmBlob());
    });
    expect(players).toHaveLength(0);
    expect(revoke).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Ready when you are");
  });

  it.each([false, true])(
    "uses the current automatic-read preference (%s) when a pending reply arrives",
    async (readWhenReady) => {
      let finish!: (value: { texte: string }) => void;
      mocks.api.mockImplementation((route: string) =>
        route === "/assistant/dialogue"
          ? new Promise((resolve) => {
              finish = resolve;
            })
          : defaultApi(route),
      );
      await show();
      const preference = screen.getByLabelText("Read replies automatically");
      if (!readWhenReady) fireEvent.click(preference);
      await send();
      expect(preference).toBeEnabled();
      fireEvent.click(preference);
      expect(preference).toHaveProperty("checked", readWhenReady);
      await act(async () => {
        finish({ texte: "A deferred synthetic reply." });
      });
      expect(screen.getByText("A deferred synthetic reply.")).toBeVisible();
      if (readWhenReady) {
        expect(mocks.audio).toHaveBeenCalledWith(
          "A deferred synthetic reply.",
          expect.any(AbortSignal),
          "en",
        );
      } else {
        expect(mocks.audio).not.toHaveBeenCalled();
        expect(players).toHaveLength(0);
      }
    },
  );

  it("follows actual playback time and revokes each URL after stop or unmount", async () => {
    const view = await show();
    await send();
    await click("Listen");
    const audio = players[0];
    expect(contexts).toHaveLength(0);
    audio.currentTime = 0.1;
    expect(reader()?.()?.level).toBe(0);
    audio.currentTime = 0.4;
    expect(reader()?.()?.level).toBeCloseTo(0.5);
    audio.paused = true;
    expect(reader()?.()).toBeNull();
    audio.paused = false;
    await click("Stop playback");
    expect(audio.pause).toHaveBeenCalledOnce();
    expect(audio.removeAttribute).toHaveBeenCalledWith("src");
    expect(revoke).toHaveBeenCalledWith("blob:synthetic-1");
    expect(audio.onended).toBeNull();
    await click("Listen");
    view.unmount();
    expect(players[1].pause).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:synthetic-2");
    expect(revoke).toHaveBeenCalledTimes(2);
  });
  it("keeps native playback working with unsupported visual audio data", async () => {
    mocks.audio.mockResolvedValue(
      new Blob(["unsupported"], { type: "audio/wav" }),
    );
    await show();
    await send();
    await click("Listen");
    expect(players[0].play).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("Speaking");
    expect(reader()?.()).toBeNull();
  });
  it("recovers from autoplay refusal and revokes the object URL", async () => {
    playError = new DOMException("Gesture required", "NotAllowedError");
    await show();
    await send();
    await click("Listen");
    expect(screen.getByRole("alert")).toHaveTextContent("requires a click");
    expect(revoke).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Your message")).toBeEnabled();
  });
  it("does not play synthesis arriving after cancellation", async () => {
    let finish!: (blob: Blob) => void;
    mocks.audio.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await show();
    await send();
    await click("Listen");
    const signal = mocks.audio.mock.calls[0][1] as AbortSignal;
    await click("Stop playback");
    await act(async () => {
      finish(pcmBlob());
    });
    expect(signal.aborted).toBe(true);
    expect(players).toHaveLength(0);
    expect(revoke).not.toHaveBeenCalled();
  });
});

describe("explicit bounded hands-free conversation", () => {
  beforeEach(() => vi.useFakeTimers());
  it("prevents concurrent typing through reply preparation, playback and the next-turn delay", async () => {
    let reply!: (value: { texte: string }) => void;
    let speech!: (value: Blob) => void;
    mocks.api.mockImplementation((route: string) =>
      route === "/assistant/dialogue"
        ? new Promise((resolve) => {
            reply = resolve;
          })
        : defaultApi(route),
    );
    mocks.audio.mockImplementation(
      () =>
        new Promise((resolve) => {
          speech = resolve;
        }),
    );
    await show();
    await click("Start conversation");
    expect(
      screen.getByRole("button", { name: "How do I start an analysis?" }),
    ).toBeDisabled();
    await advance(500);
    amplitude = 0;
    await advance(2000);
    const input = screen.getByLabelText("Your message");
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await act(async () => {
      reply({ texte: "A synthetic spoken response." });
    });
    expect(mocks.audio).toHaveBeenCalledOnce();
    expect(input).toBeDisabled();
    await act(async () => {
      speech(pcmBlob());
    });
    expect(screen.getByRole("status")).toHaveTextContent("Speaking");
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await finishPlayback();
    expect(screen.getByRole("status")).toHaveTextContent("Ready when you are");
    expect(input).toBeDisabled();
    await click("End conversation");
    expect(input).toBeEnabled();
    fireEvent.change(input, { target: { value: "New manual evidence." } });
    expect(input).toHaveValue("New manual evidence.");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    await advance(1000);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("completes two speech/silence/reply turns with history and full cleanup", async () => {
    await show();
    await click("Start conversation");
    expect(screen.getByLabelText("Conversation language")).toBeDisabled();
    expect(screen.getByLabelText("Read replies automatically")).toBeDisabled();
    await spokenTurn();
    expect(calls("/assistant/dialogue")).toHaveLength(1);
    expect(contexts[0].close).toHaveBeenCalledOnce();
    await finishPlayback();
    await advance(600);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
    await spokenTurn();
    expect(calls("/assistant/dialogue")[1][2].messages).toEqual([
      { role: "user", content: "A synthetic question." },
      { role: "assistant", content: "A synthetic answer." },
      { role: "user", content: "A synthetic question." },
    ]);
    await click("End conversation");
    await advance(5000);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
    expect(
      contexts.every((context) => context.close.mock.calls.length === 1),
    ).toBe(true);
    expect(revoke).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });
  it("keeps a low or unmeasurable turn for manual review instead of discarding it", async () => {
    amplitude = 0;
    await show();
    await click("Start conversation");
    await advance(12000);
    expect(screen.getByLabelText("Your message")).toHaveValue(
      "A synthetic question.",
    );
    expect(screen.getByLabelText("Your message")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    expect(mocks.notifier).toHaveBeenCalledWith(
      expect.stringContaining("No input signal was detected"),
    );
    expect(calls("/voix/transcrire")).toHaveLength(1);
    expect(calls("/assistant/dialogue")).toHaveLength(0);
    expect(
      screen.queryByRole("button", { name: "End conversation" }),
    ).not.toBeInTheDocument();
    await advance(1);
    expect(vi.getTimerCount()).toBe(0);
  });
  it("completes a quiet but sustained spoken turn below the previous threshold", async () => {
    amplitude = 0.004;
    await show();
    await click("Start conversation");
    await advance(500);
    expect(
      screen.getByRole("meter", { name: "Measured input level" }),
    ).toHaveAttribute("value", expect.stringMatching(/^0\.01/));
    expect(screen.getByText("Input signal detected.")).toBeVisible();
    amplitude = 0;
    await advance(2000);
    expect(calls("/voix/transcrire")).toHaveLength(1);
    expect(calls("/assistant/dialogue")).toHaveLength(1);
  });
  it("explains an empty transcript after silence and never submits a fabricated turn", async () => {
    amplitude = 0;
    mocks.api.mockImplementation((route: string) =>
      route === "/voix/transcrire"
        ? Promise.resolve({ texte: "" })
        : defaultApi(route),
    );
    await show();
    await click("Start conversation");
    await advance(12000);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No speech was detected",
    );
    expect(screen.getByLabelText("Your message")).toHaveValue("");
    expect(calls("/assistant/dialogue")).toHaveLength(0);
    expect(track.stop).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("keeps recording for manual completion when monitoring is suspended", async () => {
    await show();
    await click("Start conversation");
    contexts[0].state = "suspended";
    await advance(1200);
    expect(
      screen.getByText(/The browser paused microphone monitoring/),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Finish recording" }),
    ).toBeEnabled();
    expect(recorders[0].state).toBe("recording");
    expect(calls("/voix/transcrire")).toHaveLength(0);
    await click("Enable microphone monitoring");
    await advance(300);
    expect(contexts[0].resume).toHaveBeenCalledOnce();
    expect(screen.getByText("Input signal detected.")).toBeVisible();
    await click("Finish recording");
    expect(screen.getByLabelText("Your message")).toHaveValue(
      "A synthetic question.",
    );
    expect(calls("/assistant/dialogue")).toHaveLength(0);
  });
  it("stops capture at 90 seconds even if speech never pauses", async () => {
    await show();
    await click("Start conversation");
    await advance(90000);
    expect(recorders[0].state).toBe("inactive");
    expect(calls("/voix/transcrire")).toHaveLength(1);
    expect(contexts[0].close).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("Speaking");
  });
  it("ends after twenty turns without reopening the microphone", async () => {
    await show();
    await click("Start conversation");
    for (let turn = 0; turn < 20; turn++) {
      await spokenTurn();
      await finishPlayback();
      await advance(600);
    }
    expect(calls("/assistant/dialogue")).toHaveLength(20);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(20);
    expect(
      screen.getByRole("button", { name: "Start conversation" }),
    ).toBeEnabled();
    expect(mocks.notifier).toHaveBeenCalledWith(
      expect.stringContaining("20 turns"),
    );
    expect(vi.getTimerCount()).toBe(0);
  });
  it("interrupts playback with Speak now and ignores a stale ended event", async () => {
    await show();
    await click("Start conversation");
    await spokenTurn();
    const staleEnd = players[0].onended;
    await click("Speak now");
    expect(players[0].pause).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledOnce();
    act(() => staleEnd?.());
    await advance(1000);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
  });
  it("cancels a scheduled next turn on unmount", async () => {
    const view = await show();
    await click("Start conversation");
    await spokenTurn();
    await finishPlayback();
    view.unmount();
    await advance(2000);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
  it.each(["transcription", "dialogue", "synthesis"])(
    "stops on %s failure without retrying automatically",
    async (step) => {
      if (step === "synthesis")
        mocks.audio.mockRejectedValue(new Error("Synthetic speech failure"));
      else
        mocks.api.mockImplementation((route: string) =>
          route ===
          (step === "transcription"
            ? "/voix/transcrire"
            : "/assistant/dialogue")
            ? Promise.reject(new Error("Synthetic local failure"))
            : defaultApi(route),
        );
      await show();
      await click("Start conversation");
      await advance(500);
      amplitude = 0;
      await advance(2000);
      expect(screen.getByRole("alert")).toBeVisible();
      const start = screen.getByRole("button", { name: "Start conversation" });
      if (step === "dialogue") {
        expect(start).toBeDisabled();
        expect(screen.getByLabelText("Your message")).toHaveValue(
          "A synthetic question.",
        );
        expect(screen.getByLabelText("Your message")).toBeEnabled();
      } else expect(start).toBeEnabled();
      await advance(5000);
      expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);
    },
  );
});
