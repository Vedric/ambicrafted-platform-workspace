import { useEffect, useRef, useState } from "react";
import { Mic, Play, Square } from "lucide-react";
import { useAudioFocus } from "./audio-focus";
import { t, useI18n } from "./i18n";
import { waveform } from "./audio-signal";

/** A browser-only input/output check. Its short sample never reaches the API. */
export function MicrophoneCheck({
  disabled,
  onActiveChange,
}: {
  disabled: boolean;
  onActiveChange: (active: boolean) => void;
}) {
  useI18n();
  const [phase, setPhase] = useState<
    "idle" | "permission" | "recording" | "ready" | "playing"
  >("idle");
  const [level, setLevel] = useState(0);
  const [heard, setHeard] = useState(false);
  const [error, setError] = useState("");
  const [input, setInput] = useState("");
  const [seconds, setSeconds] = useState(0);
  const generation = useRef(0);
  const stream = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const sample = useRef<string | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const callback = useRef(onActiveChange);
  callback.current = onActiveChange;
  useAudioFocus(
    phase === "permission" || phase === "recording"
      ? "microphone"
      : phase === "playing"
        ? "speech"
        : null,
  );
  function releaseInput() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    if (context.current) void context.current.close().catch(() => {});
    context.current = null;
  }
  function releasePlayback() {
    if (player.current) {
      player.current.onended = null;
      player.current.onerror = null;
      player.current.pause();
      player.current.removeAttribute("src");
      player.current.load();
    }
    player.current = null;
  }
  function reset() {
    generation.current++;
    const recording = recorder.current;
    recorder.current = null;
    if (recording) {
      recording.onstop = null;
      recording.ondataavailable = null;
      recording.onerror = null;
      if (recording.state === "recording") recording.stop();
    }
    releaseInput();
    releasePlayback();
    if (sample.current) URL.revokeObjectURL(sample.current);
    sample.current = null;
    callback.current(false);
  }
  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
    else {
      reset();
      setPhase("idle");
    }
  }
  async function start() {
    reset();
    const current = generation.current;
    setError("");
    setHeard(false);
    setLevel(0);
    setSeconds(0);
    setInput("");
    setPhase("permission");
    callback.current(true);
    try {
      if (
        !navigator.mediaDevices?.getUserMedia ||
        typeof MediaRecorder === "undefined"
      )
        throw new Error("unsupported");
      // Keep activation alive before awaiting the browser permission dialog.
      const audio = new AudioContext();
      context.current = audio;
      void audio.resume().catch(() => {});
      const media = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: false,
      });
      if (current !== generation.current) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = media;
      setInput(
        media.getAudioTracks()[0]?.label || t("System default microphone"),
      );
      const source = audio.createMediaStreamSource(media);
      const analyser = audio.createAnalyser();
      analyser.fftSize = 1024;
      const silent = audio.createGain();
      silent.gain.value = 0;
      source.connect(analyser);
      analyser.connect(silent);
      silent.connect(audio.destination);
      const values = new Float32Array(analyser.fftSize);
      const recording = new MediaRecorder(media);
      recorder.current = recording;
      const parts: Blob[] = [];
      let size = 0;
      recording.ondataavailable = (event) => {
        if (current !== generation.current) return;
        size += event.data.size;
        if (size <= 8 * 1024 * 1024) parts.push(event.data);
        else {
          reset();
          setPhase("idle");
          setError(t("Microphone test failed. Try a shorter recording."));
        }
      };
      recording.onerror = () => {
        if (current !== generation.current) return;
        reset();
        setPhase("idle");
        setError(t("Microphone test failed. Try a shorter recording."));
      };
      recording.onstop = () => {
        if (current !== generation.current) return;
        releaseInput();
        recorder.current = null;
        callback.current(false);
        if (!size) {
          setPhase("idle");
          setError(t("No audio was recorded. Please try again."));
          return;
        }
        sample.current = URL.createObjectURL(
          new Blob(parts, { type: recording.mimeType }),
        );
        setPhase("ready");
      };
      recording.start(250);
      setPhase("recording");
      const began = performance.now();
      timer.current = setInterval(() => {
        if (current !== generation.current) return;
        analyser.getFloatTimeDomainData(values);
        const energy = waveform(values).level;
        setLevel(energy);
        if (energy > 0.012) setHeard(true);
        setSeconds(Math.min(8, Math.floor((performance.now() - began) / 1000)));
        if (performance.now() - began >= 8000) {
          if (timer.current) clearInterval(timer.current);
          timer.current = null;
          if (recording.state === "recording") recording.stop();
        }
      }, 100);
    } catch (cause) {
      if (current !== generation.current) return;
      reset();
      setPhase("idle");
      setError(
        cause instanceof DOMException && cause.name === "NotAllowedError"
          ? t(
              "Microphone access was denied. Allow access in your browser’s site settings.",
            )
          : t(
              "Check your system microphone, browser permission and localhost connection, then try again.",
            ),
      );
    }
  }
  async function play() {
    if (!sample.current) return;
    const current = ++generation.current;
    releasePlayback();
    const audio = new Audio(sample.current);
    player.current = audio;
    callback.current(true);
    setError("");
    setPhase("playing");
    audio.onended = () => {
      if (current === generation.current) {
        callback.current(false);
        setPhase("ready");
      }
    };
    const failed = () => {
      if (current !== generation.current) return;
      audio.pause();
      callback.current(false);
      setPhase("ready");
      setError(
        t("Check your system speakers and tab volume, then replay the sample."),
      );
    };
    audio.onerror = failed;
    try {
      await audio.play();
    } catch {
      failed();
    }
  }
  useEffect(() => {
    const leave = () => {
      if (document.hidden) {
        reset();
        setPhase("idle");
      }
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        reset();
        setPhase("idle");
      }
    };
    document.addEventListener("visibilitychange", leave);
    window.addEventListener("keydown", key);
    return () => {
      reset();
      document.removeEventListener("visibilitychange", leave);
      window.removeEventListener("keydown", key);
    };
  }, []);
  const busy = ["permission", "recording", "playing"].includes(phase);
  return (
    <details
      className="microphone-check"
      onToggle={(event) => {
        if (!event.currentTarget.open) {
          reset();
          setPhase("idle");
        }
      }}
    >
      <summary>{t("Check microphone & sound")}</summary>
      <p>
        {t(
          "Record up to 8 seconds, then listen back. This test stays in your browser.",
        )}
      </p>
      {input && <p className="hint">{input}</p>}
      {phase === "permission" && (
        <p role="status">{t("Waiting for microphone permission…")}</p>
      )}
      {phase === "recording" && (
        <>
          <meter
            aria-label={t("Test input level")}
            min={0}
            max={1}
            value={level}
          />
          <p role="status">
            {heard
              ? t("Input signal detected.")
              : t("Speak naturally and watch the input meter.")}{" "}
            · {seconds} / 8 s
          </p>
        </>
      )}
      <div className="microphone-diagnostic-actions">
        {busy ? (
          <button type="button" className="btn" onClick={stop}>
            <Square size={16} />
            {t("Stop test")}
          </button>
        ) : (
          <button
            type="button"
            className="btn"
            disabled={disabled}
            onClick={() => void start()}
          >
            <Mic size={16} />
            {t("Test microphone")}
          </button>
        )}
        {phase === "ready" && (
          <button
            type="button"
            className="btn"
            disabled={disabled}
            onClick={() => void play()}
          >
            <Play size={16} />
            {t("Listen to the sample")}
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {phase === "ready" && !heard && (
        <p role="status">
          {t(
            "No input signal yet. Check the selected microphone, hardware mute and system input level.",
          )}
        </p>
      )}
    </details>
  );
}
