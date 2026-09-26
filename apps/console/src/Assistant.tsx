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
    .replace(
      /```[\s\S]*?```/g,
      " Un exemple de code est disponible à l’écran. ",
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
        : reject(new Error("Lecture audio impossible."));
    lecteur.onerror = () => reject(new Error("Lecture audio impossible."));
    lecteur.readAsDataURL(blob);
  });
}

const erreursMicro: Record<string, string> = {
  NotAllowedError:
    "L’accès au microphone est refusé. Autorisez-le dans les réglages de ce site.",
  NotFoundError:
    "Aucun microphone détecté. Connectez un microphone ou écrivez votre message.",
  NotReadableError:
    "Le microphone est utilisé par une autre application ou indisponible.",
  SecurityError:
    "Le navigateur bloque le microphone. Ouvrez la plateforme sur localhost.",
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
      notifier("Cette réponse ne contient pas de texte à lire.");
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
          setErreur(new Error("Le navigateur ne peut pas lire cet audio."));
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
            ? "Le navigateur demande un clic pour lire la voix. Cliquez sur Écouter la réponse."
            : cause instanceof Error
              ? cause.message
              : "La lecture vocale est indisponible.",
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
        throw new Error("La réponse locale est vide. Réessayez.");
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
          : new Error("Le modèle local n’a pas répondu."),
      );
    }
  }

  async function dicter() {
    if (!microDisponible) {
      setErreur(
        new Error(
          "Ce navigateur ne permet pas l’enregistrement. Utilisez un navigateur récent sur localhost ou écrivez votre message.",
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
              "L’enregistrement dépasse 8 Mio. Dictez un message plus court.",
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
          new Error("L’enregistrement a été interrompu par le navigateur."),
        );
      };
      recorder.onstop = async () => {
        if (!actuel(numero) || invalide) return;
        couperMicro();
        if (!taille) {
          setPhase("repos");
          setErreur(new Error("Aucun audio enregistré. Réessayez."));
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
              "Aucune parole reconnue. Réessayez en parlant plus près du microphone.",
            );
          const complet = [brouillon.trim(), resultat.texte.trim()]
            .filter(Boolean)
            .join("\n");
          if (complet.length > 4000)
            throw new Error(
              "Le message avec cette transcription dépasse 4 000 caractères. Votre brouillon est conservé ; dictez un message plus court.",
            );
          setBrouillon(complet);
          setPhase("repos");
          notifier(
            "Transcription prête. Vérifiez le texte, puis cliquez sur Envoyer.",
          );
        } catch (cause) {
          if (!actuel(numero)) return;
          setPhase("repos");
          setErreur(
            cause instanceof Error
              ? cause
              : new Error("Transcription indisponible."),
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
            "Le microphone est indisponible. Vous pouvez écrire votre message.",
        ),
      );
    }
  }

  const etats: Record<Phase, string> = {
    repos: "À votre écoute",
    permission: "Autorisation du microphone…",
    micro: `Enregistrement · ${secondes} / 90 s`,
    transcription: "Transcription sur votre poste…",
    reflexion: "L’assistante prépare sa réponse…",
    synthese: "Préparation de la voix locale…",
    lecture: "L’assistante vous parle…",
  };

  return (
    <>
      <Titre
        surligne="ASSISTANTE LOCALE"
        titre="Une voix à vos côtés."
        texte="Échangez naturellement, à l’écrit ou avec une voix française féminine. Vos données restent sur votre poste."
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
          <Trash2 size={16} /> Effacer le dialogue
        </button>
      </Titre>
      <div className="chat-layout">
        <section
          className="panel chat-panel"
          aria-label="Dialogue avec l’assistante"
        >
          <div
            className="chat-messages"
            ref={conversation}
            role="log"
            aria-label="Messages du dialogue"
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
                <h2>Parlons de votre prochaine étape.</h2>
                <p>
                  Un signal à comprendre, une procédure à retrouver, une
                  question sur votre plateforme. Je vous accompagne.
                </p>
                <div className="chat-suggestions">
                  {[
                    "Comment lancer une analyse ?",
                    "Comment fonctionnent les agents ?",
                    "Comment sauvegarder ma plateforme ?",
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
                  {message.role === "assistant" ? <Bot size={17} /> : "VOUS"}
                </div>
                <div className="message-body">
                  <strong>
                    {message.role === "assistant" ? "Votre assistante" : "Vous"}
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
                        aria-label="Écouter la réponse"
                      >
                        <Volume2 size={14} /> Écouter
                        {message.content.length > 2000 ? " un extrait" : ""}
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
              Votre message
            </label>
            <textarea
              ref={champ}
              id="message-assistante"
              value={brouillon}
              maxLength={4000}
              disabled={occupe}
              rows={3}
              placeholder="Écrivez votre message ou utilisez le microphone…"
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
                  aria-label={
                    phase === "micro"
                      ? "Arrêter l’enregistrement"
                      : "Dicter un message"
                  }
                >
                  {phase === "micro" ? <Square size={15} /> : <Mic size={16} />}{" "}
                  {phase === "micro" ? "Terminer" : "Dicter"}
                </button>
                {phase !== "repos" && phase !== "micro" && (
                  <button type="button" className="btn small" onClick={arreter}>
                    <Square size={14} /> Arrêter
                  </button>
                )}
              </div>
              <button
                type="submit"
                className="btn primary"
                disabled={occupe || !brouillon.trim()}
              >
                <Send size={16} /> Envoyer
              </button>
            </div>
            <div className="field-foot">
              <span>
                <CornerDownLeft size={12} /> Ctrl / ⌘ + Entrée pour envoyer
              </span>
              <span>{brouillon.length} / 4 000</span>
            </div>
          </form>
        </section>
        <aside className="voice-aside">
          <section className="panel instruction-card">
            <span className="tile-icon">
              <Headphones size={23} />
            </span>
            <h2>Une conversation privée.</h2>
            <p>
              La voix, la transcription et les réponses sont calculées
              localement.
            </p>
            <div className="voice-state">
              <span>Moteur vocal</span>
              <strong>
                {voix?.pret
                  ? "Disponible"
                  : erreurVoix || voix
                    ? "Indisponible"
                    : "Vérification…"}
              </strong>
            </div>
            <div className="voice-state">
              <span>Voix</span>
              <strong>Féminine · Français</strong>
            </div>
            <div className="voice-state">
              <span>Microphone</span>
              <strong>
                {phase === "micro"
                  ? "Enregistrement"
                  : microDisponible
                    ? "Au clic uniquement"
                    : "Non pris en charge"}
              </strong>
            </div>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={automatique}
                disabled={!voix?.pret}
                onChange={(event) => setAutomatique(event.target.checked)}
              />{" "}
              Lire les réponses automatiquement
            </label>
            {!voix?.pret && (erreurVoix || voix) && (
              <p className="hint">
                La voix est indisponible. Le dialogue écrit reste accessible ;
                vérifiez le moteur vocal dans le terminal.
              </p>
            )}
          </section>
          <section className="panel instruction-card">
            <span className="tile-icon">
              <ShieldCheck size={23} />
            </span>
            <h2>Vous gardez la main.</h2>
            <p>
              Relisez la transcription avant de l’envoyer. Une réponse vocale ne
              valide aucune action.
            </p>
            <p>
              Pour un diagnostic avec sources et approbation, ouvrez une analyse
              supervisée.
            </p>
            <Link className="text-button" to="/analyses/nouvelle">
              <Workflow size={15} /> Nouvelle analyse
            </Link>
          </section>
          <div className="voice-disclaimer">
            <LockKeyhole size={16} />
            <p>
              Dialogue éphémère : les sept derniers messages forment le
              contexte. Quitter cette page efface la conversation. Aucun
              enregistrement permanent.
            </p>
            <p>
              Voix SIWIS · Université d’Édimbourg · CC BY 4.0. Lecture limitée à
              2 000 caractères par réponse.
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}
