import { StrictMode, type RefObject } from "react";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NeuralCore, type CorePhase } from "./NeuralCore";
import { MotionPreference } from "./motion-preferences";
import { waveform, type SignalReader } from "./audio-signal";

const viewport = vi.hoisted(() => ({ visible: true }));
vi.mock("motion/react", () => ({ useInView: () => viewport.visible }));

let sequence = 0;
let frames: Map<number, FrameRequestCallback>;
let media: MediaQueryList;
let visibility: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  sequence = 0;
  frames = new Map();
  viewport.visible = true;
  visibility = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  const events = new EventTarget();
  media = {
    matches: false,
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    dispatchEvent: events.dispatchEvent.bind(events),
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => media),
  );
  vi.stubGlobal(
    "requestAnimationFrame",
    vi.fn((callback: FrameRequestCallback) => {
      const id = ++sequence;
      frames.set(id, callback);
      return id;
    }),
  );
  vi.stubGlobal(
    "cancelAnimationFrame",
    vi.fn((id: number) => frames.delete(id)),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function tick(time: number) {
  act(() => {
    const pending = [...frames.entries()];
    for (const [id, callback] of pending) {
      frames.delete(id);
      callback(time);
    }
  });
}

function reduced(value: boolean) {
  act(() => {
    Object.defineProperty(media, "matches", { configurable: true, value });
    media.dispatchEvent(new Event("change"));
  });
}

function hidden(value: boolean) {
  act(() => {
    visibility.mockReturnValue(value);
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

function show({
  phase = "listening",
  enabled = true,
  signal = { current: null },
}: {
  phase?: CorePhase;
  enabled?: boolean;
  signal?: RefObject<SignalReader | null>;
} = {}) {
  return (
    <MotionPreference.Provider value={enabled}>
      <NeuralCore phase={phase} signal={signal} />
    </MotionPreference.Provider>
  );
}

describe("real audio visualization", () => {
  it("changes the outline with measured samples and returns to silence", () => {
    const reader = vi.fn(() => waveform(new Float32Array(480)));
    const signal = { current: reader };
    const { container } = render(show({ signal }));
    const core = container.querySelector<HTMLElement>(".neural-core")!;
    const path = container.querySelector(".core-signal")!;
    const resting = path.getAttribute("d");
    tick(40);
    expect(core).toHaveAttribute("data-signal", "measured");
    expect(core.style.getPropertyValue("--signal")).toBe("0");
    expect(path.getAttribute("d")).toBe(resting);
    reader.mockReturnValue(waveform(new Float32Array(480).fill(0.125)));
    tick(80);
    expect(Number(core.style.getPropertyValue("--signal"))).toBeCloseTo(0.5);
    expect(path.getAttribute("d")).not.toBe(resting);
    reader.mockReturnValue(waveform(new Float32Array(480)));
    tick(120);
    expect(path.getAttribute("d")).toBe(resting);
  });

  it("reads the current signal ref instead of retaining a replaced reader", () => {
    const previous = vi.fn(() => waveform(new Float32Array(480)));
    const next = vi.fn(() => waveform(new Float32Array(480).fill(0.125)));
    const signal: RefObject<SignalReader | null> = { current: previous };
    render(show({ phase: "speaking", signal }));
    tick(40);
    signal.current = next;
    tick(80);
    expect(previous).toHaveBeenCalledTimes(1);
    expect(next).toHaveBeenCalledTimes(1);
  });

  it("uses a static fallback for unavailable audio without fabricated levels", () => {
    const { container } = render(show());
    const core = container.querySelector<HTMLElement>(".neural-core")!;
    tick(40);
    expect(core).toHaveAttribute("data-signal", "unavailable");
    expect(core.style.getPropertyValue("--signal")).toBe("0");
  });

  it("bounds sampling frequency while keeping at most one scheduled frame", () => {
    const reader = vi.fn(() => null);
    render(show({ signal: { current: reader } }));
    for (let index = 1; index <= 60; index++) {
      expect(frames.size).toBe(1);
      tick((index * 1000) / 60);
    }
    expect(reader.mock.calls.length).toBeGreaterThanOrEqual(20);
    expect(reader.mock.calls.length).toBeLessThanOrEqual(30);
    expect(frames.size).toBe(1);
  });

  it.each(["idle", "thinking", "loading"] as const)(
    "does not poll an audio reader while %s",
    (phase) => {
      const reader = vi.fn(() => null);
      render(show({ phase, signal: { current: reader } }));
      tick(1000);
      expect(reader).not.toHaveBeenCalled();
      expect(frames.size).toBe(0);
    },
  );
});

describe("motion preferences and resource lifecycle", () => {
  it("stops sampling and clears the signal on user pause, then resumes", () => {
    const signal = {
      current: vi.fn(() => waveform(new Float32Array(480).fill(0.125))),
    };
    const view = render(show({ signal }));
    const core = view.container.querySelector<HTMLElement>(".neural-core")!;
    tick(40);
    view.rerender(show({ signal, enabled: false }));
    expect(frames.size).toBe(0);
    expect(core).toHaveAttribute("data-resting", "true");
    expect(core.style.getPropertyValue("--signal")).toBe("0");
    tick(80);
    expect(signal.current).toHaveBeenCalledTimes(1);
    view.rerender(show({ signal, enabled: true }));
    expect(frames.size).toBe(1);
    tick(120);
    expect(signal.current).toHaveBeenCalledTimes(2);
  });

  it("reacts immediately to live operating-system reduced-motion changes", () => {
    const reader = vi.fn(() => null);
    const { container } = render(show({ signal: { current: reader } }));
    const core = container.querySelector(".neural-core")!;
    reduced(true);
    expect(core).toHaveAttribute("data-resting", "true");
    expect(frames.size).toBe(0);
    tick(100);
    expect(reader).not.toHaveBeenCalled();
    reduced(false);
    expect(core).toHaveAttribute("data-resting", "false");
    expect(frames.size).toBe(1);
    tick(200);
    expect(reader).toHaveBeenCalledTimes(1);
  });

  it("honors reduced motion before the first animation frame", () => {
    reduced(true);
    render(show());
    expect(frames.size).toBe(0);
  });

  it("suspends a hidden tab and restarts only after it becomes visible", () => {
    const reader = vi.fn(() => null);
    render(show({ signal: { current: reader } }));
    hidden(true);
    expect(frames.size).toBe(0);
    tick(100);
    expect(reader).not.toHaveBeenCalled();
    hidden(false);
    expect(frames.size).toBe(1);
    tick(200);
    expect(reader).toHaveBeenCalledTimes(1);
  });

  it("does not schedule frames when mounted in a hidden tab", () => {
    visibility.mockReturnValue(true);
    render(show());
    expect(frames.size).toBe(0);
  });

  it("suspends offscreen work and keeps a user pause after re-entry", () => {
    const signal = { current: vi.fn(() => null) };
    const view = render(show({ signal }));
    viewport.visible = false;
    view.rerender(show({ signal }));
    expect(frames.size).toBe(0);
    viewport.visible = true;
    view.rerender(show({ signal, enabled: false }));
    expect(frames.size).toBe(0);
    view.rerender(show({ signal, enabled: true }));
    expect(frames.size).toBe(1);
  });

  it("cancels the pending callback on phase changes and unmount", () => {
    const signal = { current: vi.fn(() => null) };
    const view = render(show({ signal }));
    view.rerender(show({ signal, phase: "idle" }));
    expect(frames.size).toBe(0);
    view.rerender(show({ signal, phase: "speaking" }));
    expect(frames.size).toBe(1);
    view.unmount();
    expect(frames.size).toBe(0);
    tick(1000);
    expect(signal.current).not.toHaveBeenCalled();
  });

  it("does not leak callbacks or visibility listeners across StrictMode mounts", () => {
    const removed = vi.spyOn(document, "removeEventListener");
    for (let index = 0; index < 10; index++) {
      const view = render(<StrictMode>{show()}</StrictMode>);
      expect(frames.size).toBe(1);
      view.unmount();
      expect(frames.size).toBe(0);
    }
    expect(removed).toHaveBeenCalledWith(
      "visibilitychange",
      expect.any(Function),
    );
    hidden(true);
    reduced(true);
    expect(frames.size).toBe(0);
  });

  it("keeps decorative content out of the accessibility tree and uses unique SVG IDs", () => {
    const { container } = render(
      <>
        {show()}
        {show({ enabled: false })}
      </>,
    );
    const cores = container.querySelectorAll(".neural-core");
    expect(cores).toHaveLength(2);
    cores.forEach((core) =>
      expect(core).toHaveAttribute("aria-hidden", "true"),
    );
    expect(container.querySelectorAll("button, a, [tabindex]")).toHaveLength(0);
    const ids = [...container.querySelectorAll("[id]")].map(
      (element) => element.id,
    );
    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
