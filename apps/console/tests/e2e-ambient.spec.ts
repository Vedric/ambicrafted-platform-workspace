import { expect, test } from "@playwright/test";
import { ambientState, observeAudio } from "./audio-observer";

test("native ambient playback stays under the welcome, returns gently and follows the operator's stop", async ({ page }) => {
  await observeAudio(page);
  await page.addInitScript(() => localStorage.setItem("ambicrafted-welcome-audio", "off"));
  await page.goto("/welcome");
  await page.getByRole("button", { name: "Play ambient music", exact: true }).click();
  await expect.poll(async () => (await ambientState(page))?.time).toBeGreaterThan(.2);
  const playing = await ambientState(page);
  expect(playing?.duration).toBeGreaterThan(95);
  expect(playing?.volume).toBeCloseTo(.12);
  expect(playing?.error).toBeNull();
  await page.getByRole("button", { name: "Listen to my welcome", exact: true }).click();
  await expect(page.getByText("AURA is speaking", { exact: true })).toBeVisible();
  await expect.poll(async () => (await ambientState(page))?.volume).toBeCloseTo(.0096);
  await page.getByRole("button", { name: "Stop audio", exact: true }).click();
  await expect.poll(async () => (await ambientState(page))?.volume).toBeCloseTo(.12);
  await page.getByRole("button", { name: "Pause ambient music", exact: true }).click();
  expect((await ambientState(page))?.paused).toBe(true);
  await page.reload();
  await expect(page.getByRole("button", { name: "Play ambient music", exact: true })).toBeVisible();
  expect(await ambientState(page)).toBeNull();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
