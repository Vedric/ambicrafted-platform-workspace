import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  Check,
  Clipboard,
  Compass,
  Database,
  ChartNoAxesCombined,
  HardDriveDownload,
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
import narration from "../../scripts/guide-script.json";
import chapterStarts from "../guide-chapters.json";
import "../guide.css";

const CAPTIONS_KEY = "ambicrafted-guide-captions";
let captionsPreference = true;
function readCaptions() {
  try {
    const value = localStorage.getItem(CAPTIONS_KEY);
    return value === null ? captionsPreference : value !== "off";
  } catch {
    return captionsPreference;
  }
}
function rememberCaptions(enabled: boolean) {
  captionsPreference = enabled;
  try {
    localStorage.setItem(CAPTIONS_KEY, enabled ? "on" : "off");
  } catch {
    /* Keep the current-session preference when storage is blocked. */
  }
}

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
        "AURA uses your system microphone and speakers. Check microphone & sound before starting a conversation; change devices in your operating system settings.",
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
  {
    id: "documents",
    title: "Documents and memory",
    icon: Database,
    steps: [
      [
        "Create a reviewable document",
        "Ask AURA for a diagram or report. Describe supplied facts and unknowns; choose a response format only when needed.",
        "/assistant",
      ],
      [
        "Inspect and export",
        "Check the complete outline, labels and sources. Download SVG or PNG for diagrams, Markdown or JSON for documents, and use print for a paginated PDF.",
        "/assistant",
      ],
      [
        "Save memory deliberately",
        "Prepare a note, review the generated summary, choose a scope and save explicitly. A generated note starts as a question, not an observation.",
        "/memoire",
      ],
    ],
  },
  {
    id: "recovery",
    title: "Backup and recovery",
    icon: HardDriveDownload,
    steps: [
      [
        "Protect the working set",
        "Create a private backup and inspect its final result. Include conversations, documents, missions, runbooks and the configured service data.",
        "/operations",
      ],
      [
        "Rehearse the restoration",
        "Test the backup in isolated temporary containers. Keep original data intact; a restore drill does not replace the live databases.",
        "/operations",
      ],
      [
        "Keep an off-host recovery path",
        "Configure encrypted export, copy it to a destination you control and test recovery with the separately stored identity. Local success does not verify a remote destination.",
        "/preparation",
      ],
    ],
  },
  {
    id: "observability",
    title: "Monitor your platform",
    icon: ChartNoAxesCombined,
    steps: [
      [
        "Check freshness first",
        "Read the collection time, service status and missing-data indicators before interpreting a chart. A quiet graph is not proof of good health.",
        "/observabilite",
      ],
      [
        "Compare the right signals",
        "Inspect queue pressure, latency, failures and backup age together. Check units and time ranges in Grafana before drawing conclusions.",
        "/sante",
      ],
      [
        "Connect metrics to evidence",
        "Use architecture to understand dependencies, then correlate actual timestamps and analysis results. Animated architecture flows explain the design; they are not live traffic.",
        "/architecture",
      ],
    ],
  },
] as const satisfies readonly {
  id: string;
  title: MessageKey;
  icon: typeof Compass;
  steps: readonly (readonly [MessageKey, MessageKey, string])[];
}[];

const chapterTitles = {
  "first-steps": [
    "Enter the workspace",
    "Read the readiness checks",
    "Choose a mission",
    "Inspect runbooks and CLI",
  ],
  voice: [
    "Check microphone and sound",
    "Record and review",
    "Send and stop",
    "Reopen conversation history",
  ],
  investigation: [
    "Describe the incident",
    "Review the proposal",
    "Record a human decision",
    "Inspect the analysis history",
  ],
  documents: [
    "Request a diagram",
    "Inspect and export",
    "Write a report",
    "Review a memory note",
  ],
  recovery: [
    "Identify protected data",
    "Review the backup confirmation",
    "Review the restore drill",
    "Prepare off-host recovery",
  ],
  observability: [
    "Read collection freshness",
    "Inspect service health",
    "Open monitoring dashboards",
    "Understand the architecture",
  ],
} as const satisfies Record<
  (typeof lessons)[number]["id"],
  readonly MessageKey[]
>;

