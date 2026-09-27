import { useEffect } from "react";

type Priority = "speech" | "microphone";
const owners = new Map<symbol, Priority>();
const listeners = new Set<() => void>();

export function audioFocus() {
  return [...owners.values()].includes("microphone")
    ? "microphone"
    : owners.size
      ? "speech"
      : "idle";
}

export function subscribeAudioFocus(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Independent leases avoid one player releasing another player's priority. */
export function claimAudioFocus(priority: Priority) {
  const id = Symbol();
  owners.set(id, priority);
  listeners.forEach((notify) => notify());
  return () => {
    if (owners.delete(id)) listeners.forEach((notify) => notify());
  };
}

export function useAudioFocus(priority: Priority | null) {
  useEffect(
    () => (priority ? claimAudioFocus(priority) : undefined),
    [priority],
  );
}
