/** Always follow the operating system. Saved experimental device IDs are ignored. */
export async function applyAudioOutput(audio: HTMLMediaElement): Promise<void> {
  if ("setSinkId" in audio && typeof audio.setSinkId === "function")
    await audio.setSinkId("default");
}