export function UserGuide() {
  const { language } = useI18n();
  const [selected, setSelected] = useState(0);
  const [copy, setCopy] = useState<"idle" | "done" | "error">("idle");
  const lesson = lessons[selected];
  const example: MessageKey =
    lesson.id === "documents"
      ? "Create a diagram from this synthetic description: a browser sends HTTPS requests to an API; the API queries PostgreSQL. Keep these three components, label the direction of each interaction, and separate supplied context from proposed improvements."
      : lesson.id === "recovery"
        ? "Create a recovery review report for a synthetic local platform. Backup location, recovery identity custody and the last restore test date are unknown. List the evidence to collect without claiming that a backup or restore has succeeded."
        : lesson.id === "observability"
          ? "Create an observability review from these synthetic facts: the API responds, the latest metric sample is 12 minutes old, and no alert-delivery test is documented. Separate availability, collection freshness and alert delivery; do not infer missing evidence as a failed control."
          : TRAINING_EXAMPLE;
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
        titre={t("Practical workflows, from first request to recovery.")}
        texte={t(
          "Six narrated walkthroughs in English and French. Inspect the actual interface, practise with synthetic examples and keep control of every decision.",
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
            onClick={() => {
              setSelected(index);
              setCopy("idle");
            }}
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
            {t("Four chapters · narrated locally · 1080p")}{" "}
            {t("Use fullscreen to inspect small interface labels.")}
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
            <span className="eyebrow">{t(lesson.title)}</span>
            <h2>{t("Synthetic practice request")}</h2>
          </div>
          <GitBranch size={28} />
        </div>
        <p>
          {t(
            "Synthetic training example. No customer data or production changes.",
          )}
        </p>
        <blockquote>{t(example)}</blockquote>
        <div className="guide-example-actions">
          <button
            className="btn"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(t(example));
                setCopy("done");
              } catch {
                setCopy("error");
              }
            }}
          >
            {copy === "done" ? <Check size={16} /> : <Clipboard size={16} />}
            {copy === "done" ? t("Example copied") : t("Copy the example")}
          </button>
          <Link
            className="btn primary"
            to={selected < 3 ? "/analyses/nouvelle" : "/assistant"}
          >
            {t(
              selected < 3
                ? "Start a supervised analysis"
                : "Practice with AURA",
            )}
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
            <span className="eyebrow">MCP</span>
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
                "Check system input and output",
                "Allow microphone access, check the system input level and verify that the browser tab is not muted. Device selection belongs to your operating system.",
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
  const captionTrack = useRef<HTMLTrackElement>(null);
  const pendingSeek = useRef<number | null>(null);
  const starts = chapterStarts[lesson.id][language === "fr" ? "fr" : "en"];
  const playerId = useId();
  const [captions, setCaptions] = useState(readCaptions);
  const [captionError, setCaptionError] = useState(false);
  const captionChoice = useRef(captions);
  captionChoice.current = captions;
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [outputError, setOutputError] = useState("");
  useAudioOutput(player, (cause) => setOutputError(cause.message));
  const src = `/guides/${lesson.id}-${language}.mp4`;
  useAudioFocus(playing ? "speech" : null);
  const seekChapter = (start: number) => {
    const video = player.current;
    if (!video) return;
    if (video.readyState >= 1) {
      video.currentTime = start;
      return;
    }
    // Loading on demand also supports a chapter choice before the first play.
    const alreadyLoading = pendingSeek.current !== null;
    pendingSeek.current = start;
    if (!alreadyLoading) {
      video.preload = "auto";
      video.load();
    }
  };
  const synchronizeCaptions = () => {
    for (const track of player.current?.textTracks ?? []) {
      if (track.kind === "captions")
        track.mode = captionChoice.current ? "showing" : "disabled";
    }
  };
  useEffect(() => {
    const tracks = player.current?.textTracks;
    if (!tracks) return;
    synchronizeCaptions();
    const change = () => {
      const track = Array.from(tracks).find((item) => item.kind === "captions");
      if (!track) return;
      const enabled = track.mode === "showing";
      captionChoice.current = enabled;
      setCaptions(enabled);
      rememberCaptions(enabled);
    };
    tracks.addEventListener("change", change);
    return () => tracks.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    const track = captionTrack.current;
    if (!track) return;
    // Track errors do not bubble; observe the native element and cached state.
    const failed = () => setCaptionError(true);
    const loaded = () => {
      setCaptionError(false);
      synchronizeCaptions();
    };
    track.addEventListener("error", failed);
    track.addEventListener("load", loaded);
    if (track.readyState === 3) failed();
    else if (track.readyState === 2) loaded();
    return () => {
      track.removeEventListener("error", failed);
      track.removeEventListener("load", loaded);
    };
  }, []);
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
        id={playerId}
        ref={player}
        src={src}
        controls
        playsInline
        preload="none"
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
          pendingSeek.current = null;
          setFailed(true);
          setPlaying(false);
        }}
        onLoadedMetadata={() => {
          synchronizeCaptions();
          if (pendingSeek.current !== null && player.current) {
            player.current.currentTime = pendingSeek.current;
            pendingSeek.current = null;
          }
        }}
      >
        <track
          ref={captionTrack}
          default={captions}
          kind="captions"
          src={`/guides/${lesson.id}-${language}.vtt`}
          srcLang={language}
          label={language === "fr" ? "Français" : "English"}
        />
      </video>
      <nav className="guide-chapters" aria-label={t("Video chapters")}>
        {starts.map((start, index) => (
          <button
            type="button"
            className="btn"
            key={index}
            aria-controls={playerId}
            onClick={() => seekChapter(start)}
          >
            <span className="mono">
              {Math.floor(start / 60)}:
              {String(Math.floor(start % 60)).padStart(2, "0")}
            </span>
            <span>{t(chapterTitles[lesson.id][index])}</span>
          </button>
        ))}
      </nav>
      <div className="guide-media-controls">
        <button
          type="button"
          className="btn"
          aria-controls={playerId}
          aria-pressed={captions}
          onClick={() => {
            const enabled = !captions;
            captionChoice.current = enabled;
            setCaptions(enabled);
            rememberCaptions(enabled);
            synchronizeCaptions();
          }}
        >
          {t("Captions")}
        </button>
        <span className="hint">
          {t(
            "Captions can be switched off. Your choice is remembered for the next walkthrough.",
          )}
        </span>
      </div>
      {captionError && (
        <p role="status">
          {t("Captions are unavailable. The full transcript remains below.")}
        </p>
      )}
      <details className="guide-transcript">
        <summary>{t("Transcript")}</summary>
        <ol>
          {narration[lesson.id][language === "fr" ? "fr" : "en"].map(
            (paragraph, index) => (
              <li key={index}>
                <h3>{t(chapterTitles[lesson.id][index])}</h3>
                <p>{paragraph}</p>
              </li>
            ),
          )}
        </ol>
      </details>
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
