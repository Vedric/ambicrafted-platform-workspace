import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AudioDevices } from "./AudioDevices";
import {
  AUDIO_DEVICE_KEY,
  applyAudioOutput,
  audioPreferences,
  microphoneConstraints,
  playWithAudioOutput,
  saveAudioPreferences,
} from "./audio-devices";
import { audioFocus } from "./audio-focus";
import { setLanguage } from "./i18n";

const original = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
const originalSink = Object.getOwnPropertyDescriptor(
  HTMLMediaElement.prototype,
  "setSinkId",
);
let devices: MediaDeviceInfo[];
let media: EventTarget & {
  enumerateDevices: ReturnType<typeof vi.fn>;
  getUserMedia: ReturnType<typeof vi.fn>;
  selectAudioOutput?: ReturnType<typeof vi.fn>;
};
let players: Player[];
const track = { stop: vi.fn() };
const stream = { getTracks: () => [track] };
function device(
  kind: MediaDeviceKind,
  deviceId: string,
  label: string,
): MediaDeviceInfo {
  return { kind, deviceId, label, groupId: "synthetic", toJSON: () => ({}) };
}
class Player {
  sinkId = "";
  volume = 1;
  paused = true;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public src = "") {
    players.push(this);
  }
  setSinkId = vi.fn(async (id: string) => {
    this.sinkId = id;
  });
  play = vi.fn(async () => {
    this.paused = false;
  });
  pause = vi.fn(() => {
    this.paused = true;
  });
  removeAttribute = vi.fn();
  load = vi.fn();
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  setLanguage("en");
  saveAudioPreferences({ inputId: "", outputId: "", processing: true });
  players = [];
  devices = [
    device("audioinput", "mic-usb", "USB microphone"),
    device("audioinput", "mic-webcam", "Camera microphone"),
    device("audiooutput", "headset", "USB headset"),
    device("audiooutput", "display", "Display speakers"),
  ];
  media = Object.assign(new EventTarget(), {
    enumerateDevices: vi.fn(async () => devices),
    getUserMedia: vi.fn(async () => stream),
  });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: media,
  });
  Object.defineProperty(HTMLMediaElement.prototype, "setSinkId", {
    configurable: true,
    value: vi.fn(),
  });
  vi.stubGlobal("Audio", Player);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  if (original) Object.defineProperty(navigator, "mediaDevices", original);
  else Reflect.deleteProperty(navigator, "mediaDevices");
  if (originalSink)
    Object.defineProperty(
      HTMLMediaElement.prototype,
      "setSinkId",
      originalSink,
    );
  else Reflect.deleteProperty(HTMLMediaElement.prototype, "setSinkId");
});
const flush = () =>
  act(async () => {
    await Promise.resolve();
  });
async function show() {
  const active = vi.fn();
  const view = render(
    <AudioDevices disabled={false} onActiveChange={active} />,
  );
  await flush();
  return { ...view, active };
}

