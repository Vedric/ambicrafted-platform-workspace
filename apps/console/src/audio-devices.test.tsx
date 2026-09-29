import { afterEach, expect, it, vi } from "vitest";
import {
  AUDIO_DEVICE_KEY,
  applyAudioOutput,
  audioPreferences,
  microphoneConstraints,
  microphoneError,
  playWithAudioOutput,
} from "./audio-devices";
import { setLanguage } from "./i18n";
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  setLanguage("en");
});
function player(sinkId = "") {
  const media = {
    sinkId,
    play: vi.fn(async () => {}),
    setSinkId: vi.fn(async (id: string) => {
      media.sinkId = id;
    }),
  };
  return media as unknown as HTMLMediaElement;
}
it("retires saved device identifiers and always requests system defaults", () => {
  localStorage.setItem(
    AUDIO_DEVICE_KEY,
    JSON.stringify({
      inputId: "unplugged",
      outputId: "retired",
      processing: false,
    }),
  );
  expect(audioPreferences()).toEqual({
    inputId: "",
    outputId: "",
    processing: true,
  });
  expect(localStorage.getItem(AUDIO_DEVICE_KEY)).toBeNull();
  expect(microphoneConstraints()).toEqual({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
    video: false,
  });
});
it("works with unavailable browser storage", () => {
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(audioPreferences().inputId).toBe("");
});
it("preserves gesture activation by calling default playback synchronously", async () => {
  const media = player();
  const pending = playWithAudioOutput(media);
  expect(media.play).toHaveBeenCalledOnce();
  await pending;
  expect(media.setSinkId).not.toHaveBeenCalled();
});
it("resets an existing player to the default sink before playing", async () => {
  const media = player("old-speaker");
  await playWithAudioOutput(media);
  expect(media.setSinkId).toHaveBeenCalledExactlyOnceWith("");
  expect(media.play).toHaveBeenCalledOnce();
});
it("does not play an obsolete response after asynchronous output recovery", async () => {
  const media = player("old-speaker");
  let current = true;
  let finish!: () => void;
  vi.mocked(media.setSinkId).mockImplementation(
    () =>
      new Promise<void>((resolve) => {
        finish = () => {
          Object.defineProperty(media, "sinkId", { value: "" });
          resolve();
        };
      }),
  );
  const pending = playWithAudioOutput(media, () => current);
  await vi.waitFor(() => expect(media.setSinkId).toHaveBeenCalledOnce());
  current = false;
  finish();
  await pending;
  expect(media.play).not.toHaveBeenCalled();
});
it("does not play on an unexpected sink when recovery is denied", async () => {
  const media = player("old-speaker");
  vi.mocked(media.setSinkId).mockRejectedValue(new Error("denied"));
  await expect(playWithAudioOutput(media)).rejects.toThrow();
  expect(media.play).not.toHaveBeenCalled();
});
it("serializes concurrent default recovery without redundant rerouting", async () => {
  const media = player("old-speaker");
  await Promise.all([applyAudioOutput(media), applyAudioOutput(media)]);
  expect(media.setSinkId).toHaveBeenCalledOnce();
});
it("provides actionable permission recovery in both languages", () => {
  setLanguage("en");
  expect(microphoneError({ name: "NotAllowedError" })).toContain(
    "site settings",
  );
  setLanguage("fr");
  expect(microphoneError({ name: "NotFoundError" })).not.toContain(
    "Audio devices",
  );
});
