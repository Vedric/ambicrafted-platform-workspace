import {
  createContext,
  useEffect,
  useLayoutEffect,
  useSyncExternalStore,
} from "react";

export const MotionPreference = createContext(true);
const query = "(prefers-reduced-motion: reduce)";
function subscribe(notify: () => void) {
  const media = window.matchMedia?.(query);
  media?.addEventListener("change", notify);
  return () => media?.removeEventListener("change", notify);
}
export function useReducedMotionPreference() {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia?.(query).matches ?? false,
    () => true,
  );
}

export function useMotionSettings() {
  const enabled = !useReducedMotionPreference();
  useEffect(() => {
    // Older browser overrides must neither pause motion nor bypass accessibility.
    // Never read them: unavailable storage cannot change the effective preference.
    try {
      localStorage.removeItem("ambicrafted-motion-mode");
      localStorage.removeItem("ambicrafted-motion");
    } catch {
      // Device preference remains authoritative when storage is unavailable.
    }
  }, []);
  useLayoutEffect(() => {
    // CSS, native Web Animations and React motion share the live OS preference.
    delete document.documentElement.dataset.motionMode;
    document.documentElement.dataset.motion = enabled ? "enabled" : "paused";
  }, [enabled]);
  return { enabled };
}