describe("explicit browser audio routing", () => {
  it("enumerates without opening the microphone and applies the selected exact input", async () => {
    await show();
    expect(media.getUserMedia).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Microphone input"), {
      target: { value: "mic-usb" },
    });
    fireEvent.click(screen.getByLabelText("Voice processing"));
    expect(microphoneConstraints()).toEqual({
      audio: {
        deviceId: { exact: "mic-usb" },
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
      video: false,
    });
    expect(JSON.parse(localStorage.getItem(AUDIO_DEVICE_KEY)!)).toEqual({
      inputId: "mic-usb",
      outputId: "",
      processing: false,
    });
    expect(media.getUserMedia).not.toHaveBeenCalled();
  });
  it("releases discovery capture immediately and refreshes the permitted inventory", async () => {
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Detect devices" }));
    await flush();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(
      screen.getByRole("button", { name: "Detect devices" }),
    ).toBeEnabled();
    expect(media.enumerateDevices).toHaveBeenCalledTimes(2);
  });
  it("a late permission grant after cancellation is stopped without changing the selection", async () => {
    let resolve!: (s: typeof stream) => void;
    media.getUserMedia.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const { active } = await show();
    fireEvent.click(screen.getByRole("button", { name: "Detect devices" }));
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "Cancel audio setup" }));
    await act(async () => resolve(stream));
    expect(track.stop).toHaveBeenCalledOnce();
    expect(media.enumerateDevices).toHaveBeenCalledOnce();
    expect(active).toHaveBeenLastCalledWith(false);
  });
  it("disconnected input remains explicit and can be replaced without a silent fallback", async () => {
    await show();
    fireEvent.change(screen.getByLabelText("Microphone input"), {
      target: { value: "mic-usb" },
    });
    devices = devices.filter((d) => d.deviceId !== "mic-usb");
    await act(async () => media.dispatchEvent(new Event("devicechange")));
    expect(screen.getByText("Saved microphone unavailable")).toBeVisible();
    expect(microphoneConstraints().audio).toMatchObject({
      deviceId: { exact: "mic-usb" },
    });
    fireEvent.change(screen.getByLabelText("Microphone input"), {
      target: { value: "mic-webcam" },
    });
    expect(
      screen.queryByText("Saved microphone unavailable"),
    ).not.toBeInTheDocument();
  });
  it("explains denied permission in French and permits another attempt", async () => {
    setLanguage("fr");
    media.getUserMedia.mockRejectedValueOnce(
      new DOMException("private details", "NotAllowedError"),
    );
    await show();
    fireEvent.click(
      screen.getByRole("button", { name: "Détecter les périphériques" }),
    );
    await flush();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "L’accès au microphone a été refusé",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent("private details");
    expect(
      screen.getByRole("button", { name: "Détecter les périphériques" }),
    ).toBeEnabled();
  });
  it("routes the audible speaker test before playing and releases audio focus", async () => {
    await show();
    fireEvent.change(screen.getByLabelText("Speaker output"), {
      target: { value: "headset" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test speakers" }));
    await flush();
    expect(players[0].sinkId).toBe("headset");
    expect(players[0].play).toHaveBeenCalledOnce();
    expect(audioFocus()).toBe("speech");
    await act(async () => players[0].onended?.());
    expect(audioFocus()).toBe("idle");
    expect(players[0].load).toHaveBeenCalledOnce();
  });
  it("switches an already playing test to the new output", async () => {
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Test speakers" }));
    await flush();
    fireEvent.change(screen.getByLabelText("Speaker output"), {
      target: { value: "display" },
    });
    await flush();
    expect(players[0].sinkId).toBe("display");
    expect(players[0].play).toHaveBeenCalledOnce();
  });
  it("can authorize an output omitted from enumeration through the browser chooser", async () => {
    const selected = device("audiooutput", "authorized", "Authorized headset");
    media.selectAudioOutput = vi.fn(async () => {
      devices.push(selected);
      return selected;
    });
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Authorize speakers" }));
    await flush();
    expect(audioPreferences().outputId).toBe("authorized");
    expect(screen.getByLabelText("Speaker output")).toHaveValue("authorized");
  });
  it("unsupported output selection offers an explicit system fallback", async () => {
    Reflect.deleteProperty(HTMLMediaElement.prototype, "setSinkId");
    saveAudioPreferences({ outputId: "stale" });
    await show();
    expect(screen.getByLabelText("Speaker output")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Use system output" }));
    expect(audioPreferences().outputId).toBe("");
  });
  it("default playback does not call optional sink selection and keeps the gesture", async () => {
    const player = new Player() as unknown as HTMLMediaElement;
    const played = playWithAudioOutput(player);
    expect(player.play).toHaveBeenCalledOnce();
    expect(player.setSinkId).not.toHaveBeenCalled();
    await played;
  });
  it("a denied selected output never falls back to a different audible speaker", async () => {
    saveAudioPreferences({ outputId: "headset" });
    const p = new Player();
    p.setSinkId.mockRejectedValue(
      new DOMException("private-device-id", "NotAllowedError"),
    );
    await expect(
      playWithAudioOutput(p as unknown as HTMLMediaElement),
    ).rejects.toThrow("selected output is unavailable");
    expect(p.play).not.toHaveBeenCalled();
  });
  it("cancellation during output selection never starts delayed playback", async () => {
    saveAudioPreferences({ outputId: "headset" });
    const p = new Player();
    let finish!: () => void;
    let active = true;
    p.setSinkId.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const pending = playWithAudioOutput(
      p as unknown as HTMLMediaElement,
      () => active,
    );
    await flush();
    active = false;
    finish();
    await pending;
    expect(p.play).not.toHaveBeenCalled();
  });
  it("serializes rapid sink changes and retains the last requested output", async () => {
    const p = new Player();
    const applied: string[] = [];
    p.setSinkId.mockImplementation(async (id) => {
      await Promise.resolve();
      applied.push(id);
      p.sinkId = id;
    });
    saveAudioPreferences({ outputId: "headset" });
    const first = applyAudioOutput(p as unknown as HTMLMediaElement);
    saveAudioPreferences({ outputId: "display" });
    const second = applyAudioOutput(p as unknown as HTMLMediaElement);
    await Promise.all([first, second]);
    expect(applied).toEqual(["headset", "display"]);
    expect(p.sinkId).toBe("display");
  });
  it("ignores malformed persisted values and supports storage-denied sessions", () => {
    localStorage.setItem(AUDIO_DEVICE_KEY, "{broken");
    expect(audioPreferences().inputId).toBe("");
    const write = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new DOMException("quota", "QuotaExceededError");
      });
    saveAudioPreferences({ inputId: "mic-session" });
    expect(audioPreferences().inputId).toBe("mic-session");
    write.mockRestore();
    saveAudioPreferences({ inputId: "", outputId: "", processing: true });
  });
});
