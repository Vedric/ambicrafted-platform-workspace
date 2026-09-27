import { t, useI18n } from "./i18n";
import { useEffect, useRef, useState, type FormEvent } from "react";
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
import { pcmSignal, waveform, type SignalReader } from "./audio-signal";
import { api, audioLocal } from "./api";
import { Erreur, Markdown, Titre, useToast } from "./ui";

type Message = { role: "user" | "assistant"; content: string };
type EtatVoix = { pret: boolean; local: boolean; voix: string; langue: string };
type Phase =
  | "repos"
  | "permission"
  | "micro"
  | "transcription"
  | "reflexion"
  | "synthese"
  | "lecture";
const MAX_AUDIO = 8 * 1024 * 1024;

export function texteOral(texte: string, langue: "en" | "fr" = "en"): string {
  return texte
    .replace(
      /```[\s\S]*?```/g,
      langue === "fr"
        ? " Un exemple de code est disponible à l’écran. "
        : " A code example is available on screen. ",
    )
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/<[^>]*>/g, " ")
    .replace(/^\s{0,3}(?:#{1,6}|>|[-*+] |\d+\. )/gm, " ")
    .replace(/[`*_~|]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 2000)
    .replace(/[\uD800-\uDBFF]$/, "");
}

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
};

export default function Assistant() {
  useI18n();
  const notifier = useToast();
  const [messages, setMessages] = useState<Message[]>([]);
  const [brouillon, setBrouillon] = useState("");
  const [phase, setPhase] = useState<Phase>("repos");
  const [secondes, setSecondes] = useState(0);
  const [waitingSeconds, setWaitingSeconds] = useState(0);
  const [automatique, setAutomatique] = useState(false);
  const automatiqueRef = useRef(false);
  const automaticSpeech = useRef(false);
  const [langue, setLangue] = useState<"en" | "fr">("en");
  const [handsFree, setHandsFree] = useState(false);
  const handsFreeRef = useRef(false);
  const turns = useRef(0);
  const nextTurn = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestMessages = useRef<Message[]>([]);
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
  const occupe = phase !== "repos" && phase !== "lecture";
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

  function attachMicrophoneSignal(stream: MediaStream) {
    try {
      if (!window.AudioContext) return;
      const context = new AudioContext();
      microphoneContext.current = context;
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
    if (phase !== "reflexion") return;
    const start = Date.now();
    const interval = setInterval(
      () => setWaitingSeconds(Math.floor((Date.now() - start) / 1000)),
      1000,
    );
    return () => clearInterval(interval);
  }, [phase]);

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
    const numero = generation.current;
    const controle = new AbortController();
    requete.current = controle;
    const suivants: Message[] = [
      ...latestMessages.current.slice(-6),
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
      const resultat = await api<{ texte: string }>(
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
      const updated = [
        ...suivants,
        { role: "assistant", content: resultat.texte },
      ].slice(-7) as Message[];
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
    setPhase("permission");
    setSecondes(0);
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
          } else
            notifier(t("Transcript ready. Review the text, then select Send."));
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
      let lastSpeech = debut,
        heardSpeech = false;
      minuterie.current = setInterval(() => {
        if (!actuel(numero)) return;
        const duree = Math.floor((Date.now() - debut) / 1000);
        setSecondes(Math.min(90, duree));
        if (continueConversation && handsFreeRef.current) {
          const frame = signal.current?.();
          if (frame && frame.level > 0.08) {
            heardSpeech = true;
            lastSpeech = Date.now();
          }
          if (heardSpeech && Date.now() - lastSpeech > 1600 && duree >= 2) {
            couperMicro();
            return;
          }
          if (!heardSpeech && duree >= 12) {
            arreter();
            notifier(
              t(
                "Conversation paused: no speech detected. Check your microphone or use Record.",
              ),
            );
            return;
          }
        }
        if (duree >= 90) couperMicro();
      }, 250);
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
    repos: t("Ready when you are"),
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
          disabled={!messages.length || occupe}
          onClick={() => {
            arreter();
            latestMessages.current = [];
            setMessages([]);
            setBrouillon("");
            setErreur(null);
          }}
        >
          <Trash2 size={16} /> {t("Clear conversation")}
        </button>
      </Titre>
      <div className="aura-deck">
        <section
          className="aura-stage panel"
          aria-label={t("AURA voice interface")}
        >
          <div className="instrument-heading">
            <span>
              <i className="health-dot healthy" /> {t("LOCAL VOICE INTERFACE")}
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
            <p>{etats[phase]}</p>
          </div>
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
                disabled={!voix?.pret || !microDisponible || occupe}
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
                        disabled={occupe}
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
              <span>{etats[phase]}</span>
            </div>
            {phase === "reflexion" && waitingSeconds >= 15 && (
              <p className="chat-waiting" role="status">
                {t(
                  "The first reply can take longer while local inference starts. You can stop at any time.",
                )}
              </p>
            )}
            {erreur && <Erreur erreur={erreur} />}
            <form className="chat-compose" onSubmit={envoyer}>
              <label className="sr-only" htmlFor="message-assistante">
                {t("Your message")}
              </label>
              <textarea
                ref={champ}
                id="message-assistante"
                value={brouillon}
                maxLength={4000}
                disabled={occupe}
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
                  disabled={occupe || !brouillon.trim()}
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
                  "This conversation is temporary. The last seven messages provide context. Leaving this page clears the conversation. Recordings are not stored permanently.",
                )}
              </p>
              <p>
                {langue === "en"
                  ? t("LJSpeech voice · public domain.")
                  : t(
                      "SIWIS voice · University of Edinburgh · CC BY 4.0.",
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
