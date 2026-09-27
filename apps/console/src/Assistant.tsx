import { useAudioFocus } from "./audio-focus";
import { texteOral } from "./spoken-text";
export { texteOral } from "./spoken-text";
import { getLanguage, number, t, useI18n, type MessageKey } from "./i18n";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import {
  AudioLines,
  Bot,
  Check,
  CornerDownLeft,
  Headphones,
  LoaderCircle,
  LockKeyhole,
  Mic,
  Send,
  ShieldCheck,
  Square,
  Trash2,
  Volume2,
  Workflow,
} from "lucide-react";
import { NeuralCore, type CorePhase } from "./NeuralCore";
import {
  inputActivity,
  pcmSignal,
  waveform,
  type SignalReader,
} from "./audio-signal";
import { applyAudioOutput } from "./audio-devices";
import { api, audioLocal } from "./api";
import { Erreur, Markdown, Titre, useToast } from "./ui";
import "./voice-controls.css";

export type Message = { role: "user" | "assistant"; content: string };
export type SavedConversationProps = {
  initialMessages?: Message[];
  initialDraft?: string;
  onDraftChange?: (draft: string) => void;
  externalBusy?: boolean;
  sendMessage?: (
    text: string,
    language: "en" | "fr",
    signal: AbortSignal,
    onText: (text: string) => void,
  ) => Promise<{ texte: string; usage?: unknown }>;
  onNew?: () => void;
  composerExtra?: ReactNode;
};
type EtatVoix = { pret: boolean; local: boolean; voix: string; langue: string };
type TokenUsage = {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
};

export function reportedUsage(value: unknown): TokenUsage {
  const usage =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  const count = (key: string) =>
    typeof usage[key] === "number" &&
    Number.isSafeInteger(usage[key]) &&
    usage[key] >= 0
      ? usage[key]
      : null;
  return {
    prompt_tokens: count("prompt_tokens"),
    completion_tokens: count("completion_tokens"),
    total_tokens: count("total_tokens"),
  };
}
type Phase =
  | "repos"
  | "permission"
  | "micro"
  | "transcription"
  | "reflexion"
  | "synthese"
  | "lecture";
const MAX_AUDIO = 8 * 1024 * 1024;

function encoderAudio(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const lecteur = new FileReader();
    lecteur.onload = () =>
      typeof lecteur.result === "string"
        ? resolve(lecteur.result.split(",")[1] || "")
        : reject(new Error(t("Unable to read the audio recording.")));
    lecteur.onerror = () =>
      reject(new Error(t("Unable to read the audio recording.")));
    lecteur.readAsDataURL(blob);
  });
}

const erreursMicro: Record<string, string> = {
  get NotAllowedError() {
    return t(
      "Microphone access was denied. Allow access in your browser’s site settings.",
    );
  },
  get NotFoundError() {
    return t("No microphone was found. Connect one or type your message.");
  },
  get NotReadableError() {
    return t("The microphone is unavailable or in use by another application.");
  },
  get SecurityError() {
    return t(
      "Your browser blocked microphone access. Open the platform on localhost.",
    );
  },
  get OverconstrainedError() {
    return t(
      "The default microphone is unavailable. Check your operating system’s audio input settings.",
    );
  },
};

