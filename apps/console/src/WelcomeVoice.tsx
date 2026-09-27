import { useAudioFocus } from "./audio-focus";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AudioLines, LoaderCircle, Play, Square } from "lucide-react";
import { api, audioLocal, type Vue } from "./api";
import { t, useI18n } from "./i18n";
import { applyAudioOutput } from "./audio-devices";
import { pcmSignal, type SignalReader } from "./audio-signal";
import { NeuralCore } from "./NeuralCore";
import { useTechWatch } from "./TechWatch";

export const GREETING =
  "Hi Védric, good to have you back. What are we working on today? We can look into an incident, talk through an architecture, or pick up where we left off. Take your time, I'm here." as const;
const preferenceKey = "ambicrafted-welcome-audio";
type Phase = "idle" | "loading" | "speaking" | "blocked" | "error";

export function briefingText(data: Vue): string {
  return t(
    "Védric, here is your workspace briefing. {healthy} of {services} services responded successfully to the latest health check. {waiting} analyses await your decision, and {active} executions are queued or running. Your knowledge library contains {runbooks} runbooks. These readings describe the current workspace. They do not certify production readiness.",
    {
      healthy: data.sante.services.filter((service) => service.ok).length,
      services: data.sante.services.length,
      waiting: data.statuts.en_attente_humain || 0,
      active:
        (data.statuts.en_file || 0) +
        (data.statuts.en_cours || 0) +
        (data.statuts.decision || 0),
      runbooks: data.runbooks,
    },
  );
}

