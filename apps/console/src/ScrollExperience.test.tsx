import { StrictMode } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MotionPreference } from "./motion-preferences";
import { ScrollExperience } from "./ScrollExperience";

class ViewportObserver {
  static instances: ViewportObserver[] = [];
  observed = new Set<Element>();
  disconnected = false;
  constructor(private callback: IntersectionObserverCallback) {
    ViewportObserver.instances.push(this);
  }
  observe = vi.fn((element: Element) => this.observed.add(element));
  unobserve = vi.fn((element: Element) => this.observed.delete(element));
  disconnect = vi.fn(() => {
    this.disconnected = true;
    this.observed.clear();
  });
  show(element: Element, visible = true) {
    act(() => {
      this.callback(
        [
          {
            target: element,
            isIntersecting: visible,
          } as IntersectionObserverEntry,
        ],
        this as unknown as IntersectionObserver,
      );
    });
  }
}

let frames: Map<number, FrameRequestCallback>;
let sequence: number;
let media: MediaQueryList;
let visibility: ReturnType<typeof vi.spyOn>;
let originalAnimate: PropertyDescriptor | undefined;
let animations: { element: HTMLElement; animation: Animation }[];

beforeEach(() => {
  ViewportObserver.instances = [];
  frames = new Map();
  sequence = 0;
  animations = [];
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
  vi.stubGlobal("IntersectionObserver", ViewportObserver);
  vi.stubGlobal("scrollY", 0);
  vi.stubGlobal("innerHeight", 600);
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(
    1800,
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
  originalAnimate = Object.getOwnPropertyDescriptor(
    HTMLElement.prototype,
    "animate",
  );
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    value: vi.fn(function (this: HTMLElement) {
      const animation = {
        cancel: vi.fn(),
        onfinish: null,
        oncancel: null,
      } as unknown as Animation;
      animations.push({ element: this, animation });
      return animation;
    }),
  });
});

