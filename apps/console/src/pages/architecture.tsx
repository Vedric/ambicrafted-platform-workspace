import { useContext, useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  Box,
  CircleHelp,
  Database,
  Fingerprint,
  GitBranch,
  LayoutDashboard,
  LockKeyhole,
  Network,
  Radar,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import { api, type Sante } from "../api";
import { number, useI18n } from "../i18n";
import { type architectureFr } from "../messages.architecture";
import {
  MotionPreference,
  useReducedMotionPreference,
} from "../motion-preferences";
import { Titre } from "../ui";

type Label = keyof typeof architectureFr;
type Kind = "request" | "knowledge" | "human";
type Component = {
  title: Label;
  caption: Label;
  role: Label;
  data: Label;
  boundary: Label;
  href: string;
  kind: Kind;
  icon: LucideIcon;
  service?: string;
};
const components = {
  operator: {
    title: "Operator",
    caption: "Browser · CLI · MCP",
    role: "Starts a supervised analysis or reads platform information through the authenticated control boundary.",
    data: "Alerts, bounded requests and explicit human decisions.",
    boundary:
      "The control MCP exposes read-only tools. It cannot approve a proposal or execute maintenance.",
    href: "/analyses/nouvelle",
    kind: "human",
    icon: Fingerprint,
  },
  control: {
    title: "Control API",
    caption: "Authenticated · local",
    role: "Validates requests, enforces access controls and schedules bounded work through one serial worker.",
    data: "Session metadata, analysis requests, maintenance requests and audit events.",
    boundary:
      "The browser uses a private local session. Remote multi-user exposure requires a separate security design.",
    href: "/agents",
    kind: "request",
    icon: LockKeyhole,
  },
  graph: {
    title: "Supervised agents",
    caption: "LangGraph · bounded work",
    role: "Extracts, triages and investigates an alert, checks evidence provenance, then pauses for human review.",
    data: "Alert context, model messages, retrieved passages and derived diagnostic proposals.",
    boundary:
      "Provenance checks establish which passage was read. They do not certify factual accuracy or authorize a fix.",
    href: "/analyses",
    kind: "request",
    icon: GitBranch,
  },
  review: {
    title: "Human review",
    caption: "Explicit decision",
    role: "Lets the operator inspect supporting evidence and approve or reject the proposed diagnosis.",
    data: "The proposal, its references and a recorded approval or rejection.",
    boundary:
      "Approving a proposal does not run remediation. AURA speech is never an approval channel.",
    href: "/approbations",
    kind: "human",
    icon: ShieldCheck,
  },
  state: {
    title: "Private state",
    caption: "SQLite · checkpoints",
    role: "Persists console history and supervised workflow checkpoints in protected local databases.",
    data: "Derived analysis messages, conversations, extracted documents, checkpoints, audit events and session metadata.",
    boundary:
      "Derived content can remain confidential. Separate client deployments and backup policies are still required.",
    href: "/operations",
    kind: "knowledge",
    icon: Database,
  },
  gateway: {
    title: "AI gateway",
    caption: "LiteLLM · restricted aliases",
    role: "Routes this workspace’s confidential requests through the local and local-embed model aliases.",
    data: "Model prompts, dialogue context and embedding inputs.",
    boundary:
      "The confidential route uses local inference without cloud fallback. Other gateway aliases are outside this journey.",
    href: "/sante",
    kind: "request",
    icon: Network,
    service: "litellm",
  },
  inference: {
    title: "Local inference",
    caption: "Ollama · local models",
    role: "Runs the configured local language and embedding models on this host.",
    data: "Prompts, generated text and numerical embeddings.",
    boundary:
      "Ollama runs separately from the gateway stack and dedicated graph-memory service.",
    href: "/sante",
    kind: "request",
    icon: Sparkles,
    service: "ollama",
  },
  runbooks: {
    title: "NEXUS · MCP gateway",
    caption: "Fixed profiles · scoped tools",
    role: "Routes allowlisted, namespaced tools over local stdio. ATLAS receives four runbook tools; the operator profile also exposes eleven read-only control tools.",
    data: "Search queries, file names, document hashes and retrieved passages.",
    boundary:
      "These tools read procedures; they do not execute the commands described inside them.",
    href: "/agents",
    kind: "knowledge",
    icon: Box,
  },
  corpus: {
    title: "Reviewed runbooks",
    caption: "Markdown · source of truth",
    role: "Stores procedures that an operator reviews before they become retrieval evidence.",
    data: "Local Markdown procedures and their content fingerprints.",
    boundary:
      "Platform backups include the active Markdown corpus. Mission files are included only from explicitly configured roots. Keep an encrypted off-host copy and test recovery.",
    href: "/runbooks",
    kind: "knowledge",
    icon: BookOpen,
  },
  browser: {
    title: "Voice workspace",
    caption: "AURA · browser audio",
    role: "Records with permission, presents editable transcripts and plays the generated WAV through native browser audio.",
    data: "Microphone audio, reviewed text and locally saved conversation messages.",
    boundary:
      "Hands-free mode is opt-in. Transcription can change words or numbers; review consequential facts.",
    href: "/assistant",
    kind: "human",
    icon: AudioLines,
  },
  speech: {
    title: "Local speech",
    caption: "Whisper · ONNX speech · CPU",
    role: "Transcribes English or French audio and synthesizes the selected female voice locally.",
    data: "Bounded audio uploads, transient private audio files and generated WAV output.",
    boundary:
      "Speech availability has its own checks. The six service probes below do not measure transcription accuracy or voice readiness.",
    href: "/assistant",
    kind: "request",
    icon: AudioLines,
  },
  dialogue: {
    title: "AURA dialogue",
    caption: "Saved context · no tools",
    role: "Builds a bounded conversational reply through the restricted local model route.",
    data: "The current message and a limited recent conversation context.",
    boundary:
      "Dialogue has no tool access or approval authority. Use a supervised analysis for an evidence-backed diagnosis.",
    href: "/assistant",
    kind: "request",
    icon: Sparkles,
  },
  memory: {
    title: "Graph memory",
    caption: "Neo4j · explicit scopes",
    role: "Stores sourced operator notes and same-scope relationships in a dedicated local database.",
    data: "Observations, decisions, questions, preferences and their source references.",
    boundary:
      "Scope filters are not tenant permissions. Notes are unverified context; only selected copies enter a conversation.",
    href: "/memoire",
    kind: "knowledge",
    icon: GitBranch,
  },
  indexer: {
    title: "Runbook indexer",
    caption: "Chunks · versioned publication",
    role: "Splits reviewed procedures into sections, computes local embeddings and publishes a new vector collection.",
    data: "Document sections, source fingerprints and numerical embeddings.",
    boundary:
      "Indexing is an explicit maintenance operation. Previous collections are retained for rollback.",
    href: "/operations",
    kind: "knowledge",
    icon: Waypoints,
  },
  vectors: {
    title: "Vector memory",
    caption: "Qdrant · runbooks-current",
    role: "Serves the published runbook collection through a versioned alias for semantic retrieval.",
    data: "Embeddings, indexed passages and source metadata.",
    boundary:
      "A corpus fingerprint detects a stale index. Literal search remains available when vector search is unavailable.",
    href: "/recherche",
    kind: "knowledge",
    icon: Database,
    service: "qdrant",
  },
  postgres: {
    title: "Gateway database",
    caption: "PostgreSQL · gateway state",
    role: "Persists the gateway’s configuration and accounting state.",
    data: "Gateway configuration, virtual-key records and usage records.",
    boundary:
      "PostgreSQL has no independent probe in this six-endpoint view. Gateway availability does not prove database readiness.",
    href: "/operations",
    kind: "knowledge",
    icon: Database,
  },
  metrics: {
    title: "Metrics",
    caption: "Prometheus · scrape targets",
    role: "Collects configured metrics from the platform exporter, Prometheus itself, Tempo, Qdrant and Grafana.",
    data: "Service counters, timings and resource metrics exposed by the configured targets.",
    boundary:
      "Local alert rules have no external notification destination configured.",
    href: "/observabilite",
    kind: "request",
    icon: Radar,
    service: "prometheus",
  },
  traces: {
    title: "Traces",
    caption: "Tempo · correlated spans",
    role: "Stores correlated spans for supervised tasks, model requests and tool calls.",
    data: "Trace identifiers, operation names, timing and bounded diagnostic attributes.",
    boundary:
      "Instrumentation deliberately avoids raw tool arguments. Trace presence does not certify complete coverage.",
    href: "/observabilite",
    kind: "request",
    icon: GitBranch,
    service: "tempo",
  },
  dashboards: {
    title: "Dashboards",
    caption: "Grafana · local exploration",
    role: "Queries Prometheus and Tempo to present local metrics and traces.",
    data: "Dashboard configuration, metric results and trace results.",
    boundary:
      "A healthy dashboard is not evidence that a client mission is ready. Check the dedicated readiness report.",
    href: "/observabilite",
    kind: "request",
    icon: LayoutDashboard,
    service: "grafana",
  },
} as const satisfies Record<string, Component>;

type ComponentId = keyof typeof components;
type Position = { id: ComponentId; x: number; y: number };
type Connection = {
  from: ComponentId;
  to: ComponentId;
  label: Label;
  kind: Kind;
};
type Journey = {
  label: Label;
  title: Label;
  description: Label;
  icon: LucideIcon;
  nodes: Position[];
  connections: Connection[];
};
const journeys: Record<string, Journey> = {
  investigation: {
    label: "Investigation",
    title: "From an alert to a reviewed proposal",
    description:
      "A bounded agent workflow retrieves evidence and pauses for a human decision. It does not execute remediation.",
    icon: GitBranch,
    nodes: [
      { id: "operator", x: 150, y: 85 },
      { id: "control", x: 500, y: 85 },
      { id: "graph", x: 500, y: 250 },
      { id: "runbooks", x: 150, y: 415 },
      { id: "corpus", x: 150, y: 580 },
      { id: "gateway", x: 850, y: 250 },
      { id: "inference", x: 850, y: 415 },
      { id: "state", x: 850, y: 580 },
      { id: "review", x: 500, y: 580 },
    ],
    connections: [
      {
        from: "operator",
        to: "control",
        label: "Submit a validated request",
        kind: "request",
      },
      {
        from: "control",
        to: "graph",
        label: "Schedule the supervised workflow",
        kind: "request",
      },
      {
        from: "graph",
        to: "runbooks",
        label: "Retrieve read-only evidence",
        kind: "knowledge",
      },
      {
        from: "runbooks",
        to: "corpus",
        label: "Read source procedures",
        kind: "knowledge",
      },
      {
        from: "graph",
        to: "gateway",
        label: "Request local model reasoning",
        kind: "request",
      },
      {
        from: "gateway",
        to: "inference",
        label: "Run local inference",
        kind: "request",
      },
      {
        from: "graph",
        to: "state",
        label: "Persist checkpoints",
        kind: "knowledge",
      },
      {
        from: "graph",
        to: "review",
        label: "Pause for an explicit decision",
        kind: "human",
      },
    ],
  },
  voice: {
    label: "Voice",
    title: "From your voice to a local reply",
    description:
      "Speech recognition, dialogue and speech synthesis run in successive local steps. Transcript review is the default.",
    icon: AudioLines,
    nodes: [
      { id: "browser", x: 150, y: 140 },
      { id: "control", x: 500, y: 140 },
      { id: "speech", x: 850, y: 140 },
      { id: "dialogue", x: 500, y: 360 },
      { id: "gateway", x: 500, y: 560 },
      { id: "inference", x: 850, y: 560 },
    ],
    connections: [
      {
        from: "browser",
        to: "control",
        label: "Upload audio or reviewed text",
        kind: "human",
      },
      {
        from: "control",
        to: "speech",
        label: "Transcribe audio; synthesize the reply",
        kind: "request",
      },
      {
        from: "control",
        to: "dialogue",
        label: "Create a bounded dialogue request",
        kind: "request",
      },
      {
        from: "dialogue",
        to: "gateway",
        label: "Route the conversation locally",
        kind: "request",
      },
      {
        from: "gateway",
        to: "inference",
        label: "Run local inference",
        kind: "request",
      },
      {
        from: "control",
        to: "browser",
        label: "Return WAV audio for browser playback",
        kind: "request",
      },
    ],
  },
  knowledge: {
    label: "Knowledge",
    title: "From reviewed procedures to grounded retrieval",
    description:
      "Human-reviewed Markdown remains the source. Vector search helps retrieve it; similarity is not a confidence score.",
    icon: BookOpen,
    nodes: [
      { id: "corpus", x: 150, y: 110 },
      { id: "indexer", x: 500, y: 110 },
      { id: "gateway", x: 850, y: 110 },
      { id: "inference", x: 850, y: 350 },
      { id: "vectors", x: 500, y: 350 },
      { id: "runbooks", x: 150, y: 560 },
    ],
    connections: [
      {
        from: "indexer",
        to: "corpus",
        label: "Read reviewed Markdown",
        kind: "knowledge",
      },
      {
        from: "indexer",
        to: "gateway",
        label: "Request local embeddings",
        kind: "request",
      },
      {
        from: "gateway",
        to: "inference",
        label: "Run local inference",
        kind: "request",
      },
      {
        from: "indexer",
        to: "vectors",
        label: "Publish a versioned collection",
        kind: "knowledge",
      },
      {
        from: "runbooks",
        to: "vectors",
        label: "Search the active vector alias",
        kind: "knowledge",
      },
      {
        from: "runbooks",
        to: "corpus",
        label: "Read exact source passages",
        kind: "knowledge",
      },
    ],
  },
  memory: {
    label: "Memory",
    title: "From explicit notes to conversational context",
    description:
      "Choose a sourced note within its scope. The API copies it into a conversation; related notes and other threads are never silently included.",
    icon: GitBranch,
    nodes: [
      { id: "operator", x: 150, y: 110 },
      { id: "control", x: 500, y: 110 },
      { id: "memory", x: 850, y: 110 },
      { id: "runbooks", x: 150, y: 350 },
      { id: "state", x: 500, y: 350 },
      { id: "dialogue", x: 850, y: 350 },
      { id: "gateway", x: 850, y: 560 },
    ],
    connections: [
      {
        from: "operator",
        to: "control",
        label: "Select a scope and a sourced note",
        kind: "human",
      },
      {
        from: "control",
        to: "memory",
        label: "Read or write explicit operator notes",
        kind: "knowledge",
      },
      {
        from: "runbooks",
        to: "control",
        label: "Two read-only scoped memory tools",
        kind: "knowledge",
      },
      {
        from: "control",
        to: "state",
        label: "Copy selected context with provenance",
        kind: "knowledge",
      },
      {
        from: "state",
        to: "dialogue",
        label: "Include only selected bounded context",
        kind: "knowledge",
      },
      {
        from: "dialogue",
        to: "gateway",
        label: "Route the conversation locally",
        kind: "request",
      },
    ],
  },
  telemetry: {
    label: "Telemetry",
    title: "From local signals to operational visibility",
    description:
      "Metrics and traces have separate collection paths. Dashboards help inspect them without proving that every workflow is correct.",
    icon: Radar,
    nodes: [
      { id: "graph", x: 150, y: 85 },
      { id: "gateway", x: 500, y: 85 },
      { id: "postgres", x: 850, y: 85 },
      { id: "traces", x: 150, y: 305 },
      { id: "vectors", x: 850, y: 305 },
      { id: "metrics", x: 850, y: 560 },
      { id: "dashboards", x: 150, y: 560 },
    ],
    connections: [
      {
        from: "gateway",
        to: "postgres",
        label: "Record gateway state",
        kind: "knowledge",
      },
      {
        from: "graph",
        to: "traces",
        label: "Emit correlated task spans",
        kind: "request",
      },
      {
        from: "gateway",
        to: "traces",
        label: "Emit model-request spans",
        kind: "request",
      },
      {
        from: "metrics",
        to: "vectors",
        label: "Scrape Qdrant metrics",
        kind: "request",
      },
      {
        from: "metrics",
        to: "traces",
        label: "Scrape Tempo metrics",
        kind: "request",
      },
      {
        from: "metrics",
        to: "dashboards",
        label: "Scrape Grafana metrics",
        kind: "request",
      },
      {
        from: "dashboards",
        to: "metrics",
        label: "Query collected metrics",
        kind: "request",
      },
      {
        from: "dashboards",
        to: "traces",
        label: "Query collected traces",
        kind: "request",
      },
    ],
  },
};
const measured = [
  "gateway",
  "inference",
  "vectors",
  "metrics",
  "traces",
  "dashboards",
] as const;
const kinds: { id: Kind; label: Label }[] = [
  { id: "request", label: "Request & inference" },
  { id: "knowledge", label: "Knowledge & storage" },
  { id: "human", label: "Human control" },
];

function connector(from: Position, to: Position, reverse: boolean): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.abs(dx) > Math.abs(dy)) {
    const direction = Math.sign(dx);
    const start = from.x + 133 * direction;
    const end = to.x - 133 * direction;
    const offset = reverse ? 19 : -5;
    const bend = Math.max(45, Math.abs(end - start) / 2);
    return `M ${start} ${from.y + offset} C ${start + bend * direction} ${from.y + offset}, ${end - bend * direction} ${to.y + offset}, ${end} ${to.y + offset}`;
  }
  const direction = Math.sign(dy);
  const start = from.y + 58 * direction;
  const end = to.y - 58 * direction;
  const bend = Math.max(40, Math.abs(end - start) / 2);
  const offset = reverse ? 19 : -5;
  return `M ${from.x + offset} ${start} C ${from.x + offset} ${start + bend * direction}, ${to.x + offset} ${end - bend * direction}, ${to.x + offset} ${end}`;
}

