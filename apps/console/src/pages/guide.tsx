import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  Check,
  Clipboard,
  Compass,
  GitBranch,
  Network,
  ShieldCheck,
  SquareTerminal,
} from "lucide-react";
import { t, useI18n, type MessageKey } from "../i18n";
import { Titre } from "../ui";
import { useAudioFocus } from "../audio-focus";
import {
  audioPreferences,
  playWithAudioOutput,
  useAudioOutput,
} from "../audio-devices";

export const TRAINING_EXAMPLE =
  "Training incident: the gateway returns HTTP 504 for 18% of requests since 14:30 UTC. The upstream responds in 120 ms when queried locally; the gateway times out at 5 seconds. A configuration change was applied at 14:20 UTC. No restart or configuration change is authorised. Find the relevant runbook, distinguish facts from hypotheses, quote the exact passages and list the evidence still needed." as const;
const lessons = [
  {
    id: "first-steps",
    title: "First steps",
    icon: Compass,
    steps: [
      [
        "Check your workspace",
        "Open Readiness and review each check. A green service check is not a production sign-off.",
        "/preparation",
      ],
      [
        "Prepare the facts",
        "Describe the symptoms, time window and known changes. Remove secrets. Keep client data in a dedicated private environment.",
        "/missions",
      ],
      [
        "Check the sources",
        "The SRE workflow reads runbooks through the local MCP gateway. Inspect quoted passages and missing information before accepting a proposal.",
        "/runbooks",
      ],
    ],
  },
  {
    id: "voice",
    title: "Talk with AURA",
    icon: AudioLines,
    steps: [
      [
        "Check your microphone",
        "Open Audio devices, detect and select your microphone and speakers, then test the signal and playback before starting a conversation.",
        "/assistant",
      ],
      [
        "Review, then send",
        "Record captures a draft: stop recording, review the transcription, then select Send. Start conversation sends successive turns automatically while enabled.",
        "/assistant",
      ],
      [
        "Keep control",
        "Stop or press Escape at any time. Changing page or hiding the tab closes capture and stops playback.",
        "/assistant",
      ],
    ],
  },
  {
    id: "investigation",
    title: "Investigate an incident",
    icon: GitBranch,
    steps: [
      [
        "Prepare the facts",
        "Describe the symptoms, time window and known changes. Remove secrets. Keep client data in a dedicated private environment.",
        "/analyses/nouvelle",
      ],
      [
        "Check the sources",
        "The SRE workflow reads runbooks through the local MCP gateway. Inspect quoted passages and missing information before accepting a proposal.",
        "/analyses",
      ],
      [
        "Make the decision",
        "Approval records your decision. It does not run remediation commands. Export only the evidence you have reviewed.",
        "/approbations",
      ],
    ],
  },
] as const satisfies readonly {
  id: string;
  title: MessageKey;
  icon: typeof Compass;
  steps: readonly (readonly [MessageKey, MessageKey, string])[];
}[];