export default function Assistant({
  initialMessages = [],
  initialDraft = "",
  onDraftChange,
  externalBusy = false,
  sendMessage,
  onNew,
  composerExtra,
}: SavedConversationProps = {}) {
  useI18n();
  const notifier = useToast();
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [brouillon, setBrouillon] = useState(initialDraft);
  const draftCallback = useRef(onDraftChange);
  draftCallback.current = onDraftChange;
  useEffect(() => {
    draftCallback.current?.(brouillon);
  }, [brouillon]);
  const [phase, setPhase] = useState<Phase>("repos");
  useAudioFocus(
    phase === "permission" || phase === "micro"
      ? "microphone"
      : phase !== "repos"
        ? "speech"
        : null,
  );
  const [secondes, setSecondes] = useState(0);
  const [waitingSeconds, setWaitingSeconds] = useState(0);
  const [automatique, setAutomatique] = useState(false);
  const automatiqueRef = useRef(false);
  const automaticSpeech = useRef(false);
  const [langue, setLangue] = useState<"en" | "fr">(getLanguage);
  const [microLevel, setMicroLevel] = useState(0);
  const [captureNote, setCaptureNote] = useState<MessageKey | null>(null);
  const [monitorBlocked, setMonitorBlocked] = useState(false);
  const [reviewReady, setReviewReady] = useState(false);
  const [lastUsage, setLastUsage] = useState<TokenUsage | null>(null);
  const [sessionUsage, setSessionUsage] = useState({
    total: 0,
    reported: 0,
    replies: 0,
  });
  const [handsFree, setHandsFree] = useState(false);
  const handsFreeRef = useRef(false);
  const turns = useRef(0);
  const nextTurn = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestMessages = useRef<Message[]>(initialMessages);
  const signal = useRef<SignalReader | null>(null);
  const microphoneContext = useRef<AudioContext | null>(null);
  const microphoneSource = useRef<MediaStreamAudioSourceNode | null>(null);
  const microphoneAnalyser = useRef<AnalyserNode | null>(null);
  const [voix, setVoix] = useState<EtatVoix | null>(null);
  const [erreurVoix, setErreurVoix] = useState(false);
  const [erreur, setErreur] = useState<Error | null>(null);
  const vivant = useRef(true),
    generation = useRef(0);
  const requete = useRef<AbortController | null>(null);
  const flux = useRef<MediaStream | null>(null),
    enregistreur = useRef<MediaRecorder | null>(null);
  const minuterie = useRef<ReturnType<typeof setInterval> | null>(null);
  const lecteur = useRef<HTMLAudioElement | null>(null),
    urlAudio = useRef<string | null>(null);
  const conversation = useRef<HTMLDivElement | null>(null),
    champ = useRef<HTMLTextAreaElement | null>(null);
  const envoiEnCours = useRef<{ texte: string; avant: Message[] } | null>(null);
  const actuel = (numero: number) =>
    vivant.current && numero === generation.current;
  const occupe = externalBusy || (phase !== "repos" && phase !== "lecture");
  const microDisponible =
    typeof MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia;

  function endConversation() {
    handsFreeRef.current = false;
    if (vivant.current) setHandsFree(false);
    if (nextTurn.current) clearTimeout(nextTurn.current);
    nextTurn.current = null;
  }

  function releaseMicrophoneSignal() {
    signal.current = null;
    microphoneSource.current?.disconnect();
    microphoneAnalyser.current?.disconnect();
    microphoneSource.current = null;
    microphoneAnalyser.current = null;
    const context = microphoneContext.current;
    microphoneContext.current = null;
    if (context && context.state !== "closed")
      void context.close().catch(() => {});
  }

  function prepareMicrophoneSignal() {
    try {
      if (!window.AudioContext) return;
      // Called synchronously from Record/Start, before awaiting microphone
      // permission. Resume requires user activation in some browsers.
      const context = new AudioContext();
      microphoneContext.current = context;
      if (context.state === "suspended") void context.resume().catch(() => {});
    } catch {
      releaseMicrophoneSignal();
    }
  }

  function attachMicrophoneSignal(stream: MediaStream) {
    try {
      const context = microphoneContext.current;
      if (!context) return;
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      microphoneSource.current = source;
      microphoneAnalyser.current = analyser;
      analyser.fftSize = 1024;
      source.connect(analyser); // Never connect the microphone to the speakers.
      const samples = new Float32Array(analyser.fftSize);
      signal.current = () => {
        if (context.state !== "running") return null;
        analyser.getFloatTimeDomainData(samples);
        return waveform(samples);
      };
      if (context.state === "suspended") void context.resume().catch(() => {});
    } catch {
      releaseMicrophoneSignal();
    }
  }

  function couperMicro() {
    if (minuterie.current) clearInterval(minuterie.current);
    minuterie.current = null;
    if (enregistreur.current?.state === "recording")
      enregistreur.current.stop();
    flux.current?.getTracks().forEach((piste) => piste.stop());
    flux.current = null;
    enregistreur.current = null;
    releaseMicrophoneSignal();
  }

  function couperSon() {
    automaticSpeech.current = false;
    signal.current = null;
    if (lecteur.current) {
      lecteur.current.onended = null;
      lecteur.current.onerror = null;
      lecteur.current.pause();
      lecteur.current.removeAttribute("src");
    }
    lecteur.current = null;
    if (urlAudio.current) URL.revokeObjectURL(urlAudio.current);
    urlAudio.current = null;
  }

  function arreter(preserveConversation = false) {
    if (!preserveConversation) endConversation();
    generation.current += 1;
    requete.current?.abort();
    requete.current = null;
    couperMicro();
    couperSon();
    if (vivant.current) {
      setPhase("repos");
      if (envoiEnCours.current) {
        setBrouillon(envoiEnCours.current.texte);
        latestMessages.current = envoiEnCours.current.avant;
        setMessages(envoiEnCours.current.avant);
      }
    }
    envoiEnCours.current = null;
  }

  useEffect(() => {
    vivant.current = true;
    const hidden = () => {
      if (document.hidden) arreter();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") arreter();
    };
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("keydown", escape);
    return () => {
      vivant.current = false;
      document.removeEventListener("visibilitychange", hidden);
      window.removeEventListener("keydown", escape);
      arreter();
    };
  }, []);

  useEffect(() => {
    const controle = new AbortController();
    setVoix(null);
    setErreurVoix(false);
    api<EtatVoix>(
      `/voix/statut?langue=${langue}`,
      "GET",
      undefined,
      controle.signal,
    )
      .then((resultat) => {
        if (!controle.signal.aborted) setVoix(resultat);
      })
      .catch(() => {
        if (!controle.signal.aborted) setErreurVoix(true);
      });
    return () => controle.abort();
  }, [langue]);

  useEffect(() => {
    setWaitingSeconds(0);
    if (!["transcription", "reflexion", "synthese"].includes(phase)) return;
    const start = Date.now();
    const interval = setInterval(
      () => setWaitingSeconds(Math.floor((Date.now() - start) / 1000)),
      1000,
    );
    return () => clearInterval(interval);
  }, [phase]);

  useEffect(() => {
    if (reviewReady && phase === "repos") champ.current?.focus();
  }, [reviewReady, phase]);

  useEffect(() => {
    if (conversation.current)
      conversation.current.scrollTop = conversation.current.scrollHeight;
  }, [messages, phase]);

  async function lire(
    texte: string,
    continueConversation = false,
    automaticPlayback = false,
  ) {
    const oral = texteOral(texte, langue);
    if (!oral) {
      endConversation();
      notifier(t("This reply has no text to read aloud."));
      return;
    }
    arreter(continueConversation);
    automaticSpeech.current = automaticPlayback;
    const numero = generation.current;
    const controle = new AbortController();
    requete.current = controle;
    setErreur(null);
    setPhase("synthese");
    try {
      const audio = await audioLocal(oral, controle.signal, langue);
      if (!actuel(numero)) return;
      // The visualizer is optional. Native playback must survive unsupported WAVs.
      let envelope: ReturnType<typeof pcmSignal> = null;
      try {
        envelope = pcmSignal(await audio.arrayBuffer());
      } catch {
        /* static fallback */
      }
      if (!actuel(numero)) return;
      const url = URL.createObjectURL(audio);
      urlAudio.current = url;
      const son = new Audio(url);
      lecteur.current = son;
      signal.current = () =>
        son.paused ? null : (envelope?.(son.currentTime) ?? null);
      son.onended = () => {
        if (actuel(numero)) {
          couperSon();
          setPhase("repos");
          if (handsFreeRef.current && continueConversation) {
            nextTurn.current = setTimeout(() => {
              nextTurn.current = null;
              if (actuel(numero) && handsFreeRef.current) void dicter(true);
            }, 600);
          }
        }
      };
      son.onerror = () => {
        if (actuel(numero)) {
          couperSon();
          setPhase("repos");
          endConversation();
          setErreur(new Error(t("Your browser could not play this audio.")));
        }
      };
      await applyAudioOutput(son);
      if (!actuel(numero)) return;
      await son.play();
      if (actuel(numero)) setPhase("lecture");
    } catch (cause) {
      if (!actuel(numero)) return;
      couperSon();
      endConversation();
      setPhase("repos");
      setErreur(
        cause instanceof TypeError
          ? cause
          : new Error(
              cause instanceof DOMException && cause.name === "NotAllowedError"
                ? t(
                    "Your browser requires a click to play audio. Select Listen to hear this reply.",
                  )
                : cause instanceof Error
                  ? cause.message
                  : t("Voice playback is unavailable."),
            ),
      );
    }
  }

  function envoyer(event: FormEvent) {
    event.preventDefault();
    if (!occupe) void envoyerTexte(brouillon);
  }

  async function envoyerTexte(value: string, continueConversation = false) {
    const texte = value.trim();
    if (!texte || texte.length > 4000) return;
    arreter(continueConversation);
    setReviewReady(false);
    setCaptureNote(null);
    const numero = generation.current;
    const controle = new AbortController();
    requete.current = controle;
    const suivants: Message[] = [
      ...latestMessages.current.slice(sendMessage ? -99 : -6),
      { role: "user", content: texte },
    ];
    const avant = latestMessages.current;
    envoiEnCours.current = { texte, avant };
    latestMessages.current = suivants;
    setMessages(suivants);
    setBrouillon("");
    setErreur(null);
    setPhase("reflexion");
    try {
      const resultat = sendMessage
        ? await sendMessage(texte, langue, controle.signal, (text) => {
            if (actuel(numero))
              setMessages([...suivants, { role: "assistant", content: text }]);
          })
        : await api<{ texte: string; usage?: unknown }>(
            "/assistant/dialogue",
            "POST",
            {
              langue,
              messages: suivants.map((message) => ({
                ...message,
                content: message.content.slice(0, 4000),
              })),
            },
            controle.signal,
          );
      if (!actuel(numero)) return;
      if (typeof resultat.texte !== "string" || !resultat.texte.trim())
        throw new Error(
          t("The local assistant returned an empty reply. Please try again."),
        );
      envoiEnCours.current = null;
      const usage = reportedUsage(resultat.usage);
      setLastUsage(usage);
      setSessionUsage((previous) => ({
        total: previous.total + (usage.total_tokens ?? 0),
        reported: previous.reported + (usage.total_tokens === null ? 0 : 1),
        replies: previous.replies + 1,
      }));
      const updated = [
        ...suivants,
        { role: "assistant", content: resultat.texte },
      ].slice(sendMessage ? -100 : -7) as Message[];
      latestMessages.current = updated;
      setMessages(updated);
      setPhase("repos");
      if (continueConversation && handsFreeRef.current) {
        turns.current += 1;
        if (turns.current >= 20) {
          endConversation();
          notifier(
            t(
              "Conversation paused after 20 turns. Start again whenever you’re ready.",
            ),
          );
        }
        void lire(resultat.texte, handsFreeRef.current);
      } else if (automatiqueRef.current && voix?.pret)
        void lire(resultat.texte, false, true);
    } catch (cause) {
      if (!actuel(numero)) return;
      envoiEnCours.current = null;
      endConversation();
      latestMessages.current = avant;
      setMessages(avant);
      setBrouillon(texte);
      setPhase("repos");
      setErreur(
        cause instanceof Error
          ? cause
          : new Error(
              t("The local assistant did not respond. Please try again."),
            ),
      );
    }
  }

  async function dicter(continueConversation = false) {
    if (!microDisponible) {
      endConversation();
      setErreur(
        new Error(
          t(
            "Recording is unavailable in this browser. Use a recent browser on localhost or type your message.",
          ),
        ),
      );
      return;
    }
    arreter(continueConversation);
    const numero = generation.current;
    setErreur(null);
    setReviewReady(false);
    setMicroLevel(0);
    setCaptureNote(null);
    setMonitorBlocked(false);
    setPhase("permission");
    setSecondes(0);
    prepareMicrophoneSignal();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
      if (!actuel(numero)) {
        stream.getTracks().forEach((piste) => piste.stop());
        return;
      }
      flux.current = stream;
      attachMicrophoneSignal(stream);
      const format = [
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(
        stream,
        format ? { mimeType: format } : undefined,
      );
      enregistreur.current = recorder;
      const morceaux: Blob[] = [];
      let taille = 0,
        invalide = false;
      recorder.ondataavailable = (event) => {
        if (!actuel(numero) || invalide) return;
        taille += event.data.size;
        if (taille > MAX_AUDIO) {
          invalide = true;
          couperMicro();
          endConversation();
          setPhase("repos");
          setErreur(
            new Error(
              t(
                "The recording exceeds 8 MiB. Please record a shorter message.",
              ),
            ),
          );
        } else if (event.data.size) morceaux.push(event.data);
      };
      recorder.onerror = () => {
        if (!actuel(numero)) return;
        invalide = true;
        couperMicro();
        endConversation();
        setPhase("repos");
        setErreur(
          new Error(
            t("Your browser interrupted the recording. Please try again."),
          ),
        );
      };
      recorder.onstop = async () => {
        if (!actuel(numero) || invalide) return;
        couperMicro();
        if (!taille) {
          endConversation();
          setPhase("repos");
          setErreur(new Error(t("No audio was recorded. Please try again.")));
          return;
        }
        setPhase("transcription");
        const controle = new AbortController();
        requete.current = controle;
        try {
          const audio = await encoderAudio(
            new Blob(morceaux, { type: recorder.mimeType }),
          );
          if (!actuel(numero)) return;
          const resultat = await api<{ texte: string }>(
            "/voix/transcrire",
            "POST",
            { audio, langue },
            controle.signal,
          );
          if (!actuel(numero)) return;
          if (!resultat.texte?.trim())
            throw new Error(
              t(
                "No speech was detected. Try speaking closer to the microphone.",
              ),
            );
          const complet = [
            continueConversation ? "" : brouillon.trim(),
            resultat.texte.trim(),
          ]
            .filter(Boolean)
            .join("\n");
          if (complet.length > 4000)
            throw new Error(
              t(
                "This transcript would exceed the 4,000-character message limit. Your draft is saved here; please record a shorter message.",
              ),
            );
          setBrouillon(complet);
          setPhase("repos");
          if (continueConversation && handsFreeRef.current) {
            void envoyerTexte(complet, true);
          } else {
            setReviewReady(true);
            notifier(t("Transcript ready. Review the text, then select Send."));
          }
        } catch (cause) {
          if (!actuel(numero)) return;
          endConversation();
          setPhase("repos");
          setErreur(
            cause instanceof Error
              ? cause
              : new Error(t("Transcription is unavailable. Please try again.")),
          );
        }
      };
      recorder.start(1000);
      setPhase("micro");
      const debut = Date.now();
      const activity = inputActivity(debut);
      stream.getAudioTracks?.().forEach((track) => {
        track.addEventListener?.(
          "ended",
          () => {
            if (!actuel(numero) || flux.current !== stream) return;
            invalide = true;
            arreter();
            setErreur(
              new Error(
                t(
                  "The microphone was disconnected. Reconnect it or choose another input, then record again.",
                ),
              ),
            );
          },
          { once: true },
        );
      });
      minuterie.current = setInterval(() => {
        if (!actuel(numero)) return;
        const duree = Math.floor((Date.now() - debut) / 1000);
        setSecondes(Math.min(90, duree));
        const frame = signal.current?.();
        const measured = activity(frame, Date.now());
        setMicroLevel(frame?.level || 0);
        const muted = stream
          .getAudioTracks?.()
          .some((track) => track.muted || !track.enabled);
        setMonitorBlocked(!measured.available);
        setCaptureNote(
          muted
            ? "Your microphone is muted. Unmute it in your device or system settings."
            : !measured.available
              ? "The browser paused microphone monitoring. Recording still works; stop to review the transcript or enable monitoring."
              : measured.heard
                ? "Input signal detected."
                : duree >= 3
                  ? "No input signal yet. Check the selected microphone, hardware mute and system input level."
                  : "Speak naturally and watch the input meter.",
        );
        if (continueConversation && handsFreeRef.current) {
          if (!measured.available && duree >= 1) {
            // Missing analyser data is not evidence of silence. Keep the
            // recording for manual review rather than discard a spoken turn.
            endConversation();
            return;
          }
          if (measured.heard && measured.silence > 1600 && duree >= 2) {
            couperMicro();
            return;
          }
          if (!measured.heard && duree >= 12) {
            endConversation();
            notifier(
              t(
                "No input signal was detected. The recording will be transcribed for review; check your microphone.",
              ),
            );
            couperMicro();
            return;
          }
        }
        if (duree >= 90) couperMicro();
      }, 100);
    } catch (cause) {
      if (!actuel(numero)) return;
      couperMicro();
      endConversation();
      setPhase("repos");
      const nom =
        cause &&
        typeof cause === "object" &&
        "name" in cause &&
        typeof cause.name === "string"
          ? cause.name
          : "";
      setErreur(
        new Error(
          erreursMicro[nom] ||
            t(
              "The microphone is unavailable. You can still type your message.",
            ),
        ),
      );
    }
  }

  const etats: Record<Phase, string> = {
    repos: reviewReady
      ? t("Transcript ready. Review the text, then select Send.")
      : t("Ready when you are"),
    permission: t("Waiting for microphone permission…"),
    micro: t("Recording · {seconds} / 90 s", { seconds: secondes }),
    transcription: t("Transcribing on your device…"),
    reflexion: t("AURA is thinking locally…"),
    synthese: t("Preparing local voice playback…"),
    lecture: t("Speaking…"),
  };

  const corePhase: CorePhase =
    phase === "micro"
      ? "listening"
      : phase === "lecture"
        ? "speaking"
        : phase === "reflexion"
          ? "thinking"
          : phase === "repos"
            ? "idle"
            : "loading";

  return (
    <>
      <Titre
        surligne={t("AURA · LOCAL INTELLIGENCE")}
        titre={t("Voice assistant")}
        texte={t(
          "A conversation that stays with you. Think, speak and explore with your private AI assistant.",
        )}
      >
        <button
          className="btn"
          disabled={(!messages.length && !onNew) || occupe}
          onClick={() => {
            arreter();
            if (onNew) {
              onNew();
              return;
            }
            latestMessages.current = [];
            setMessages([]);
            setBrouillon("");
            setErreur(null);
            setReviewReady(false);
            setLastUsage(null);
            setSessionUsage({ total: 0, reported: 0, replies: 0 });
          }}
        >
          <Trash2 size={16} />{" "}
          {onNew ? t("New conversation") : t("Clear conversation")}
        </button>
      </Titre>
      <div className="aura-deck">
        <section
          className="aura-stage panel"
          aria-label={t("AURA voice interface")}
        >
          <div className="instrument-heading">
            <span>
              <i
                className={
                  "health-dot " +
                  (voix?.pret
                    ? "healthy"
                    : voix || erreurVoix
                      ? "unhealthy"
                      : "checking")
                }
                aria-hidden="true"
              />{" "}
              {t("LOCAL VOICE INTERFACE")}
            </span>
            <span>01 / AURA</span>
          </div>
          <NeuralCore phase={corePhase} signal={signal} />
          <div className="aura-identity">
            <span className="eyebrow">{t("YOUR PRIVATE AI ASSISTANT")}</span>
            <h2>
              {t("AURA")}
              <span>—</span>
            </h2>
            <p>
              {etats[phase]}
              {["transcription", "reflexion", "synthese"].includes(phase) &&
              waitingSeconds > 0
                ? ` · ${waitingSeconds} s`
                : ""}
            </p>
          </div>
          {phase === "micro" && (
            <div
              className="microphone-diagnostic"
              aria-label={t("Microphone diagnostics")}
            >
              <strong>{t("Microphone input")}</strong>
              <meter
                min={0}
                max={1}
                value={microLevel}
                aria-label={t("Measured input level")}
              />
              <p aria-live="polite">
                {captureNote
                  ? t(captureNote)
                  : t("Speak naturally and watch the input meter.")}
              </p>
              <p>
                {handsFree
                  ? t(
                      "Pause briefly when you finish. You can also send this turn now.",
                    )
                  : t(
                      "Finish recording to see your text. Review it, then select Send to receive a reply.",
                    )}
              </p>
              <div className="microphone-diagnostic-actions">
                <button
                  type="button"
                  className="btn primary"
                  onClick={couperMicro}
                >
                  {handsFree ? t("Send this turn") : t("Finish recording")}
                </button>
                {monitorBlocked && !!window.AudioContext && (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => {
                      const context = microphoneContext.current;
                      if (context)
                        void context.resume().catch(() => {
                          if (vivant.current)
                            setErreur(
                              new Error(
                                t(
                                  "Microphone monitoring is still blocked. Finish recording to review the transcript.",
                                ),
                              ),
                            );
                        });
                      else if (flux.current) {
                        prepareMicrophoneSignal();
                        attachMicrophoneSignal(flux.current);
                      }
                    }}
                  >
                    {t("Enable microphone monitoring")}
                  </button>
                )}
              </div>
            </div>
          )}
          <div className="aura-mode">
            {handsFree ? (
              <>
                <button className="btn danger" onClick={() => arreter()}>
                  <Square size={16} /> {t("End conversation")}
                </button>
                {phase === "lecture" && (
                  <button className="btn" onClick={() => void dicter(true)}>
                    <Mic size={16} /> {t("Speak now")}
                  </button>
                )}
              </>
            ) : (
              <button
                className="btn primary"
                disabled={
                  !voix?.pret ||
                  !microDisponible ||
                  occupe ||
                  !!brouillon.trim()
                }
                onClick={() => {
                  arreter();
                  turns.current = 0;
                  handsFreeRef.current = true;
                  setHandsFree(true);
                  void dicter(true);
                }}
              >
                <AudioLines size={17} /> {t("Start conversation")}
              </button>
            )}
            <p>
              {handsFree
                ? t(
                    "Listening resumes after each reply. Esc ends the conversation.",
                  )
                : t(
                    "Hands-free mode sends speech after a pause and reads replies aloud. Up to 20 turns.",
                  )}
            </p>
          </div>
          {!handsFree && brouillon.trim() && (
            <p className="aura-draft-hint">
              {t("Send or clear your draft before starting hands-free mode.")}
            </p>
          )}
          <div className="aura-controls">
            <label htmlFor="voice-language">{t("Conversation language")}</label>
            <select
              id="voice-language"
              value={langue}
              disabled={handsFree || occupe}
              onChange={(event) => {
                arreter();
                setLangue(event.target.value as "en" | "fr");
              }}
            >
              <option value="en">{t("English · female voice")}</option>
              <option value="fr">{t("French · female voice")}</option>
            </select>
            <div className="voice-state">
              <span>{t("Voice engine")}</span>
              <strong>
                {voix?.pret
                  ? t("Ready")
                  : erreurVoix || voix
                    ? t("Unavailable")
                    : t("Checking…")}
              </strong>
            </div>
            <div className="voice-state">
              <span>{t("Microphone")}</span>
              <strong>{phase === "micro" ? t("Recording") : t("Off")}</strong>
            </div>
          </div>
          <p className="hint">
            {t("AURA uses your system’s default microphone and speakers.")}
          </p>
        </section>
        <div className="chat-layout">
          <section
            className="panel chat-panel"
            aria-label={t("Assistant conversation")}
          >
            <div
              className="chat-messages"
              ref={conversation}
              role="log"
              aria-label={t("Conversation messages")}
              aria-live="polite"
              aria-relevant="additions"
            >
              {!messages.length && (
                <div className="chat-welcome">
                  <span className="tile-icon">
                    <AudioLines size={28} />
                  </span>
                  <h2>{t("Let’s think this through.")}</h2>
                  <p>
                    {t(
                      "Ask AURA a question, use Record to review a transcript, or start a hands-free conversation.",
                    )}
                  </p>
                  <div className="chat-suggestions">
                    {[
                      t("How do I start an analysis?"),
                      t("How do the agents work?"),
                      t("How do I back up my platform?"),
                    ].map((suggestion) => (
                      <button
                        key={suggestion}
                        disabled={occupe || handsFree}
                        onClick={() => {
                          setBrouillon(suggestion);
                          champ.current?.focus();
                        }}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((message, index) => (
                <article className={"chat-message " + message.role} key={index}>
                  <div className="message-avatar" aria-hidden="true">
                    {message.role === "assistant" ? (
                      <Bot size={17} />
                    ) : (
                      t("YOU")
                    )}
                  </div>
                  <div className="message-body">
                    <strong>
                      {message.role === "assistant" ? t("AURA") : t("You")}
                    </strong>
                    {message.role === "assistant" ? (
                      <Markdown texte={message.content} />
                    ) : (
                      <p>{message.content}</p>
                    )}
                    {message.role === "assistant" && (
                      <div className="message-actions">
                        <button
                          disabled={occupe || !voix?.pret}
                          onClick={() => void lire(message.content)}
                          aria-label={t("Listen")}
                        >
                          <Volume2 size={14} /> {t("Listen")}
                          {message.content.length > 2000 ? (
                            <>
                              {" "}
                              · <span>{t("excerpt")}</span>
                            </>
                          ) : null}
                        </button>
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
            <div className="chat-status" role="status">
              {phase === "repos" ? (
                <Check size={14} />
              ) : phase === "micro" ? (
                <Mic size={15} />
              ) : phase === "lecture" ? (
                <AudioLines size={15} />
              ) : (
                <LoaderCircle size={15} className="spin" />
              )}
              <span>
                {etats[phase]}
                {["transcription", "reflexion", "synthese"].includes(phase) &&
                waitingSeconds > 0
                  ? ` · ${waitingSeconds} s`
                  : ""}
              </span>
            </div>
            {phase === "reflexion" && waitingSeconds >= 15 && (
              <p className="chat-waiting" role="status">
                {t(
                  "The first reply can take longer while local inference starts. You can stop at any time.",
                )}
              </p>
            )}
            {erreur && <Erreur erreur={erreur} />}
            {!handsFree && phase === "repos" && (
              <p className="voice-step-hint">
                {reviewReady
                  ? t(
                      "Your transcript is ready below. Edit it if needed, then select Send. Nothing has been sent to AURA yet.",
                    )
                  : t(
                      "AURA only listens after you select Record or Start conversation. With Record, finish recording and select Send after reviewing your text.",
                    )}
              </p>
            )}
            <form className="chat-compose" onSubmit={envoyer}>
              {composerExtra && (
                <fieldset
                  className="attachment-controls"
                  disabled={occupe || handsFree}
                >
                  {composerExtra}
                </fieldset>
              )}
              <label className="sr-only" htmlFor="message-assistante">
                {t("Your message")}
              </label>
              <textarea
                ref={champ}
                id="message-assistante"
                value={brouillon}
                maxLength={4000}
                disabled={occupe || handsFree}
                rows={3}
                placeholder={t("Type a message or record your thoughts…")}
                onChange={(event) => setBrouillon(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    (event.ctrlKey || event.metaKey)
                  ) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <div className="compose-actions">
                <div>
                  <button
                    type="button"
                    className={
                      "btn " + (phase === "micro" ? "recording-button" : "")
                    }
                    onClick={
                      phase === "micro" ? couperMicro : () => void dicter()
                    }
                    disabled={phase !== "micro" && (occupe || !voix?.pret)}
                    aria-label={
                      phase === "micro" ? t("Stop recording") : t("Record")
                    }
                  >
                    {phase === "micro" ? (
                      <Square size={15} />
                    ) : (
                      <Mic size={16} />
                    )}{" "}
                    {phase === "micro" ? t("Stop recording") : t("Record")}
                  </button>
                  {phase !== "repos" && phase !== "micro" && (
                    <button
                      type="button"
                      className="btn small"
                      onClick={() => arreter()}
                    >
                      <Square size={14} />{" "}
                      {phase === "synthese" || phase === "lecture"
                        ? t("Stop playback")
                        : t("Stop")}
                    </button>
                  )}
                </div>
                <button
                  type="submit"
                  className="btn primary"
                  disabled={occupe || handsFree || !brouillon.trim()}
                >
                  <Send size={16} /> {t("Send")}
                </button>
              </div>
              <div className="field-foot">
                <span>
                  <CornerDownLeft size={12} /> {t("Ctrl / ⌘ + Enter to send")}
                </span>
                <span>{t("{count} / 4,000", { count: brouillon.length })}</span>
              </div>
            </form>
          </section>
          <aside className="voice-aside">
            <section
              className="panel instruction-card"
              aria-label={t("Reported token usage")}
            >
              <h2>{t("Reported token usage")}</h2>
              <dl className="token-usage">
                <div>
                  <dt>{t("Last input context")}</dt>
                  <dd>
                    {lastUsage?.prompt_tokens != null
                      ? number(lastUsage.prompt_tokens)
                      : t("Not reported")}
                  </dd>
                </div>
                <div>
                  <dt>{t("Last reply")}</dt>
                  <dd>
                    {lastUsage?.completion_tokens != null
                      ? number(lastUsage.completion_tokens)
                      : t("Not reported")}
                  </dd>
                </div>
                <div>
                  <dt>{t("Session · reported total")}</dt>
                  <dd>
                    {sessionUsage.reported
                      ? number(sessionUsage.total)
                      : t("Not reported")}
                  </dd>
                </div>
              </dl>
              <p className="hint">
                {t("Usage reported for {count} of {total} completed replies.", {
                  count: number(sessionUsage.reported),
                  total: number(sessionUsage.replies),
                })}
              </p>
              <p className="hint">
                {t(
                  "Input includes instructions and up to seven messages. Older messages leave the context window. Each reply is capped at 650 output tokens.",
                )}
              </p>
              <p className="hint">
                {t(
                  "Unknown usage is not zero. Interrupted or failed requests may still consume tokens. These counters reset when you clear or leave this conversation.",
                )}
              </p>
            </section>
            <section className="panel instruction-card">
              <span className="tile-icon">
                <Headphones size={23} />
              </span>
              <h2>{t("A private conversation.")}</h2>
              <p>
                {t(
                  "Voice, transcription, and replies run locally on your device.",
                )}
              </p>
              <div className="voice-state">
                <span>{t("Voice engine")}</span>
                <strong>
                  {voix?.pret
                    ? t("Ready")
                    : erreurVoix || voix
                      ? t("Unavailable")
                      : t("Checking…")}
                </strong>
              </div>
              <div className="voice-state">
                <span>{t("Voice")}</span>
                <strong>
                  {langue === "en"
                    ? t("English · female voice")
                    : t("French · female voice")}
                </strong>
              </div>
              <div className="voice-state">
                <span>{t("Microphone")}</span>
                <strong>
                  {phase === "micro"
                    ? t("Recording")
                    : microDisponible
                      ? t("Only when you record")
                      : t("Not supported")}
                </strong>
              </div>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={automatique}
                  disabled={!voix?.pret || handsFree}
                  onChange={(event) => {
                    automatiqueRef.current = event.target.checked;
                    setAutomatique(event.target.checked);
                    if (!event.target.checked && automaticSpeech.current)
                      arreter();
                  }}
                />{" "}
                {t("Read replies automatically")}
              </label>
              {!voix?.pret && (erreurVoix || voix) && (
                <p className="hint">
                  {t(
                    "Voice is unavailable. You can continue chatting by text. Check the voice engine from the terminal to restore audio.",
                  )}
                </p>
              )}
            </section>
            <section className="panel instruction-card">
              <span className="tile-icon">
                <ShieldCheck size={23} />
              </span>
              <h2>{t("You’re in control.")}</h2>
              <p>
                {t(
                  "Record lets you review before sending. Conversation mode sends transcripts automatically. Voice replies never approve an action.",
                )}
              </p>
              <p>
                {t(
                  "Need a diagnosis with evidence and approval? Start a supervised analysis.",
                )}
              </p>
              <Link className="text-button" to="/analyses/nouvelle">
                <Workflow size={15} /> {t("New analysis")}
              </Link>
            </section>
            <div className="voice-disclaimer">
              <LockKeyhole size={16} />
              <p>
                {t(
                  sendMessage
                    ? "Saved locally for 30 days after the last activity. AURA uses recent messages and the attachments you select. Audio recordings are not saved. Delete conversations from History."
                    : "This conversation is temporary. The last seven messages provide context. Leaving this page clears the conversation. Recordings are not stored permanently.",
                )}
              </p>
              <p>
                {langue === "en"
                  ? t("Synthetic voice · Apache-2.0 model.")
                  : t(
                      "French training: SIWIS · University of Edinburgh · CC BY 4.0.",
                    )}{" "}
                {t(
                  "Synthetic AI voice. Playback is limited to 2,000 characters per reply. Conversation uses successive local processing steps; response times depend on this device.",
                )}
              </p>
            </div>
          </aside>
        </div>
      </div>
    </>
  );
}
