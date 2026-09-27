import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Music2, VolumeX } from "lucide-react";
import {
  audioFocus,
  subscribeAudioFocus,
  claimAudioFocus,
} from "./audio-focus";
import { t, useI18n } from "./i18n";
import "./ambient-audio.css";

const KEY = "ambicrafted-ambient";
const MAX_VOLUME = 0.22;
type State = "off" | "playing" | "blocked" | "error" | "paused";
function preference() {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(KEY) || "null");
    if (
      data &&
      typeof data === "object" &&
      "volume" in data &&
      "enabled" in data
    )
      return {
        enabled: data.enabled === true,
        volume:
          typeof data.volume === "number" && Number.isFinite(data.volume)
            ? Math.max(0, Math.min(MAX_VOLUME, data.volume))
            : 0.12,
      };
  } catch {
    /* A corrupted preference must not block the workspace. */
  }
  return { enabled: false, volume: 0.12 };
}
const Context = createContext({
  enabled: false,
  volume: 0.12,
  state: "off" as State,
  toggle: () => {},
  setVolume: (_volume: number) => {},
});

export function AmbientAudioProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(preference);
  const [state, setState] = useState<State>("off");
  const current = useRef(settings);
  current.current = settings;
  const player = useRef<HTMLAudioElement | null>(null);
  const playGeneration = useRef(0);
  const fade = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopFade = () => {
    if (fade.current !== null) clearInterval(fade.current);
    fade.current = null;
  };
  const syncVolume = () => {
    const audio = player.current;
    if (!audio) return;
    stopFade();
    const focus = audioFocus();
    audio.muted = focus === "microphone";
    const target =
      focus === "microphone"
        ? 0
        : current.current.volume * (focus === "speech" ? 0.08 : 1);
    // Attenuate synchronously, before speech/recording; only the return fades in.
    if (target <= audio.volume || audio.paused) {
      audio.volume = target;
      return;
    }
    const start = audio.volume;
    const started = performance.now();
    fade.current = setInterval(() => {
      const progress = Math.min(1, (performance.now() - started) / 1400);
      audio.volume = start + (target - start) * progress;
      if (progress === 1) stopFade();
    }, 50);
  };
  const play = () => {
    if (document.hidden || !current.current.enabled) return;
    const audio = player.current || new Audio("/audio/orbital-drift.mp3");
    if (!player.current) {
      audio.loop = true;
      audio.preload = "none";
      audio.volume = 0;
      audio.onerror = () => {
        stopFade();
        setState("error");
      };
      player.current = audio;
    }
    const generation = ++playGeneration.current;
    syncVolume();
    void audio
      .play()
      .then(() => {
        if (generation !== playGeneration.current) return;
        setState("playing");
        syncVolume();
      })
      .catch((error: unknown) => {
        if (generation !== playGeneration.current) return;
        stopFade();
        setState(
          error instanceof DOMException && error.name === "NotAllowedError"
            ? "blocked"
            : "error",
        );
      });
  };
  const pause = () => {
    playGeneration.current++;
    stopFade();
    player.current?.pause();
  };
  const toggle = () => {
    // A blocked autoplay is resumed by this explicit gesture, never a hidden click handler.
    const enabled =
      !current.current.enabled || state === "blocked" || state === "error";
    current.current = { ...current.current, enabled };
    setSettings(current.current);
    if (enabled) play();
    else {
      pause();
      setState("off");
    }
  };
  useEffect(() => {
    const release = subscribeAudioFocus(syncVolume);
    const visibility = () => {
      if (document.hidden) {
        pause();
        setState(current.current.enabled ? "paused" : "off");
      } else play();
    };
    const exit = () => {
      pause();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      current.current = { ...current.current, enabled: false };
      setSettings(current.current);
      pause();
      setState("off");
    };
    // Guide video audio also takes priority over the ambient score.
    const videos = new Map<HTMLVideoElement, () => void>();
    const videoEvent = (event: Event) => {
      if (!(event.target instanceof HTMLVideoElement)) return;
      const video = event.target;
      if (event.type === "play" && !videos.has(video)) {
        // A video lease is released on pause/ended or removal.
        videos.set(video, claimAudioFocus("speech"));
      } else if (event.type !== "play") {
        videos.get(video)?.();
        videos.delete(video);
      }
    };
    const observer = new MutationObserver(() => {
      for (const [video, releaseVideo] of videos)
        if (!video.isConnected) {
          releaseVideo();
          videos.delete(video);
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    for (const event of ["play", "pause", "ended", "emptied"])
      document.addEventListener(event, videoEvent, true);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", exit);
    window.addEventListener("keydown", escape);
    play();
    return () => {
      release();
      observer.disconnect();
      videos.forEach((releaseVideo) => releaseVideo());
      for (const event of ["play", "pause", "ended", "emptied"])
        document.removeEventListener(event, videoEvent, true);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", exit);
      window.removeEventListener("keydown", escape);
      pause();
      if (player.current) {
        player.current.onerror = null;
        player.current.removeAttribute("src");
        player.current.load();
        player.current = null;
      }
    };
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(settings));
    } catch {
      /* Session control still works. */
    }
    syncVolume();
  }, [settings]);
  return (
    <Context.Provider
      value={{
        ...settings,
        state,
        toggle,
        setVolume: (volume) => {
          if (Number.isFinite(volume))
            setSettings((before) => ({
              ...before,
              volume: Math.max(0, Math.min(MAX_VOLUME, volume)),
            }));
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function AmbientAudioControl({
  expanded = false,
}: {
  expanded?: boolean;
}) {
  useI18n();
  const audio = useContext(Context);
  const resume = audio.state === "blocked" || audio.state === "error";
  const label =
    audio.enabled && !resume
      ? t("Pause ambient music")
      : t("Play ambient music");
  return (
    <div className={expanded ? "ambient-settings" : "ambient-control"}>
      <button
        type="button"
        className={expanded ? "btn" : "icon-button"}
        onClick={audio.toggle}
        aria-label={label}
        title={label}
        aria-pressed={audio.enabled && !resume}
      >
        {audio.enabled && !resume ? (
          <Music2 size={18} />
        ) : (
          <VolumeX size={18} />
        )}
        {expanded && label}
      </button>
      {expanded && (
        <>
          <label className="ambient-volume">
            {t("Background level")}
            <input
              type="range"
              min="0"
              max="22"
              step="1"
              value={Math.round(audio.volume * 100)}
              onChange={(event) =>
                audio.setVolume(Number(event.target.value) / 100)
              }
            />
            <output>{Math.round(audio.volume * 100)}%</output>
          </label>
          <p>
            {t(
              "Orbital Drift · Original instrumental. Softened while AURA speaks, silent while your microphone listens.",
            )}
          </p>
        </>
      )}
      {resume && expanded && (
        <p role="status">
          {audio.state === "blocked"
            ? t("Select Play ambient music to allow audio in this browser.")
            : t("Ambient audio is unavailable. You can retry playback.")}
        </p>
      )}
    </div>
  );
}
