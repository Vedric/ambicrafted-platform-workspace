import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  useSyncExternalStore,
} from "react";

export const MotionPreference = createContext(true);
export type MotionMode = "system" | "full" | "paused";
export const MotionModePreference = createContext<MotionMode>("system");
const storageKey = "ambicrafted-motion-mode";
const legacyKey = "ambicrafted-motion";
const query = "(prefers-reduced-motion: reduce)";
function subscribe(notify: () => void) {
  const media = window.matchMedia?.(query);
  media?.addEventListener("change", notify);
  return () => media?.removeEventListener("change", notify);
}
export function useSystemReducedMotionPreference() {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia?.(query).matches ?? false,
    () => true,
  );
}

export function useReducedMotionPreference() {
  const mode = useContext(MotionModePreference);
  const reduced = useSystemReducedMotionPreference();
  return mode !== "full" && reduced;
}

function readMode(): MotionMode {
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved === "system" || saved === "full" || saved === "paused")
      return saved;
    // Previous versions wrote "enabled" automatically on every visit. It is
    // not evidence of an explicit choice to override the device preference.
    return localStorage.getItem(legacyKey) === "paused" ? "paused" : "system";
  } catch {
    return "system";
  }
}

export function useMotionSettings() {
  const [mode, updateMode] = useState<MotionMode>(readMode);
  const reduced = useSystemReducedMotionPreference();
  const enabled = mode === "full" || (mode === "system" && !reduced);
  const setMode = useCallback((value: MotionMode) => {
    updateMode(value);
    try {
      localStorage.setItem(storageKey, value);
    } catch {
      // The current tab stays usable when browser storage is unavailable.
    }
  }, []);
  useEffect(() => {
    const synchronize = (event: StorageEvent) => {
      if (
        (event.key === null ||
          event.key === storageKey ||
          event.key === legacyKey) &&
        (!event.storageArea || event.storageArea === localStorage)
      )
        updateMode(readMode());
    };
    window.addEventListener("storage", synchronize);
    return () => window.removeEventListener("storage", synchronize);
  }, []);
  useLayoutEffect(() => {
    // CSS, native Web Animations and React motion use the same effective state.
    document.documentElement.dataset.motionMode = mode;
    document.documentElement.dataset.motion = enabled ? "enabled" : "paused";
  }, [mode, enabled]);
  return { mode, setMode, enabled };
}