export function UserGuide() {
  const { language } = useI18n();
  const [selected, setSelected] = useState(0);
  const [copy, setCopy] = useState<"idle" | "done" | "error">("idle");
  const lesson = lessons[selected];
  const [flow, setFlow] = useState(0);
  const flowSteps: {
    title: MessageKey;
    text: MessageKey;
    icon: typeof Compass;
  }[] = [
    { title: "Your request", text: "Prepare the facts", icon: Compass },
    {
      title: "Local MCP gateway",
      text: "One gateway for your tools",
      icon: Network,
    },
    { title: "Read-only tools", text: "Runbooks profile", icon: BookOpen },
    {
      title: "Source verification",
      text: "Check the sources",
      icon: GitBranch,
    },
    { title: "Your decision", text: "Make the decision", icon: ShieldCheck },
  ];
  return (
    <>
      <Titre
        surligne={t("LEARN BY DOING")}
        titre={t("Your first mission, step by step.")}
        texte={t(
          "Short walkthroughs, real interface recordings and reusable examples. Start small, inspect the evidence, then decide.",
        )}
      >
        <Link className="btn primary" to="/missions">
          <Compass size={17} />
          {t("Launch a mission")}
        </Link>
      </Titre>
      <nav className="guide-lessons" aria-label={t("User guide")}>
        {lessons.map((item, index) => (
          <button
            key={item.id}
            className={"guide-lesson " + (index === selected ? "active" : "")}
            aria-pressed={index === selected}
            onClick={() => setSelected(index)}
          >
            <item.icon size={21} />
            <span>{t(item.title)}</span>
            <span className="mono">0{index + 1}</span>
          </button>
        ))}
      </nav>
      <div className="guide-walkthrough" key={lesson.id}>
        <section className="panel guide-video">
          <div className="panel-heading">
            <h2>{t("Watch the walkthrough")}</h2>
            <span className="tag">{language === "fr" ? "FR" : "EN"}</span>
          </div>
          <NarratedWalkthrough
            key={lesson.id + language}
            lesson={lesson}
            language={language}
          />
          <p className="hint">
            {t("Narrated walkthrough · captions available")}
          </p>
          <p className="hint">
            {t(
              "A demonstration uses deterministic synthetic responses to explain the interface. It does not certify model accuracy.",
            )}
          </p>
        </section>
        <ol className="guide-steps">
          {lesson.steps.map(([title, text, path], index) => (
            <li className="guide-step" key={title}>
              <span className="guide-step-number">0{index + 1}</span>
              <div>
                <h2>{t(title)}</h2>
                <p>{t(text)}</p>
                <Link className="text-button" to={path}>
                  {t(title)} <ArrowRight size={15} />
                </Link>
              </div>
            </li>
          ))}
        </ol>
      </div>
      <section className="panel guide-example">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">ATLAS · SRE</span>
            <h2>{t("A working example")}</h2>
          </div>
          <GitBranch size={28} />
        </div>
        <p>
          {t(
            "Synthetic training example. No customer data or production changes.",
          )}
        </p>
        <blockquote>{t(TRAINING_EXAMPLE)}</blockquote>
        <div className="guide-example-actions">
          <button
            className="btn"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(t(TRAINING_EXAMPLE));
                setCopy("done");
              } catch {
                setCopy("error");
              }
            }}
          >
            {copy === "done" ? <Check size={16} /> : <Clipboard size={16} />}
            {copy === "done" ? t("Example copied") : t("Copy the example")}
          </button>
          <Link className="btn primary" to="/analyses/nouvelle">
            {t("Start a supervised analysis")}
            <ArrowRight size={16} />
          </Link>
        </div>
        {copy === "error" && (
          <p role="status">
            {t(
              "Copy was unavailable. Select the example text and copy it manually.",
            )}
          </p>
        )}
      </section>
      <section className="panel guide-flow">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">NEXUS · MCP</span>
            <h2>{t("Understand MCP")}</h2>
          </div>
          <Link className="text-button" to="/architecture">
            {t("Open full architecture")}
            <ArrowRight size={16} />
          </Link>
        </div>
        <p>
          {t(
            "The SRE agent receives only runbook tools. The operator profile can also inspect the control API. Tool access does not grant approval authority.",
          )}
        </p>
        <div
          className="guide-flow-path"
          role="group"
          aria-label={t("Understand MCP")}
        >
          {flowSteps.map((step, index) => (
            <button
              key={step.title}
              aria-pressed={flow === index}
              className={flow === index ? "active" : ""}
              onClick={() => setFlow(index)}
            >
              <step.icon size={23} />
              <strong>{t(step.title)}</strong>
              <span className="mono">0{index + 1}</span>
            </button>
          ))}
        </div>
        <p className="guide-flow-caption" aria-live="polite">
          {t(flowSteps[flow].text)}
        </p>
        <p className="hint">
          {t("A conceptual path, not a live traffic measurement.")}
        </p>
      </section>
      <div className="guide-bottom-grid">
        <section className="panel settings-panel">
          <h2>
            <SquareTerminal size={21} />
            {t("Use the CLI")}
          </h2>
          <p>
            {t(
              "The same local control API serves your terminal and the interface. Start with these read-only commands.",
            )}
          </p>
          <pre>
            <code>
              {
                "./plateforme --help\n./plateforme preparation\n./plateforme statut\n./plateforme analyses lister"
              }
            </code>
          </pre>
          <Link className="text-button" to="/parametres">
            {t("CLI reference")}
            <ArrowRight size={15} />
          </Link>
        </section>
        <section className="panel guide-faq">
          <h2>{t("Settings & help")}</h2>
          {(
            [
              [
                "Nothing happens when you speak?",
                "First start recording or a conversation. Confirm microphone permission, then select the right input. If the level stays flat, check your operating system privacy and microphone settings.",
              ],
              [
                "No sound?",
                "Check the selected output and browser tab mute setting. Some browsers require a click before playback or only support your system default output.",
              ],
              [
                "Why are animations still?",
                "Enable animations in the header, or choose Full animations in Settings → Appearance. Follow device settings respects reduced motion; hidden tabs and offscreen AURA always pause.",
              ],
            ] as const
          ).map(([question, answer]) => (
            <details key={question}>
              <summary>{t(question)}</summary>
              <p>{t(answer)}</p>
            </details>
          ))}
        </section>
      </div>
    </>
  );
}