/** Public greeting is a fixed local asset; private readings require the authenticated API. */
export default function WelcomeVoice({ connected }: { connected: boolean }) {
  const { language } = useI18n();
  const watch = useTechWatch();
  const latestWatch = useRef(watch.data);
  latestWatch.current = watch.data;
  const [phase, setPhase] = useState<Phase>("idle");
  useAudioFocus(phase === "loading" || phase === "speaking" ? "speech" : null);
  const [message, setMessage] = useState<string | null>(null);
  const [transcript, setTranscript] = useState("");
  const [automatic, setAutomatic] = useState(() => {
    try {
      return localStorage.getItem(preferenceKey) !== "off";
    } catch {
      return true;
    }
  });
  const player = useRef<HTMLAudioElement | null>(null);
  const request = useRef<AbortController | null>(null);
  const signal = useRef<SignalReader | null>(null);
  const objectUrl = useRef<string | null>(null);
  const generation = useRef(0);
  const playLatest = useRef<() => void>(() => {});
  const overview = useQuery({
    queryKey: ["welcome-briefing"],
    queryFn: ({ signal: abortSignal }) =>
      api<Vue>("/vue-ensemble", "GET", undefined, abortSignal),
    enabled: connected,
    staleTime: 30_000,
    retry: false,
  });
  const stop = () => {
    generation.current++;
    request.current?.abort();
    request.current = null;
    if (player.current) {
      player.current.onplaying = null;
      player.current.onended = null;
      player.current.onerror = null;
      player.current.pause();
      player.current.removeAttribute("src");
      player.current.load();
      player.current = null;
    }
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    signal.current = null;
    setPhase("idle");
  };
  const play = async (kind: "greeting" | "briefing" | "watch") => {
    stop();
    const current = generation.current;
    const controller = new AbortController();
    request.current = controller;
    setMessage(null);
    setPhase("loading");
    const text = kind === "greeting" ? t(GREETING) : "";
    setTranscript(text);
    try {
      let source = `/audio/aura-welcome-${language}.wav`;
      let audioData: Promise<ArrayBuffer>;
      if (kind === "briefing") {
        // Fetch on request so a saved welcome page never reads yesterday's health as current.
        const data = await overview.refetch();
        if (current !== generation.current) return;
        if (!connected || !data.data || data.error)
          throw new Error(
            t(
              "Workspace data is unavailable. Refresh before requesting your briefing.",
            ),
          );
        const briefing = briefingText(data.data);
        setTranscript(briefing);
        const blob = await audioLocal(briefing, controller.signal, language);
        if (current !== generation.current) return;
        source = URL.createObjectURL(blob);
        objectUrl.current = source;
        audioData = blob.arrayBuffer();
      } else {
        if (kind === "watch") {
          const briefing = latestWatch.current?.briefings?.[language];
          if (!briefing || latestWatch.current?.stale)
            throw new Error("Technology briefing unavailable");
          source = `/api/veille/audio/${language}`;
          setTranscript(briefing.text);
        }
        audioData = fetch(source, { signal: controller.signal }).then(
          (response) => {
            if (!response.ok) throw new Error("audio unavailable");
            return response.arrayBuffer();
          },
        );
      }
      const audio = new Audio(source);
      player.current = audio;
      audio.onplaying = () => {
        if (generation.current === current) setPhase("speaking");
      };
      audio.onended = () => {
        if (generation.current !== current) return;
        if (
          kind === "greeting" &&
          latestWatch.current?.briefings?.[language] &&
          !latestWatch.current.stale
        )
          void play("watch");
        else stop();
      };
      audio.onerror = () => {
        if (generation.current !== current) return;
        stop();
        setMessage(
          t(
            "Playback was interrupted. Check your output device and try again.",
          ),
        );
        setPhase("error");
      };
      // Decode only for truthful visual energy; native playback does not depend on Web Audio.
      void audioData
        .then((buffer) => {
          if (generation.current !== current) return;
          const sample = pcmSignal(buffer);
          signal.current = sample
            ? () => (audio.paused ? null : sample(audio.currentTime))
            : null;
        })
        .catch(() => {
          /* Playback itself reports failures. */
        });
      await applyAudioOutput(audio);
      if (generation.current !== current) return;
      await audio.play();
    } catch (error) {
      if (generation.current !== current) return;
      const blocked =
        error instanceof DOMException && error.name === "NotAllowedError";
      stop();
      setPhase(blocked ? "blocked" : "error");
      setMessage(
        blocked
          ? t(
              "Your browser needs a click to start the audio. Select Listen to my welcome.",
            )
          : error instanceof Error && kind === "briefing"
            ? error.message
            : t(
                "Playback was interrupted. Check your output device and try again.",
              ),
      );
    }
  };
  playLatest.current = () => {
    void play("greeting");
  };
  useEffect(() => {
    // Delay one task to avoid a double greeting during StrictMode setup/cleanup.
    const timer = automatic
      ? window.setTimeout(() => playLatest.current(), 80)
      : undefined;
    return () => {
      window.clearTimeout(timer);
      stop();
    };
    // Changing language or the arrival preference starts a new, explicit welcome lifecycle.
  }, [automatic, language]);
  useEffect(() => {
    const visibility = () => {
      if (document.hidden) stop();
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") stop();
    };
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", stop);
    window.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", stop);
      window.removeEventListener("keydown", key);
    };
  }, []);
  const busy = phase === "speaking" || phase === "loading";
  return (
    <section className="welcome-voice" aria-label={t("AURA welcomes you")}>
      <div className="welcome-instrument">
        <div className="instrument-heading">
          <span>
            <AudioLines size={15} /> {t("LOCAL VOICE INTERFACE")}
          </span>
        </div>
        <NeuralCore
          phase={
            phase === "speaking"
              ? "speaking"
              : phase === "loading"
                ? "loading"
                : "idle"
          }
          signal={signal}
        />
        <div className="welcome-identity">
          <span className="eyebrow">AURA</span>
          <h2>{t("Welcome, Védric.")}</h2>
          <p>{t("Your space. Your pace.")}</p>
        </div>
      </div>
      <div className="welcome-voice-controls">
        <div className="welcome-audio-actions">
          <button
            className="btn primary"
            onClick={() => (busy ? stop() : void play("greeting"))}
          >
            {phase === "loading" ? (
              <LoaderCircle size={17} className="spin" />
            ) : busy ? (
              <Square size={17} />
            ) : (
              <Play size={17} />
            )}
            {busy ? t("Stop audio") : t("Listen to my welcome")}
          </button>
          {connected && (
            <button
              className="btn"
              disabled={busy || overview.isPending}
              onClick={() => void play("briefing")}
            >
              <AudioLines size={17} />
              {t("Listen to my briefing")}
            </button>
          )}
          {watch.data?.briefings?.[language] && !watch.data.stale && (
            <button
              className="btn"
              disabled={busy}
              onClick={() => void play("watch")}
            >
              <AudioLines size={17} />
              {t("Listen to technology watch")}
            </button>
          )}
        </div>
        <p
          className="welcome-audio-status"
          role={phase === "error" ? "alert" : "status"}
        >
          {message ||
            (phase === "speaking"
              ? t("AURA is speaking")
              : phase === "loading"
                ? t("Preparing your audio…")
                : t("Ready when you are, Védric."))}
        </p>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={automatic}
            onChange={(event) => {
              setAutomatic(event.target.checked);
              try {
                localStorage.setItem(
                  preferenceKey,
                  event.target.checked ? "on" : "off",
                );
              } catch {
                /* In-memory preference remains usable. */
              }
            }}
          />
          {t("Welcome me on arrival")}
        </label>
        <p className="hint">
          {t("AURA uses your system’s default microphone and speakers.")}
        </p>
        {transcript && (
          <details className="welcome-transcript">
            <summary>{t("Transcript")}</summary>
            <p>{transcript}</p>
          </details>
        )}
        <p className="hint">
          {connected
            ? t(
                "Your private workspace briefing is separate from the public technology watch below.",
              )
            : t("Sign in to hear your private workspace briefing.")}
        </p>
      </div>
    </section>
  );
}
