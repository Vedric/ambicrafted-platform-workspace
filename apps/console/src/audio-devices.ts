import { useEffect, useRef, type RefObject } from "react";
import { t } from "./i18n";

export const AUDIO_DEVICE_KEY = "ambicrafted-audio-routing-v1";
const defaults = Object.freeze({ inputId: "", outputId: "", processing: true });
/** Retired explicit routing must never override the operating system's defaults. */
export function audioPreferences() {
  try {
    localStorage.removeItem(AUDIO_DEVICE_KEY);
  } catch {
    /* Storage may be blocked. */
  }
  return defaults;
}
export function useAudioPreferences() {
  return audioPreferences();
}
export function microphoneConstraints(): MediaStreamConstraints {
  const { processing } = audioPreferences();
  return {
    audio: {
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
      "Check your system microphone, browser permission and localhost connection, then try again.",
    );
  if (name === "SecurityError")
    return t(
      "Your browser blocked microphone access. Open the platform on localhost.",
    );
  return t(
    "Check your system microphone, browser permission and localhost connection, then try again.",
  );
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
            "Check your system microphone, browser permission and localhost connection, then try again.",
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
/** Ensure an existing player uses the system output. */
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