export function Architecture() {
  const { t, locale } = useI18n();
  const [journeyId, setJourneyId] = useState("investigation");
  const [selected, setSelected] = useState<ComponentId>("graph");
  const [foreground, setForeground] = useState(
    () => typeof document !== "undefined" && !document.hidden,
  );
  const [inView, setInView] = useState(false);
  const canvas = useRef<HTMLDivElement>(null);
  const preference = useContext(MotionPreference);
  const reduced = useReducedMotionPreference();
  const unique = useId().replace(/:/g, "");
  const journey = journeys[journeyId];
  const selectedComponent: Component = components[selected];
  const SelectedIcon = selectedComponent.icon;
  const health = useQuery({
    queryKey: ["sante"],
    queryFn: ({ signal }) => api<Sante>("/sante", "GET", undefined, signal),
    refetchInterval: foreground ? 15000 : false,
    refetchIntervalInBackground: false,
  });
  useEffect(() => {
    const update = () => setForeground(!document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  useEffect(() => {
    const element = canvas.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry?.isIntersecting ?? false),
      { threshold: 0.05 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  function probe(id?: string) {
    const service =
      !health.isError && Array.isArray(health.data?.services)
        ? health.data.services.find((entry) => entry && entry.id === id)
        : undefined;
    const known = id && typeof service?.ok === "boolean";
    return {
      state: known ? (service.ok ? "up" : "down") : "unknown",
      label: t(
        known
          ? service.ok
            ? "Health check passed"
            : "Health check failed"
          : "Not measured",
      ),
      latency:
        known &&
        service.ok &&
        Number.isFinite(service.latence_ms) &&
        service.latence_ms >= 0
          ? service.latence_ms
          : undefined,
    };
  }
  function selectJourney(id: string) {
    setJourneyId(id);
    setSelected(journeys[id].nodes[0].id);
  }
  function componentButton(position: Position, mobile = false) {
    const component: Component = components[position.id];
    const Icon = component.icon;
    return (
      <button
        key={position.id}
        type="button"
        className={`architecture-node kind-${component.kind}${selected === position.id ? " is-selected" : ""}`}
        style={
          mobile
            ? undefined
            : { left: `${position.x / 10}%`, top: `${position.y / 6.6}%` }
        }
        aria-pressed={selected === position.id}
        aria-controls={`${unique}-details`}
        onClick={() => setSelected(position.id)}
      >
        <span className="architecture-node-icon">
          <Icon size={20} aria-hidden="true" />
        </span>
        <span>
          <strong>{t(component.title)}</strong>
          <small>{t(component.caption)}</small>
        </span>
      </button>
    );
  }
  const selectedProbe = probe(selectedComponent.service);

  return (
    <div className="architecture-page">
      <Titre
        surligne={t("THE SYSTEM, EXPLAINED")}
        titre={t("See how your intelligence connects.")}
        texte={t(
          "Explore the components, follow a request and understand where your data goes.",
        )}
      >
        <Link className="btn" to="/preparation">
          <ShieldCheck size={18} aria-hidden="true" />
          {t("Readiness checks")}
        </Link>
      </Titre>

      <div
        className="architecture-journeys"
        role="group"
        aria-label={t("Architecture journeys")}
      >
        {Object.entries(journeys).map(([id, item]) => {
          const Icon = item.icon;
          return (
            <button
              type="button"
              key={id}
              aria-pressed={id === journeyId}
              onClick={() => selectJourney(id)}
            >
              <Icon size={20} aria-hidden="true" />
              {t(item.label)}
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          );
        })}
      </div>

      <section
        className="architecture-journey"
        aria-labelledby={`${unique}-journey`}
      >
        <header className="architecture-journey-header">
          <div>
            <div className="eyebrow">{t("Conceptual flow")}</div>
            <h2 id={`${unique}-journey`}>{t(journey.title)}</h2>
            <p>{t(journey.description)}</p>
          </div>
          <span className="architecture-guide-icon" aria-hidden="true">
            <Waypoints size={34} />
          </span>
        </header>
        <p className="architecture-disclaimer">
          <CircleHelp size={18} aria-hidden="true" />
          {t(
            "Arrows explain dependencies, not live traffic. Animation never indicates an active task.",
          )}
        </p>
        <div className="architecture-layout">
          <div className="architecture-canvas-wrap">
            <div
              className="architecture-legend"
              aria-label={t("Component map")}
            >
              {kinds.map((kind) => (
                <span key={kind.id} className={`kind-${kind.id}`}>
                  <i aria-hidden="true" />
                  {t(kind.label)}
                </span>
              ))}
            </div>
            <p className="architecture-instruction">
              {t("Select a component to inspect its role and data.")}
            </p>
            <div
              ref={canvas}
              className="architecture-canvas"
              data-motion={
                preference && !reduced && foreground && inView ? "on" : "off"
              }
              role="group"
              aria-label={t("Component map")}
            >
              <svg
                className="architecture-connectors"
                viewBox="0 0 1000 660"
                aria-hidden="true"
                focusable="false"
              >
                <defs>
                  {kinds.map((kind) => (
                    <marker
                      key={kind.id}
                      id={`${unique}-${kind.id}`}
                      className={`kind-${kind.id}`}
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
                    </marker>
                  ))}
                </defs>
                {journey.connections.map((connection, index) => {
                  const from = journey.nodes.find(
                    (node) => node.id === connection.from,
                  )!;
                  const to = journey.nodes.find(
                    (node) => node.id === connection.to,
                  )!;
                  const reverse = journey.connections
                    .slice(0, index)
                    .some(
                      (other) =>
                        other.from === connection.to &&
                        other.to === connection.from,
                    );
                  return (
                    <g
                      key={`${journeyId}-${index}`}
                      className={`architecture-connection kind-${connection.kind}${connection.from === selected || connection.to === selected ? " is-related" : ""}`}
                    >
                      <path
                        className="architecture-wire"
                        d={connector(from, to, reverse)}
                        markerEnd={`url(#${unique}-${connection.kind})`}
                      />
                      <path
                        className="architecture-flow"
                        d={connector(from, to, reverse)}
                      />
                    </g>
                  );
                })}
              </svg>
              {journey.nodes.map((position) => componentButton(position))}
            </div>
            <div
              className="architecture-mobile-list"
              role="group"
              aria-label={t("Component list")}
            >
              {journey.nodes.map((position) => componentButton(position, true))}
            </div>
          </div>

          <aside
            className={`architecture-details kind-${selectedComponent.kind}`}
            id={`${unique}-details`}
            aria-label={t("Component details")}
          >
            <div className="architecture-detail-title">
              <span className="architecture-node-icon">
                <SelectedIcon size={25} aria-hidden="true" />
              </span>
              <div>
                <h3 aria-live="polite" aria-atomic="true">
                  {t(selectedComponent.title)}
                </h3>
                <p>{t(selectedComponent.caption)}</p>
              </div>
            </div>
            <span
              className={`architecture-probe probe-${selectedComponent.service ? selectedProbe.state : "unknown"}`}
            >
              <i aria-hidden="true" />
              {selectedComponent.service
                ? selectedProbe.label
                : t("No direct health probe")}
            </span>
            <dl>
              <dt>{t("Role in this system")}</dt>
              <dd>{t(selectedComponent.role)}</dd>
              <dt>{t("Data handled")}</dt>
              <dd>{t(selectedComponent.data)}</dd>
              <dt>{t("Boundary to remember")}</dt>
              <dd>{t(selectedComponent.boundary)}</dd>
            </dl>
            <Link
              className="btn"
              to={selectedComponent.href}
              aria-label={`${t("Open related workspace")}: ${t(selectedComponent.title)}`}
            >
              {t("Open related workspace")}
              <ArrowRight size={17} aria-hidden="true" />
            </Link>
          </aside>
        </div>

        <div className="architecture-connections-guide">
          <h3>{t("Connection guide")}</h3>
          <ul>
            {journey.connections.map((connection, index) => (
              <li
                key={`${journeyId}-${index}`}
                className={`kind-${connection.kind}`}
              >
                <span
                  className="architecture-connection-number"
                  aria-hidden="true"
                >
                  {number(index + 1)}
                </span>
                <div>
                  <strong>
                    {t(components[connection.from].title)}
                    <ArrowRight size={14} aria-hidden="true" />
                    {t(components[connection.to].title)}
                  </strong>
                  <p>{t(connection.label)}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section
        className="architecture-health"
        aria-labelledby={`${unique}-health`}
      >
        <header>
          <div>
            <div className="eyebrow">{t("Measured by the health API")}</div>
            <h2 id={`${unique}-health`}>{t("Measured availability")}</h2>
            <p>
              {t(
                "Six endpoint checks from the local health API. A successful response is an availability signal, not a complete readiness or security assessment.",
              )}
            </p>
          </div>
          <button
            className="btn"
            type="button"
            onClick={() => void health.refetch()}
            disabled={health.isFetching}
          >
            <RefreshCw size={17} aria-hidden="true" />
            {t(health.isFetching ? "Checking services…" : "Check services")}
          </button>
        </header>
        {health.isError && (
          <p className="architecture-health-error" role="status">
            {t(
              "Service checks are unavailable. The architecture guide remains available; current availability is unknown.",
            )}
          </p>
        )}
        <ul className="architecture-health-grid">
          {measured.map((id) => {
            const component = components[id];
            const status = probe(component.service);
            return (
              <li key={id}>
                <strong>{t(component.title)}</strong>
                <span className={`architecture-probe probe-${status.state}`}>
                  <i aria-hidden="true" />
                  {status.label}
                </span>
                {status.latency !== undefined && (
                  <small>
                    {t("Probe duration")}:{" "}
                    {number(status.latency, { maximumFractionDigits: 0 })} ms
                  </small>
                )}
              </li>
            );
          })}
        </ul>
        <div className="architecture-health-footer">
          <p>
            {health.dataUpdatedAt ? (
              <>
                {t("Last successful check")}{" "}
                <time dateTime={new Date(health.dataUpdatedAt).toISOString()}>
                  {new Intl.DateTimeFormat(locale, {
                    dateStyle: "medium",
                    timeStyle: "medium",
                  }).format(health.dataUpdatedAt)}
                </time>
              </>
            ) : (
              t("No successful check yet")
            )}
          </p>
          <Link to="/sante">
            {t("Open system health")}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <div className="architecture-boundary">
        <ShieldCheck size={25} aria-hidden="true" />
        <div>
          <h3>{t("Local trust boundary")}</h3>
          <p>
            {t(
              "One trusted operator per deployment. Use a separate VM or deployment for each client; this workspace has no tenant isolation.",
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
