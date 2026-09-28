import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  MotionModePreference,
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

it("follows live device changes by default without storing an explicit choice", () => {
  localStorage.setItem("ambicrafted-motion", "enabled");
  const { result } = renderHook(useMotionSettings);
  expect(result.current.mode).toBe("system");
  expect(result.current.enabled).toBe(true);
  reduce(true);
  expect(result.current.enabled).toBe(false);
  expect(document.documentElement.dataset.motion).toBe("paused");
  reduce(false);
  expect(result.current.enabled).toBe(true);
  expect(document.documentElement.dataset.motion).toBe("enabled");
  expect(localStorage.getItem("ambicrafted-motion-mode")).toBeNull();
});

it("honors an explicit full selection, persists it and can return to system mode", () => {
  reduce(true);
  const first = renderHook(useMotionSettings);
  act(() => first.result.current.setMode("full"));
  expect(first.result.current.enabled).toBe(true);
  expect(document.documentElement.dataset.motionMode).toBe("full");
  first.unmount();
  const { result } = renderHook(useMotionSettings);
  expect(result.current.mode).toBe("full");
  expect(result.current.enabled).toBe(true);
  act(() => result.current.setMode("system"));
  expect(result.current.enabled).toBe(false);
  reduce(false);
  expect(result.current.enabled).toBe(true);
});

it("preserves a previous pause until an explicit selection takes precedence", () => {
  localStorage.setItem("ambicrafted-motion", "paused");
  const first = renderHook(useMotionSettings);
  expect(first.result.current.mode).toBe("paused");
  reduce(true);
  reduce(false);
  expect(first.result.current.enabled).toBe(false);
  act(() => first.result.current.setMode("full"));
  first.unmount();
  const { result } = renderHook(useMotionSettings);
  expect(result.current.enabled).toBe(true);
  act(() => result.current.setMode("paused"));
  reduce(true);
  reduce(false);
  expect(result.current.enabled).toBe(false);
});

it("ignores invalid saved values and remains usable when persistence fails", () => {
  localStorage.setItem("ambicrafted-motion-mode", "invalid");
  const { result } = renderHook(useMotionSettings);
  expect(result.current.mode).toBe("system");
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("Storage unavailable", "SecurityError");
  });
  act(() => result.current.setMode("full"));
  reduce(true);
  expect(result.current.enabled).toBe(true);
  act(() => result.current.setMode("paused"));
  expect(result.current.enabled).toBe(false);
});

it("defaults safely when saved preferences cannot be read", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("Storage unavailable", "SecurityError");
  });
  reduce(true);
  const { result } = renderHook(useMotionSettings);
  expect(result.current.mode).toBe("system");
  expect(result.current.enabled).toBe(false);
});

it("synchronizes explicit preferences and a storage reset from another tab", () => {
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
  expect(result.current.enabled).toBe(false);
  act(() => {
    sessionStorage.setItem("ambicrafted-motion-mode", "full");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "ambicrafted-motion-mode",
        storageArea: sessionStorage,
      }),
    );
  });
  expect(result.current.mode).toBe("paused");
  act(() => {
    localStorage.clear();
    window.dispatchEvent(
      new StorageEvent("storage", { key: null, storageArea: localStorage }),
    );
  });
  expect(result.current.mode).toBe("system");
  expect(result.current.enabled).toBe(true);
});

it("applies the full override to component hooks while retaining the system default", () => {
  reduce(true);
  const automatic = renderHook(useReducedMotionPreference);
  expect(automatic.result.current).toBe(true);
  const full = renderHook(useReducedMotionPreference, {
    wrapper: ({ children }) => (
      <MotionModePreference.Provider value="full">
        {children}
      </MotionModePreference.Provider>
    ),
  });
  expect(full.result.current).toBe(false);
});
