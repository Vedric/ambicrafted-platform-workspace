import { useEffect, useRef, useSyncExternalStore, type RefObject } from "react";
import { t } from "./i18n";

export const AUDIO_DEVICE_KEY = "ambicrafted-audio-routing-v1";
const EVENT = "ambicrafted-audio-routing";
type Preferences = { inputId: string; outputId: string; processing: boolean };
const defaults: Preferences = { inputId: "", outputId: "", processing: true };
let snapshot = defaults;
let previous: string | null | undefined;
let memory = defaults;
let sessionOnly = false;

/** Device IDs stay in this browser; never send them to the API or logs. */
export function audioPreferences(): Preferences {
  if (sessionOnly) return memory;
  let raw: string | null;
  try {
    raw = localStorage.getItem(AUDIO_DEVICE_KEY);
  } catch {
    return memory;
  }
  if (raw === previous) return snapshot;
  previous = raw;
  try {
    const value = JSON.parse(raw || "null");
    const id = (v: unknown) =>
      typeof v === "string" && v.length <= 1024 ? v : "";
    snapshot =
      value && typeof value === "object"
        ? {
            inputId: id(value.inputId),
            outputId: id(value.outputId),
            processing: value.processing !== false,
          }
        : defaults;
  } catch {
    snapshot = defaults;
  }
  return snapshot;
}
export function saveAudioPreferences(change: Partial<Preferences>) {
  memory = { ...audioPreferences(), ...change };
  try {
    localStorage.setItem(AUDIO_DEVICE_KEY, JSON.stringify(memory));
    sessionOnly = false;
  } catch {
    sessionOnly = true;
  }
  window.dispatchEvent(new Event(EVENT));
}
function subscribe(notify: () => void) {
  const changed = (event: StorageEvent) => {
    if (event.key === AUDIO_DEVICE_KEY || event.key === null) notify();
  };
  window.addEventListener(EVENT, notify);
  window.addEventListener("storage", changed);
  return () => {
    window.removeEventListener(EVENT, notify);
    window.removeEventListener("storage", changed);
  };
}
export function useAudioPreferences() {
  return useSyncExternalStore(subscribe, audioPreferences);
}
export function microphoneConstraints(): MediaStreamConstraints {
  const { inputId, processing } = audioPreferences();
  return {
    audio: {
      ...(inputId ? { deviceId: { exact: inputId } } : {}),
      echoCancellation: processing,
      noiseSuppression: processing,
      autoGainControl: processing,
    },
    video: false,
  };
}
export function microphoneError(cause: unknown): string {
  const name =
    cause && typeof cause === "object" && "name" in cause ? cause.name : "";
  if (name === "NotAllowedError")
    return t(
      "Microphone access was denied. Allow access in your browser’s site settings.",
    );
  if (name === "NotReadableError")
    return t("The microphone is unavailable or in use by another application.");
  if (name === "OverconstrainedError" || name === "NotFoundError")
    return t(
      "The selected microphone is unavailable. Connect it or choose another input in Audio devices.",
    );
  if (name === "SecurityError")
    return t(
      "Your browser blocked microphone access. Open the platform on localhost.",
    );
  return t(
    "Check your system microphone, browser permission and localhost connection, then try again.",
  );
}
export function outputSelectionSupported() {
  return typeof HTMLMediaElement.prototype.setSinkId === "function";
}
const queues = new WeakMap<HTMLMediaElement, Promise<void>>();
export function applyAudioOutput(media: HTMLMediaElement): Promise<void> {
  const outputId = audioPreferences().outputId;
  if (!queues.has(media) && (media.sinkId || "") === outputId)
    return Promise.resolve();
  const pending = (queues.get(media) || Promise.resolve())
    .catch(() => {})
    .then(async () => {
      if ((media.sinkId || "") === outputId) return;
      if (typeof media.setSinkId !== "function")
        throw new Error(
          t(
            "This browser cannot select speakers. Choose System default and select the output in your operating system.",
          ),
        );
      try {
        await media.setSinkId(outputId);
      } catch {
        throw new Error(
          t(
            "The selected output is unavailable or not permitted. Choose another speaker or authorize it in Audio devices.",
          ),
        );
      }
    });
  queues.set(media, pending);
  const release = () => {
    if (queues.get(media) === pending) queues.delete(media);
  };
  void pending.then(release, release);
  return pending;
}
/** Preserve synchronous play on the default path for browser gesture activation. */
export function playWithAudioOutput(
  media: HTMLMediaElement,
  current: () => boolean = () => true,
): Promise<void> {
  if (!current()) return Promise.resolve();
  if (
    !queues.has(media) &&
    (media.sinkId || "") === audioPreferences().outputId
  )
    return media.play();
  return applyAudioOutput(media).then(() =>
    playWithAudioOutput(media, current),
  );
}
/** Also route players that are already playing when the selection changes. */
export function useAudioOutput(
  ref: RefObject<HTMLMediaElement | null>,
  failed: (error: Error) => void,
) {
  const { outputId } = useAudioPreferences();
  const callback = useRef(failed);
  callback.current = failed;
  useEffect(() => {
    let active = true;
    const media = ref.current;
    if (media)
      void applyAudioOutput(media).catch((error: Error) => {
        if (active) {
          media.pause();
          callback.current(error);
        }
      });
    return () => {
      active = false;
    };
  }, [outputId, ref]);
}
