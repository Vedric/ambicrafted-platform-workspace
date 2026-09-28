import { useEffect, useRef, useState } from "react";
import {
  Headphones,
  Mic,
  RefreshCw,
  SlidersHorizontal,
  Square,
  Volume2,
} from "lucide-react";
import { MicrophoneCheck } from "./MicrophoneCheck";
import { claimAudioFocus } from "./audio-focus";
import {
  microphoneError,
  outputSelectionSupported,
  playWithAudioOutput,
  saveAudioPreferences,
  useAudioOutput,
  useAudioPreferences,
} from "./audio-devices";
import { t, useI18n } from "./i18n";
import "./audio-devices.css";

type OutputChooser = MediaDevices & {
  selectAudioOutput?: () => Promise<MediaDeviceInfo>;
};

export function AudioDevices({
  disabled,
  onActiveChange,
}: {
  disabled: boolean;
  onActiveChange: (active: boolean) => void;
}) {
  useI18n();
  const preferences = useAudioPreferences();
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [sampleActive, setSampleActive] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const refreshGeneration = useRef(0);
  const player = useRef<HTMLAudioElement | null>(null);
  const releaseFocus = useRef<(() => void) | null>(null);
  const callback = useRef(onActiveChange);
  callback.current = onActiveChange;
  const media = navigator.mediaDevices as OutputChooser | undefined;
  const outputsSupported = outputSelectionSupported();
  function stop() {
    generation.current++;
    if (player.current) {
      player.current.onended = player.current.onerror = null;
      player.current.pause();
      player.current.removeAttribute("src");
      player.current.load();
      player.current = null;
    }
    releaseFocus.current?.();
    releaseFocus.current = null;
    callback.current(false);
    setBusy(false);
    setTesting(false);
  }
  useAudioOutput(player, (cause) => {
    stop();
    setError(cause.message);
  });
  async function refresh() {
    if (!media?.enumerateDevices) return;
    const current = ++refreshGeneration.current;
    const listed = await media.enumerateDevices();
    if (current === refreshGeneration.current) setDevices(listed);
  }
  useEffect(() => {
    const changed = () => {
      void refresh().catch(() => {});
    };
    changed();
    media?.addEventListener?.("devicechange", changed);
    const cancel = (event: KeyboardEvent) => {
      if (event.key === "Escape") stop();
    };
    const hidden = () => {
      if (document.hidden) stop();
    };
    window.addEventListener("keydown", cancel);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      refreshGeneration.current++;
      stop();
      media?.removeEventListener?.("devicechange", changed);
      window.removeEventListener("keydown", cancel);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, []);
  async function detect() {
    stop();
    setError("");
    setBusy(true);
    callback.current(true);
    const current = generation.current;
    try {
      if (!media?.getUserMedia) throw new Error("unsupported");
      // This action asks for permission only; it never records or uploads sound.
      const stream = await media.getUserMedia({ audio: true, video: false });
      stream.getTracks().forEach((track) => track.stop());
      if (current === generation.current) await refresh();
    } catch (cause) {
      if (current === generation.current) setError(microphoneError(cause));
    } finally {
      if (current === generation.current) {
        setBusy(false);
        callback.current(false);
      }
    }
  }
  async function authorizeOutput() {
    if (!media?.selectAudioOutput) return;
    stop();
    setError("");
    setBusy(true);
    callback.current(true);
    const current = generation.current;
    try {
      const selected = await media.selectAudioOutput();
      if (current !== generation.current) return;
      saveAudioPreferences({ outputId: selected.deviceId });
      await refresh();
    } catch {
      if (current === generation.current)
        setError(
          t(
            "Speaker access was not granted. Choose System default or authorize the output again.",
          ),
        );
    } finally {
      if (current === generation.current) {
        setBusy(false);
        callback.current(false);
      }
    }
  }
  async function testOutput() {
    stop();
    setError("");
    setTesting(true);
    callback.current(true);
    const current = generation.current;
    releaseFocus.current = claimAudioFocus("speech");
    const audio = new Audio("/audio/speaker-check.wav");
    audio.volume = 0.35;
    player.current = audio;
    audio.onended = () => {
      if (current === generation.current) stop();
    };
    audio.onerror = () => {
      if (current === generation.current) {
        stop();
        setError(
          t(
            "Check your system speakers and tab volume, then replay the sample.",
          ),
        );
      }
    };
    try {
      await playWithAudioOutput(audio, () => current === generation.current);
    } catch (cause) {
      if (current === generation.current) {
        stop();
        setError(
          cause instanceof Error
            ? cause.message
            : t("Voice playback is unavailable."),
        );
      }
    }
  }
  const inputs = devices.filter(
    (d) => d.kind === "audioinput" && d.deviceId && d.deviceId !== "default",
  );
  const outputs = devices.filter(
    (d) => d.kind === "audiooutput" && d.deviceId && d.deviceId !== "default",
  );
  const inputMissing =
    !!preferences.inputId &&
    !inputs.some((d) => d.deviceId === preferences.inputId);
  const outputMissing =
    !!preferences.outputId &&
    !outputs.some((d) => d.deviceId === preferences.outputId);
  const locked = disabled || busy || testing || sampleActive;
  return (
    <section className="audio-devices" aria-label={t("Audio devices")}>
      <div className="audio-device-heading">
        <SlidersHorizontal size={18} />
        <h3>{t("Audio devices")}</h3>
        <span>{t("This browser")}</span>
      </div>
      <p>
        {t(
          "Choose your microphone and speakers, then check the signal before talking to AURA.",
        )}
      </p>
      <div className="audio-device-grid">
        <label>
          <span>
            <Mic size={16} />
            {t("Microphone input")}
          </span>
          <select
            aria-label={t("Microphone input")}
            value={preferences.inputId}
            disabled={locked}
            onChange={(event) => {
              saveAudioPreferences({ inputId: event.target.value });
              setError("");
            }}
          >
            <option value="">{t("System default")}</option>
            {inputMissing && (
              <option value={preferences.inputId}>
                {t("Saved microphone unavailable")}
              </option>
            )}
            {inputs.map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || t("Microphone {number}", { number: i + 1 })}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>
            <Headphones size={16} />
            {t("Speaker output")}
          </span>
          <select
            aria-label={t("Speaker output")}
            value={preferences.outputId}
            disabled={busy || sampleActive || !outputsSupported}
            onChange={(event) => {
              saveAudioPreferences({ outputId: event.target.value });
              setError("");
            }}
          >
            <option value="">{t("System default")}</option>
            {outputMissing && (
              <option value={preferences.outputId}>
                {t("Saved speaker unavailable")}
              </option>
            )}
            {outputs.map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || t("Speaker {number}", { number: i + 1 })}
              </option>
            ))}
          </select>
        </label>
      </div>
      {(inputMissing || outputMissing) && (
        <p className="audio-device-notice">
          {t(
            "A saved device is disconnected or not yet authorized. Detect devices or select System default.",
          )}
        </p>
      )}
      {!outputsSupported && (
        <p className="audio-device-notice">
          {t(
            "This browser cannot select speakers. Choose System default and select the output in your operating system.",
          )}
          {preferences.outputId && (
            <button
              className="text-button"
              onClick={() => saveAudioPreferences({ outputId: "" })}
            >
              {t("Use system output")}
            </button>
          )}
        </p>
      )}
      <div className="audio-device-actions">
        {busy || testing ? (
          <button className="btn" onClick={stop}>
            <Square size={16} />
            {t("Cancel audio setup")}
          </button>
        ) : (
          <button
            className="btn"
            disabled={locked}
            onClick={() => void detect()}
          >
            <RefreshCw size={16} />
            {t("Detect devices")}
          </button>
        )}
        <button
          className="btn"
          disabled={disabled || busy || testing || sampleActive}
          onClick={() => void testOutput()}
        >
          <Volume2 size={16} />
          {t("Test speakers")}
        </button>
        {outputsSupported && media?.selectAudioOutput && (
          <button
            className="text-button"
            disabled={locked}
            onClick={() => void authorizeOutput()}
          >
            {t("Authorize speakers")}
          </button>
        )}
      </div>
      {busy && <p>{t("Waiting for device permission…")}</p>}
      {error && <p role="alert">{error}</p>}
      <label className="checkbox-label audio-processing">
        <input
          type="checkbox"
          checked={preferences.processing}
          disabled={locked}
          onChange={(event) =>
            saveAudioPreferences({ processing: event.target.checked })
          }
        />
        {t("Voice processing")}
      </label>
      <p className="hint">
        {t(
          "Reduce echo and background noise. If a virtual microphone sounds silent or clipped, disable this and test again.",
        )}
      </p>
      <MicrophoneCheck
        disabled={disabled || busy || testing}
        onActiveChange={(active) => {
          setSampleActive(active);
          callback.current(active);
        }}
      />
      <p className="hint">
        {t(
          "Device names appear after microphone permission. Your selection stays in this browser and also applies to greetings, videos and music.",
        )}
      </p>
    </section>
  );
}
