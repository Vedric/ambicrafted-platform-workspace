import type { Page } from "@playwright/test";

declare global { interface Window { __nativeAudio: HTMLAudioElement[] } }

/** Observe real browser decoding/playback, without mocking the media methods. */
export async function observeAudio(page: Page) {
  await page.addInitScript(() => {
    const NativeAudio = window.Audio;
    window.__nativeAudio = [];
    window.Audio = function (src?: string) {
      const audio = new NativeAudio(src);
      window.__nativeAudio.push(audio);
      return audio;
    } as unknown as typeof Audio;
    window.Audio.prototype = NativeAudio.prototype;
  });
}

export async function ambientState(page: Page) {
  return page.evaluate(() => {
    const audio = window.__nativeAudio.find((element) => element.src.endsWith("orbital-drift.mp3"));
    return audio ? { volume: audio.volume, paused: audio.paused, time: audio.currentTime, duration: audio.duration, error: audio.error?.code || null } : null;
  });
}
