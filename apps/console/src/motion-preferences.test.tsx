import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  useMotionSettings,
  useReducedMotionPreference,
} from "./motion-preferences";

let media: MediaQueryList;
beforeEach(() => {
  localStorage.clear();
  const events = new EventTarget();
  media = {
    matches: false,
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    dispatchEvent: events.dispatchEvent.bind(events),
  } as MediaQueryList;
  vi.stubGlobal("matchMedia", () => media);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.motion;
  delete document.documentElement.dataset.motionMode;
});
function reduce(value: boolean) {
  act(() => {
    Object.defineProperty(media, "matches", { value, configurable: true });
    media.dispatchEvent(new Event("change"));
  });
}

it("enables motion automatically and follows live device changes without persistence", () => {
  const { result } = renderHook(useMotionSettings);
  expect(result.current.enabled).toBe(true);
  expect(document.documentElement.dataset.motion).toBe("enabled");
  reduce(true);
  expect(result.current.enabled).toBe(false);
  expect(document.documentElement.dataset.motion).toBe("paused");
  reduce(false);
  expect(result.current.enabled).toBe(true);
  expect(localStorage.length).toBe(0);
});

it.each(["paused", "full", "system", "invalid"])(
  "removes obsolete %s overrides without altering appearance or audio preferences",
  (mode) => {
    localStorage.setItem("ambicrafted-motion-mode", mode);
    localStorage.setItem("ambicrafted-motion", "paused");
    localStorage.setItem("ambicrafted-theme", "light");
    localStorage.setItem("ambicrafted-welcome-audio", "off");
    document.documentElement.dataset.motionMode = "full";
    const first = renderHook(useMotionSettings);
    expect(first.result.current.enabled).toBe(true);
    expect(localStorage.getItem("ambicrafted-motion-mode")).toBeNull();
    expect(localStorage.getItem("ambicrafted-motion")).toBeNull();
    expect(document.documentElement.dataset.motionMode).toBeUndefined();
    expect(localStorage.getItem("ambicrafted-theme")).toBe("light");
    expect(localStorage.getItem("ambicrafted-welcome-audio")).toBe("off");
    first.unmount();
    reduce(true);
    expect(renderHook(useMotionSettings).result.current.enabled).toBe(false);
  },
);

it("does not let a saved full override bypass the OS on first render", () => {
  localStorage.setItem("ambicrafted-motion-mode", "full");
  reduce(true);
  expect(renderHook(useMotionSettings).result.current.enabled).toBe(false);
  expect(renderHook(useReducedMotionPreference).result.current).toBe(true);
});

it("honors the device even if storage access and migration are blocked", () => {
  for (const method of ["getItem", "removeItem", "setItem"] as const)
    vi.spyOn(Storage.prototype, method).mockImplementation(() => {
      throw new DOMException("Storage unavailable", "SecurityError");
    });
  const { result } = renderHook(useMotionSettings);
  expect(result.current.enabled).toBe(true);
  reduce(true);
  expect(result.current.enabled).toBe(false);
});

it("ignores obsolete overrides written by another open tab", () => {
  const { result } = renderHook(useMotionSettings);
  act(() => {
    localStorage.setItem("ambicrafted-motion-mode", "paused");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "ambicrafted-motion-mode",
        storageArea: localStorage,
      }),
    );
  });
  expect(result.current.enabled).toBe(true);
  reduce(true);
  act(() => {
    localStorage.setItem("ambicrafted-motion-mode", "full");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "ambicrafted-motion-mode",
        storageArea: localStorage,
      }),
    );
  });
  expect(result.current.enabled).toBe(false);
});
