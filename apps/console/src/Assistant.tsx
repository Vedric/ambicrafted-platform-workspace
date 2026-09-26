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

export function texteOral(texte: string): string {
  return texte
    .replace(/```[\s\S]*?```/g, " A code example is available on screen. ")
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
        : reject(new Error("Unable to read the audio recording."));
    lecteur.onerror = () =>
      reject(new Error("Unable to read the audio recording."));
    lecteur.readAsDataURL(blob);
  });
}

const erreursMicro: Record<string, string> = {
  NotAllowedError:
    "Microphone access was denied. Allow access in your browser’s site settings.",
  NotFoundError: "No microphone was found. Connect one or type your message.",
  NotReadableError:
    "The microphone is unavailable or in use by another application.",
  SecurityError:
    "Your browser blocked microphone access. Open the platform on localhost.",
};

export default function Assistant() {
  const notifier = useToast();
  const [messages, setMessages] = useState<Message[]>([]);
  const [brouillon, setBrouillon] = useState("");
  const [phase, setPhase] = useState<Phase>("repos");
  const [secondes, setSecondes] = useState(0);
  const [automatique, setAutomatique] = useState(false);
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

  function couperMicro() {
    if (minuterie.current) clearInterval(minuterie.current);
    minuterie.current = null;
    if (enregistreur.current?.state === "recording")
      enregistreur.current.stop();
    flux.current?.getTracks().forEach((piste) => piste.stop());
    flux.current = null;
    enregistreur.current = null;
  }

  function couperSon() {
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

  function arreter() {
    generation.current += 1;
    requete.current?.abort();
    requete.current = null;
    couperMicro();
    couperSon();
    if (vivant.current) {
      setPhase("repos");
      if (envoiEnCours.current) {
        setBrouillon(envoiEnCours.current.texte);
        setMessages(envoiEnCours.current.avant);
      }
    }
    envoiEnCours.current = null;
  }

  useEffect(() => {
    vivant.current = true;
    const controle = new AbortController();
    api<EtatVoix>("/voix/statut", "GET", undefined, controle.signal)
      .then((resultat) => {
        if (vivant.current && !controle.signal.aborted) setVoix(resultat);
      })
      .catch(() => {
        if (vivant.current && !controle.signal.aborted) setErreurVoix(true);
      });
    return () => {
      vivant.current = false;
      controle.abort();
      arreter();
    };
  }, []);

  useEffect(() => {
    if (conversation.current)
      conversation.current.scrollTop = conversation.current.scrollHeight;
  }, [messages, phase]);

  async function lire(texte: string) {
    const oral = texteOral(texte);
    if (!oral) {
      notifier("This reply has no text to read aloud.");
      return;
    }
    arreter();
    const numero = generation.current;
    const controle = new AbortController();
    requete.current = controle;
    setErreur(null);
    setPhase("synthese");
    try {
      const audio = await audioLocal(oral, controle.signal);
      if (!actuel(numero)) return;
      const url = URL.createObjectURL(audio);
      urlAudio.current = url;
      const son = new Audio(url);
      lecteur.current = son;
      son.onended = () => {
        if (actuel(numero)) {
          couperSon();
          setPhase("repos");
        }
      };
      son.onerror = () => {
        if (actuel(numero)) {
          couperSon();
          setPhase("repos");
          setErreur(new Error("Your browser could not play this audio."));
        }
      };
      await son.play();
      if (actuel(numero)) setPhase("lecture");
    } catch (cause) {
      if (!actuel(numero)) return;
      couperSon();
      setPhase("repos");
      setErreur(
        new Error(
          cause instanceof DOMException && cause.name === "NotAllowedError"
            ? "Your browser requires a click to play audio. Select Listen to hear this reply."
            : cause instanceof Error
              ? cause.message
              : "Voice playback is unavailable.",
        ),
      );
    }
  }

  async function envoyer(event: FormEvent) {
    event.preventDefault();
    const texte = brouillon.trim();
    if (!texte || texte.length > 4000 || occupe) return;
    arreter();
    const numero = generation.current;
    const controle = new AbortController();
    requete.current = controle;
    const suivants: Message[] = [
      ...messages.slice(-6),
      { role: "user", content: texte },
    ];
    envoiEnCours.current = { texte, avant: messages };
    setMessages(suivants);
    setBrouillon("");
    setErreur(null);
    setPhase("reflexion");
    try {
      const resultat = await api<{ texte: string }>(
        "/assistant/dialogue",
        "POST",
        {
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
          "The local assistant returned an empty reply. Please try again.",
        );
      envoiEnCours.current = null;
      setMessages(
        [...suivants, { role: "assistant", content: resultat.texte }].slice(
          -7,
        ) as Message[],
      );
      setPhase("repos");
      if (automatique && voix?.pret) void lire(resultat.texte);
    } catch (cause) {
      if (!actuel(numero)) return;
      envoiEnCours.current = null;
      setMessages(messages);
      setBrouillon(texte);
      setPhase("repos");
      setErreur(
        cause instanceof Error
          ? cause
          : new Error("The local assistant did not respond. Please try again."),
      );
    }
  }

  async function dicter() {
    if (!microDisponible) {
      setErreur(
        new Error(
          "Recording is unavailable in this browser. Use a recent browser on localhost or type your message.",
        ),
      );
      return;
    }
    arreter();
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
          setPhase("repos");
          setErreur(
            new Error(
              "The recording exceeds 8 MiB. Please record a shorter message.",
            ),
          );
        } else if (event.data.size) morceaux.push(event.data);
      };
      recorder.onerror = () => {
        if (!actuel(numero)) return;
        invalide = true;
        couperMicro();
        setPhase("repos");
        setErreur(
          new Error(
            "Your browser interrupted the recording. Please try again.",
          ),
        );
      };
      recorder.onstop = async () => {
        if (!actuel(numero) || invalide) return;
        couperMicro();
        if (!taille) {
          setPhase("repos");
          setErreur(new Error("No audio was recorded. Please try again."));
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
            { audio },
            controle.signal,
          );
          if (!actuel(numero)) return;
          if (!resultat.texte?.trim())
            throw new Error(
              "No speech was detected. Try speaking closer to the microphone.",
            );
          const complet = [brouillon.trim(), resultat.texte.trim()]
            .filter(Boolean)
            .join("\n");
          if (complet.length > 4000)
            throw new Error(
              "This transcript would exceed the 4,000-character message limit. Your draft is saved here; please record a shorter message.",
            );
          setBrouillon(complet);
          setPhase("repos");
          notifier("Transcript ready. Review the text, then select Send.");
        } catch (cause) {
          if (!actuel(numero)) return;
          setPhase("repos");
          setErreur(
            cause instanceof Error
              ? cause
              : new Error("Transcription is unavailable. Please try again."),
          );
        }
      };
      recorder.start(1000);
      setPhase("micro");
      const debut = Date.now();
      minuterie.current = setInterval(() => {
        if (!actuel(numero)) return;
        const duree = Math.floor((Date.now() - debut) / 1000);
        setSecondes(Math.min(90, duree));
        if (duree >= 90) couperMicro();
      }, 1000);
    } catch (cause) {
      if (!actuel(numero)) return;
      couperMicro();
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
            "The microphone is unavailable. You can still type your message.",
        ),
      );
    }
  }

  const etats: Record<Phase, string> = {
    repos: "Ready when you are",
    permission: "Waiting for microphone permission…",
    micro: `Recording · ${secondes} / 90 s`,
    transcription: "Transcribing on your device…",
    reflexion: "Preparing your reply…",
    synthese: "Preparing local voice playback…",
    lecture: "Speaking…",
  };

  return (
    <>
      <Titre
        surligne="PRIVATE, BY DESIGN"
        titre="Voice assistant"
        texte="Think out loud. Get a fresh perspective. Chat privately on your device, with an optional French female voice."
      >
        <button
          className="btn"
          disabled={!messages.length || occupe}
          onClick={() => {
            arreter();
            setMessages([]);
            setBrouillon("");
            setErreur(null);
          }}
        >
          <Trash2 size={16} /> Clear conversation
        </button>
      </Titre>
      <div className="chat-layout">
        <section
          className="panel chat-panel"
          aria-label="Assistant conversation"
        >
          <div
            className="chat-messages"
            ref={conversation}
            role="log"
            aria-label="Conversation messages"
            aria-live="polite"
            aria-relevant="additions"
          >
            {!messages.length && (
              <div className="chat-welcome">
                <div
                  className={
                    "voice-orb " +
                    (phase === "micro"
                      ? "listening"
                      : phase === "lecture"
                        ? "speaking"
                        : "")
                  }
                  aria-hidden="true"
                >
                  <AudioLines size={37} />
                </div>
                <h2>What’s your next move?</h2>
                <p>
                  Explore a signal, find a procedure, or plan your next step.
                  Start with a question.
                </p>
                <div className="chat-suggestions">
                  {[
                    "How do I start an analysis?",
                    "How do the agents work?",
                    "How do I back up my platform?",
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
                  {message.role === "assistant" ? <Bot size={17} /> : "YOU"}
                </div>
                <div className="message-body">
                  <strong>
                    {message.role === "assistant" ? "Your assistant" : "You"}
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
                        aria-label="Listen"
                      >
                        <Volume2 size={14} /> Listen
                        {message.content.length > 2000 ? " · excerpt" : ""}
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
          {erreur && <Erreur erreur={erreur} />}
          <form className="chat-compose" onSubmit={envoyer}>
            <label className="sr-only" htmlFor="message-assistante">
              Your message
            </label>
            <textarea
              ref={champ}
              id="message-assistante"
              value={brouillon}
              maxLength={4000}
              disabled={occupe}
              rows={3}
              placeholder="Type a message or record your thoughts…"
              onChange={(event) => setBrouillon(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
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
                  aria-label={phase === "micro" ? "Stop recording" : "Record"}
                >
                  {phase === "micro" ? <Square size={15} /> : <Mic size={16} />}{" "}
                  {phase === "micro" ? "Stop recording" : "Record"}
                </button>
                {phase !== "repos" && phase !== "micro" && (
                  <button type="button" className="btn small" onClick={arreter}>
                    <Square size={14} />{" "}
                    {phase === "synthese" || phase === "lecture"
                      ? "Stop playback"
                      : "Stop"}
                  </button>
                )}
              </div>
              <button
                type="submit"
                className="btn primary"
                disabled={occupe || !brouillon.trim()}
              >
                <Send size={16} /> Send
              </button>
            </div>
            <div className="field-foot">
              <span>
                <CornerDownLeft size={12} /> Ctrl / ⌘ + Enter to send
              </span>
              <span>{brouillon.length} / 4,000</span>
            </div>
          </form>
        </section>
        <aside className="voice-aside">
          <section className="panel instruction-card">
            <span className="tile-icon">
              <Headphones size={23} />
            </span>
            <h2>A private conversation.</h2>
            <p>Voice, transcription, and replies run locally on your device.</p>
            <div className="voice-state">
              <span>Voice engine</span>
              <strong>
                {voix?.pret
                  ? "Ready"
                  : erreurVoix || voix
                    ? "Unavailable"
                    : "Checking…"}
              </strong>
            </div>
            <div className="voice-state">
              <span>Voice</span>
              <strong>French female voice</strong>
            </div>
            <div className="voice-state">
              <span>Microphone</span>
              <strong>
                {phase === "micro"
                  ? "Recording"
                  : microDisponible
                    ? "Only when you record"
                    : "Not supported"}
              </strong>
            </div>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={automatique}
                disabled={!voix?.pret}
                onChange={(event) => setAutomatique(event.target.checked)}
              />{" "}
              Read replies automatically
            </label>
            {!voix?.pret && (erreurVoix || voix) && (
              <p className="hint">
                Voice is unavailable. You can continue chatting by text. Check
                the voice engine from the terminal to restore audio.
              </p>
            )}
          </section>
          <section className="panel instruction-card">
            <span className="tile-icon">
              <ShieldCheck size={23} />
            </span>
            <h2>You’re in control.</h2>
            <p>
              Review every transcript before sending. Voice replies never
              approve an action.
            </p>
            <p>
              Need a diagnosis with evidence and approval? Start a supervised
              analysis.
            </p>
            <Link className="text-button" to="/analyses/nouvelle">
              <Workflow size={15} /> New analysis
            </Link>
          </section>
          <div className="voice-disclaimer">
            <LockKeyhole size={16} />
            <p>
              This conversation is temporary. The last seven messages provide
              context. Leaving this page clears the conversation. Recordings are
              not stored permanently.
            </p>
            <p>
              SIWIS voice · University of Edinburgh · CC BY 4.0. Playback is
              limited to 2,000 characters per reply.
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}
