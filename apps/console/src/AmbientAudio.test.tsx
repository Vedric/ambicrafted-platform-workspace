import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AmbientAudioControl, AmbientAudioProvider } from "./AmbientAudio";
import { claimAudioFocus } from "./audio-focus";
import { setLanguage } from "./i18n";

const players: FakeAudio[] = [];
let denied = false;
const releases: (() => void)[] = [];
class FakeAudio {
  loop = false;
  preload = "";
  volume = 1;
  paused = true;
  onerror: (() => void) | null = null;
  pause = vi.fn(() => {
    this.paused = true;
  });
  removeAttribute = vi.fn();
  load = vi.fn();
  play = vi.fn(async () => {
    if (denied) throw new DOMException("gesture needed", "NotAllowedError");
    this.paused = false;
  });
  constructor(public src: string) {
    players.push(this);
  }
}
function mount() {
  return render(
    <AmbientAudioProvider>
      <AmbientAudioControl expanded />
    </AmbientAudioProvider>,
  );
}
async function start() {
  fireEvent.click(screen.getByRole("button", { name: "Play ambient music" }));
  await waitFor(() => expect(players[0]?.paused).toBe(false));
  return players[0];
}
beforeEach(() => {
  localStorage.clear();
  setLanguage("en");
  players.length = 0;
  denied = false;
  vi.stubGlobal("Audio", FakeAudio);
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: false,
  });
});
afterEach(() => {
  cleanup();
  releases.splice(0).forEach((release) => release());
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("requires an explicit first choice, caps volume and releases the media resource", async () => {
  const view = mount();
  expect(players).toHaveLength(0);
  const audio = await start();
  expect(audio.src).toBe("/audio/orbital-drift.mp3");
  expect(audio.loop).toBe(true);
  fireEvent.change(screen.getByRole("slider"), { target: { value: "99" } });
  expect(screen.getByRole("slider")).toHaveValue("22");
  view.unmount();
  expect(audio.pause).toHaveBeenCalled();
  expect(audio.removeAttribute).toHaveBeenCalledWith("src");
});

it("ducks before speech, silences recording and retains other speakers' priority", async () => {
  mount();
  const audio = await start();
  vi.useFakeTimers();
  let first!: () => void;
  let second!: () => void;
  let mic!: () => void;
  act(() => {
    first = claimAudioFocus("speech");
    second = claimAudioFocus("speech");
  });
  releases.push(first, second);
  expect(audio.volume).toBeCloseTo(0.12 * 0.08);
  act(() => {
    mic = claimAudioFocus("microphone");
  });
  releases.push(mic);
  expect(audio.volume).toBe(0);
  act(() => {
    first();
    mic();
    vi.advanceTimersByTime(1500);
  });
  expect(audio.volume).toBeCloseTo(0.12 * 0.08);
  act(() => {
    second();
    vi.advanceTimersByTime(500);
  });
  expect(audio.volume).toBeGreaterThan(0.12 * 0.08);
  expect(audio.volume).toBeLessThan(0.12);
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  expect(audio.volume).toBeCloseTo(0.12);
});

it("recovers from blocked autoplay only with the visible play control", async () => {
  localStorage.setItem(
    "ambicrafted-ambient",
    JSON.stringify({ enabled: true, volume: 100 }),
  );
  denied = true;
  mount();
  await screen.findByText(
    "Select Play ambient music to allow audio in this browser.",
  );
  expect(players[0].volume).toBeLessThanOrEqual(0.22);
  denied = false;
  await start();
  await waitFor(() =>
    expect(
      screen.queryByText(
        "Select Play ambient music to allow audio in this browser.",
      ),
    ).not.toBeInTheDocument(),
  );
});

it("pauses in the background, resumes on return, and Escape persists an off preference", async () => {
  mount();
  const audio = await start();
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: true,
  });
  fireEvent(document, new Event("visibilitychange"));
  expect(audio.paused).toBe(true);
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: false,
  });
  fireEvent(document, new Event("visibilitychange"));
  await waitFor(() => expect(audio.paused).toBe(false));
  fireEvent.keyDown(window, { key: "Escape" });
  expect(audio.paused).toBe(true);
  expect(JSON.parse(localStorage.getItem("ambicrafted-ambient")!).enabled).toBe(
    false,
  );
});

it("gives guide videos priority and releases removed video elements", async () => {
  mount();
  const audio = await start();
  const video = document.createElement("video");
  document.body.append(video);
  fireEvent.play(video);
  expect(audio.volume).toBeCloseTo(0.12 * 0.08);
  video.remove();
  await act(async () => {});
  await waitFor(() => expect(audio.volume).toBeCloseTo(0.12), {
    timeout: 2000,
  });
});