afterEach(() => {
  cleanup();
  if (originalAnimate)
    Object.defineProperty(HTMLElement.prototype, "animate", originalAnimate);
  else Reflect.deleteProperty(HTMLElement.prototype, "animate");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function scene(enabled = true, routeKey = "/") {
  return (
    <MotionPreference.Provider value={enabled}>
      <ScrollExperience routeKey={routeKey} />
      <main className="page-scene">
        <section className="panel" data-testid="panel">
          <button>Inspect operational data</button>
          <section className="panel">Nested content remains readable.</section>
        </section>
      </main>
    </MotionPreference.Provider>
  );
}

function observer() {
  return ViewportObserver.instances.at(-1)!;
}

function tick() {
  act(() => {
    for (const [id, callback] of [...frames]) {
      frames.delete(id);
      callback(16);
    }
  });
}

function hidden(value: boolean) {
  act(() => {
    visibility.mockReturnValue(value);
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

describe("scroll accents and operator control", () => {
  it("keeps content readable before observation and animates a visible parent only once", () => {
    render(scene());
    const panel = screen.getByTestId("panel");
    expect(screen.getByRole("button")).toBeVisible();
    expect(animations).toHaveLength(0);
    expect(observer().observed).toEqual(new Set([panel]));
    observer().show(panel);
    observer().show(panel);
    expect(animations).toHaveLength(1);
    expect(animations[0].element).toBe(panel);
  });

  it("cancels motion as a panel leaves the viewport and allows later re-entry", () => {
    render(scene());
    const panel = screen.getByTestId("panel");
    observer().show(panel);
    observer().show(panel, false);
    expect(animations[0].animation.cancel).toHaveBeenCalledTimes(1);
    observer().show(panel);
    expect(animations).toHaveLength(2);
  });
  it("observes sections of tall AURA and Welcome panels independently", () => {
    const { container } = render(
      <MotionPreference.Provider value={true}>
        <ScrollExperience routeKey="/welcome" />
        <main className="landing-main">
          <div className="landing-copy">
            <h1>Welcome</h1>
            <p>Introduction</p>
          </div>
          <section className="welcome-voice">
            <div className="welcome-instrument">AURA</div>
            <div className="welcome-voice-controls">
              <div>Playback controls</div>
              <details>Audio setup</details>
            </div>
          </section>
        </main>
        <main className="page-scene">
          <section className="aura-stage panel">
            <div>Core</div>
            <section className="audio-devices">Microphone setup</section>
          </section>
        </main>
      </MotionPreference.Provider>,
    );
    expect(observer().observed.size).toBe(7);
    expect(
      observer().observed.has(container.querySelector(".aura-stage")!),
    ).toBe(false);
    expect(
      observer().observed.has(container.querySelector(".welcome-voice")!),
    ).toBe(false);
    const setup = container.querySelector<HTMLElement>(".audio-devices")!;
    observer().show(setup);
    expect(animations[0].element).toBe(setup);
    observer().show(setup, false);
    observer().show(setup);
    expect(animations).toHaveLength(2);
  });

  it("never starts motion around focused controls and cancels on focus arrival", () => {
    render(scene());
    const panel = screen.getByTestId("panel");
    const button = screen.getByRole("button");
    act(() => button.focus());
    observer().show(panel);
    expect(animations).toHaveLength(0);
    act(() => button.blur());
    observer().show(panel, false);
    observer().show(panel);
    act(() => button.focus());
    expect(animations[0].animation.cancel).toHaveBeenCalledTimes(1);
    expect(button).toHaveFocus();
  });

  it("cancels active work on pause and reconnects cleanly when resumed", () => {
    const view = render(scene());
    observer().show(screen.getByTestId("panel"));
    window.dispatchEvent(new Event("scroll"));
    const first = observer();
    view.rerender(scene(false));
    expect(first.disconnect).toHaveBeenCalledTimes(1);
    expect(animations[0].animation.cancel).toHaveBeenCalledTimes(1);
    expect(frames.size).toBe(0);
    expect(view.container.querySelector(".scroll-progress")).toBeNull();
    window.dispatchEvent(new Event("scroll"));
    expect(frames.size).toBe(0);
    view.rerender(scene());
    expect(observer()).not.toBe(first);
    expect(observer().observed.has(screen.getByTestId("panel"))).toBe(true);
  });

  it("honors live reduced-motion changes without hiding operational content", () => {
    render(scene());
    observer().show(screen.getByTestId("panel"));
    act(() => {
      Object.defineProperty(media, "matches", {
        configurable: true,
        value: true,
      });
      media.dispatchEvent(new Event("change"));
    });
    expect(animations[0].animation.cancel).toHaveBeenCalledTimes(1);
    expect(observer().disconnected).toBe(true);
    expect(screen.getByRole("button")).toBeVisible();
    window.dispatchEvent(new Event("scroll"));
    expect(frames.size).toBe(0);
  });

  it("does not observe or schedule motion when reduced motion is initially enabled", () => {
    Object.defineProperty(media, "matches", { value: true });
    render(scene());
    expect(ViewportObserver.instances).toHaveLength(0);
    expect(frames.size).toBe(0);
    expect(screen.getByRole("button")).toBeVisible();
  });

  it("cancels hidden-tab work, ignores scroll while hidden, and restores progress", () => {
    const view = render(scene());
    observer().show(screen.getByTestId("panel"));
    window.dispatchEvent(new Event("scroll"));
    hidden(true);
    expect(animations[0].animation.cancel).toHaveBeenCalledTimes(1);
    expect(frames.size).toBe(0);
    window.dispatchEvent(new Event("scroll"));
    observer().show(screen.getByTestId("panel"), false);
    observer().show(screen.getByTestId("panel"));
    expect(frames.size).toBe(0);
    expect(animations).toHaveLength(1);
    vi.stubGlobal("scrollY", 600);
    hidden(false);
    expect(
      view.container
        .querySelector<HTMLElement>(".scroll-progress")!
        .style.getPropertyValue("--page-progress"),
    ).toBe("0.5");
  });

  it("coalesces scroll events into one frame and clamps overscroll progress", () => {
    const view = render(scene());
    for (let index = 0; index < 20; index++)
      window.dispatchEvent(new Event("scroll"));
    expect(frames.size).toBe(1);
    vi.stubGlobal("scrollY", 2400);
    tick();
    const bar = view.container.querySelector<HTMLElement>(".scroll-progress")!;
    expect(bar).toHaveAttribute("aria-hidden", "true");
    expect(bar.style.getPropertyValue("--page-progress")).toBe("1");
    expect(frames.size).toBe(0);
    vi.stubGlobal("scrollY", -30);
    window.dispatchEvent(new Event("scroll"));
    tick();
    expect(bar.style.getPropertyValue("--page-progress")).toBe("0");
  });

  it("collects dynamically loaded panels and releases removed nodes", async () => {
    render(scene());
    const panel = screen.getByTestId("panel");
    const added = document.createElement("section");
    added.className = "panel";
    panel.parentElement!.append(added);
    await waitFor(() => expect(observer().observed.has(added)).toBe(true));
    observer().show(added);
    added.remove();
    await waitFor(() => expect(observer().observed.has(added)).toBe(false));
    expect(animations[0].animation.cancel).toHaveBeenCalledTimes(1);
  });

  it("bounds observed nodes while leaving every panel available", async () => {
    render(scene());
    const main = screen.getByTestId("panel").parentElement!;
    for (let index = 0; index < 150; index++) {
      const panel = document.createElement("section");
      panel.className = "panel";
      main.append(panel);
    }
    await waitFor(() => expect(observer().observed.size).toBe(120));
    expect(main.children).toHaveLength(151);
  });

  it("releases route and StrictMode subscriptions and stops all work on unmount", () => {
    const view = render(<StrictMode>{scene()}</StrictMode>);
    expect(
      ViewportObserver.instances.filter((item) => !item.disconnected),
    ).toHaveLength(1);
    const first = observer();
    first.show(screen.getByTestId("panel"));
    view.rerender(<StrictMode>{scene(true, "/architecture")}</StrictMode>);
    expect(first.disconnected).toBe(true);
    expect(animations[0].animation.cancel).toHaveBeenCalledTimes(1);
    observer().show(screen.getByTestId("panel"));
    window.dispatchEvent(new Event("scroll"));
    view.unmount();
    expect(ViewportObserver.instances.every((item) => item.disconnected)).toBe(
      true,
    );
    expect(animations[1].animation.cancel).toHaveBeenCalledTimes(1);
    expect(frames.size).toBe(0);
    window.dispatchEvent(new Event("scroll"));
    window.dispatchEvent(new Event("resize"));
    expect(frames.size).toBe(0);
  });

  it("degrades to readable static content without browser animation support", () => {
    Reflect.deleteProperty(HTMLElement.prototype, "animate");
    render(scene());
    expect(ViewportObserver.instances).toHaveLength(0);
    expect(screen.getByRole("button")).toBeVisible();
    expect(frames.size).toBe(0);
  });
});