function NarratedWalkthrough({
  lesson,
  language,
}: {
  lesson: (typeof lessons)[number];
  language: string;
}) {
  const player = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [outputError, setOutputError] = useState("");
  useAudioOutput(player, (cause) => setOutputError(cause.message));
  const src = `/guides/${lesson.id}-${language}.mp4`;
  useAudioFocus(playing ? "speech" : null);
  useEffect(() => {
    const video = player.current;
    // A cached/fast failure can precede React's listener attachment while a
    // lazy route is being committed. Reflect the native error after mounting.
    if (video?.error) setFailed(true);
    const pause = () => {
      if (document.hidden) video?.pause();
    };
    document.addEventListener("visibilitychange", pause);
    return () => {
      document.removeEventListener("visibilitychange", pause);
      if (video) {
        video.pause();
        video.removeAttribute("src");
        video.load();
      }
    };
  }, []);
  return (
    <>
      <video
        ref={player}
        src={src}
        controls
        playsInline
        preload="metadata"
        poster={`/guides/${lesson.id}-${language}.jpg`}
        aria-label={t(lesson.title)}
        onPlay={(event) => {
          const video = event.currentTarget;
          if ((video.sinkId || "") !== audioPreferences().outputId) {
            video.pause();
            void playWithAudioOutput(
              video,
              () => player.current === video && !document.hidden,
            ).catch((cause: Error) => setOutputError(cause.message));
          } else {
            setPlaying(true);
            setOutputError("");
          }
        }}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onError={() => {
          setFailed(true);
          setPlaying(false);
        }}
      >
        <track
          default
          kind="captions"
          src={`/guides/${lesson.id}-${language}.vtt`}
          srcLang={language}
          label={language === "fr" ? "Français" : "English"}
        />
      </video>
      {outputError && <p role="alert">{outputError}</p>}
      {failed && (
        <div role="alert">
          <p>
            {t("Video unavailable. Reload it or follow the steps alongside.")}
          </p>
          <button
            className="btn"
            onClick={() => {
              setFailed(false);
              player.current?.load();
            }}
          >
            {t("Reload video")}
          </button>{" "}
          <a
            className="text-button"
            href={src}
            target="_blank"
            rel="noreferrer"
          >
            {t("Open video")}
          </a>
        </div>
      )}
    </>
  );
}
