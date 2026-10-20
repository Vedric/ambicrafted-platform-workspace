import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import {
  Database,
  Download,
  FileText,
  Maximize2,
  Minus,
  Plus,
  Printer,
  Workflow,
} from "lucide-react";
import type { Artifact } from "./artifacts";
import { memoryDraft } from "./artifacts";
import { computeDiagram } from "./diagram-worker";
import type { DiagramLayout } from "./diagram-layout";
import { DiagramSvg, basisLabel, kindLabel } from "./DiagramSvg";
import { exportDiagram, exportStoredDocument } from "./artifact-export";
import { t, useI18n } from "./i18n";
import { Erreur, Modal } from "./ui";
import "./artifacts.css";

function Provenance({ artifact }: { artifact: Artifact }) {
  return (
    <details className="document-sources">
      <summary>{t("Legend and provenance")}</summary>
      <p>
        {t(
          "References identify the supplied context. They do not verify the generated claims.",
        )}
      </p>
      <ul>
        {artifact.sources.map((source) => (
          <li key={source.id}>
            <strong>{source.id}</strong> · {source.label}{" "}
            <span className="tag">
              {
                {
                  request: t("Current request"),
                  history: t("Conversation context"),
                  attachment: t("Attachment"),
                  generated: t("Generated context"),
                }[source.kind]
              }
            </span>
            {source.truncated && (
              <span className="tag">{t("Partial source")}</span>
            )}
            <code>SHA-256 {source.sha256}</code>
          </li>
        ))}
      </ul>
    </details>
  );
}
function Attribution({
  basis,
  source_ids,
}: {
  basis: "provided" | "proposed" | "unknown";
  source_ids: string[];
}) {
  return (
    <p className="document-attribution">
      <span className={`document-basis ${basis}`}>{basisLabel(basis)}</span>
      <span>{source_ids.join(", ") || t("No source reference")}</span>
    </p>
  );
}
function Outline({
  artifact,
}: {
  artifact: Extract<Artifact, { type: "diagram" }>;
}) {
  const node = (id: string) =>
    artifact.document.nodes.find((item) => item.id === id)!.label;
  return (
    <div className="document-outline">
      {artifact.document.groups.map((group) => (
        <p key={group.id}>
          <strong>{group.label}</strong> — {group.description}
        </p>
      ))}
      <ol>
        {artifact.document.nodes.map((item) => (
          <li key={item.id}>
            <strong>{item.label}</strong> <small>{kindLabel(item.kind)}</small>
            {item.description && <p>{item.description}</p>}
            <Attribution {...item} />
          </li>
        ))}
      </ol>
      <ol>
        {artifact.document.edges.map((item) => (
          <li key={item.id}>
            <strong>
              {node(item.source)} → {node(item.target)}
            </strong>
            <p>
              {item.label} · {kindLabel(item.kind)}
            </p>
            <Attribution {...item} />
          </li>
        ))}
      </ol>
    </div>
  );
}
function Report({
  artifact,
}: {
  artifact: Extract<Artifact, { type: "report" }>;
}) {
  return (
    <div className="document-report">
      {artifact.document.sections.map((section) => (
        <section key={section.id}>
          <h3>{section.heading}</h3>
          <Attribution {...section} />
          {section.paragraphs.map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
          {!!section.bullets.length && (
            <ul>
              {section.bullets.map((bullet, index) => (
                <li key={index}>{bullet}</li>
              ))}
            </ul>
          )}
          {section.table && (
            <div
              className="document-table"
              tabIndex={0}
              role="region"
              aria-label={section.heading}
            >
              <table>
                <thead>
                  <tr>
                    {section.table.columns.map((column, index) => (
                      <th key={index} scope="col">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {section.table.rows.map((row, index) => (
                    <tr key={index}>
                      {row.map((cell, column) => (
                        <td key={column}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
function PrintDocument({
  artifact,
  finish,
}: {
  artifact: Artifact;
  finish: () => void;
}) {
  useEffect(() => {
    document.body.dataset.printDocument = "true";
    // A text layout preserves all details across PDF pages, including large graphs.
    const timer = setTimeout(() => {
      try {
        window.print();
      } finally {
        finish();
      }
    }, 150);
    return () => {
      clearTimeout(timer);
      delete document.body.dataset.printDocument;
    };
  }, [finish]);
  return createPortal(
    <article className="document-print">
      <p>{t("Generated document · Review before use")}</p>
      <h1>{artifact.title}</h1>
      <p>{artifact.summary}</p>
      {artifact.type === "report" ? (
        <Report artifact={artifact} />
      ) : (
        <Outline artifact={artifact} />
      )}
      <h2>{t("Legend and provenance")}</h2>
      <p>
        {t(
          "References identify the supplied context. They do not verify the generated claims.",
        )}
      </p>
      <ul>
        {artifact.sources.map((source) => (
          <li key={source.id}>
            {source.id} · {source.label}
            {source.truncated ? ` · ${t("Partial source")}` : ""}
            <code>{source.sha256}</code>
          </li>
        ))}
      </ul>
    </article>,
    document.body,
  );
}

function DocumentView({
  artifact,
  layout,
  theme,
  failed,
  expanded,
  svgRef,
}: {
  artifact: Artifact;
  layout: DiagramLayout | null;
  theme: "dark" | "light";
  failed: boolean;
  expanded: boolean;
  svgRef: React.RefObject<SVGSVGElement | null>;
}) {
  const { language } = useI18n();
  const viewport = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 500 });
  useLayoutEffect(() => {
    if (svgRef.current)
      setDimensions({
        width: Number(svgRef.current.getAttribute("width")),
        height: Number(svgRef.current.getAttribute("height")),
      });
  }, [layout, artifact, language, svgRef]);
  const [zoom, setZoom] = useState(1);
  function fit() {
    if (viewport.current && svgRef.current)
      setZoom(
        Math.min(
          1,
          Math.max(
            0.1,
            (viewport.current.clientWidth - 24) /
              Number(svgRef.current.getAttribute("width")),
          ),
        ),
      );
  }
  if (artifact.type === "report") return <Report artifact={artifact} />;
  return (
    <>
      {layout && (
        <>
          <div className="document-zoom">
            <button
              type="button"
              className="icon-button"
              aria-label={t("Zoom out")}
              disabled={zoom <= 0.1}
              onClick={() => setZoom((value) => Math.max(0.1, value - 0.15))}
            >
              <Minus size={16} />
            </button>
            <output>{Math.round(zoom * 100)}%</output>
            <button
              type="button"
              className="icon-button"
              aria-label={t("Zoom in")}
              disabled={zoom >= 2}
              onClick={() => setZoom((value) => Math.min(2, value + 0.15))}
            >
              <Plus size={16} />
            </button>
            <button type="button" className="btn" onClick={() => setZoom(1)}>
              {t("Actual size")}
            </button>
            <button type="button" className="btn" onClick={fit}>
              {t("Fit diagram")}
            </button>
          </div>
          <div
            ref={viewport}
            className={`document-canvas ${expanded ? "expanded" : ""}`}
            role="region"
            aria-label={t("Diagram canvas")}
            tabIndex={0}
            style={{ height: `${Math.ceil(dimensions.height * zoom) + 4}px` }}
          >
            <div
              style={{
                width: `calc(${dimensions.width}px * ${zoom})`,
                height: `calc(${dimensions.height}px * ${zoom})`,
              }}
              className="document-canvas-space"
            >
              <div
                style={{ transform: `scale(${zoom})`, transformOrigin: "0 0" }}
              >
                <DiagramSvg
                  artifact={artifact}
                  layout={layout}
                  theme={theme}
                  svgRef={svgRef}
                />
              </div>
            </div>
          </div>
          <p className="hint">
            {t(
              "Use Actual size or zoom in to read small labels. Scroll in either direction to explore the diagram.",
            )}
          </p>
        </>
      )}
      {!layout && (
        <p role="status" className="document-layout-status">
          {failed
            ? t(
                "This diagram could not be laid out without overlaps. The complete outline and exports remain available.",
              )
            : t("Preparing the diagram layout…")}
        </p>
      )}
      <details open={failed} className="document-outline-toggle">
        <summary>{t("Complete text outline")}</summary>
        <Outline artifact={artifact} />
      </details>
    </>
  );
}

export default function ArtifactCard({
  artifact,
  conversation,
}: {
  artifact: Artifact;
  conversation: string;
}) {
  const { language } = useI18n();
  const navigate = useNavigate();
  const card = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(false);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!("IntersectionObserver" in window)) {
      setSeen(true);
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        setVisible(entry.isIntersecting);
        if (entry.isIntersecting) setSeen(true);
      },
      { rootMargin: "300px" },
    );
    if (card.current) observer.observe(card.current);
    return () => observer.disconnect();
  }, []);
  const [direction, setDirection] = useState<"LR" | "TB">(
    artifact.type === "diagram" ? artifact.document.direction : "TB",
  );
  const [expanded, setExpanded] = useState(false),
    [printing, setPrinting] = useState(false),
    [busy, setBusy] = useState(false);
  const [layout, setLayout] = useState<DiagramLayout | null>(null),
    [failed, setFailed] = useState(false),
    [error, setError] = useState<Error | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">(() =>
    document.documentElement.dataset.theme === "light" ? "light" : "dark",
  );
  const svg = useRef<SVGSVGElement>(null),
    expandedSvg = useRef<SVGSVGElement>(null);
  const finishPrinting = useCallback(() => setPrinting(false), []);
  useEffect(() => {
    const observer = new MutationObserver(() =>
      setTheme(
        document.documentElement.dataset.theme === "light" ? "light" : "dark",
      ),
    );
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (artifact.type !== "diagram" || !seen) return;
    const controller = new AbortController();
    setLayout(null);
    setFailed(false);
    void computeDiagram(
      { ...artifact.document, direction },
      controller.signal,
      {
        provided: basisLabel("provided"),
        proposed: basisLabel("proposed"),
        unknown: basisLabel("unknown"),
      },
    )
      .then((value) => {
        if (!controller.signal.aborted) setLayout(value);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [artifact, language, direction, seen]);
  async function image(format: "svg" | "png" | "json" | "markdown") {
    const element = expanded ? expandedSvg.current : svg.current;
    if ((format === "svg" || format === "png") && !element) return;
    setBusy(true);
    setError(null);
    try {
      if (format === "svg" || format === "png")
        await exportDiagram(element!, artifact, format);
      else await exportStoredDocument(conversation, artifact, format);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause
          : new Error(
              t("The document could not be exported. Please try again."),
            ),
      );
    } finally {
      setBusy(false);
    }
  }
  const toolbar = (
    <div className="document-actions">
      {artifact.type === "diagram" && (
        <label className="document-direction">
          {t("Layout direction")}
          <select
            value={direction}
            onChange={(event) =>
              setDirection(event.target.value as "LR" | "TB")
            }
          >
            <option value="LR">{t("Horizontal")}</option>
            <option value="TB">{t("Vertical")}</option>
          </select>
        </label>
      )}
      {artifact.type === "diagram" && (
        <>
          <button
            type="button"
            className="btn"
            disabled={!layout || busy}
            onClick={() => void image("svg")}
          >
            <Download size={15} />
            {t("Download SVG")}
          </button>
          <button
            type="button"
            className="btn"
            disabled={!layout || busy}
            onClick={() => void image("png")}
          >
            {t("Download PNG")}
          </button>
        </>
      )}
      <button
        type="button"
        className="btn"
        disabled={busy}
        onClick={() => void image("markdown")}
      >
        {t("Download Markdown")}
      </button>
      <button
        type="button"
        className="btn"
        disabled={busy}
        onClick={() => void image("json")}
      >
        {t("Download JSON")}
      </button>
      <button
        type="button"
        className="btn"
        onClick={() => {
          setExpanded(false);
          setPrinting(true);
        }}
      >
        <Printer size={15} />
        {t("Print / save PDF")}
      </button>
      <button
        type="button"
        className="btn"
        onClick={() =>
          navigate("/memoire", {
            state: { memoryDraft: memoryDraft(artifact, conversation) },
          })
        }
      >
        <Database size={15} />
        {t("Prepare a memory note")}
      </button>
    </div>
  );
  return (
    <section
      ref={card}
      className="artifact-card"
      data-artifact-id={artifact.id}
      data-document-visible={visible || expanded}
    >
      <header>
        <span className="document-icon" aria-hidden="true">
          {artifact.type === "diagram" ? (
            <Workflow size={23} />
          ) : (
            <FileText size={23} />
          )}
        </span>
        <div>
          <small>
            {t("Saved document")} ·{" "}
            {artifact.type === "diagram" ? t("Diagram") : t("Report")}
          </small>
          <h3>{artifact.title}</h3>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label={t("Open document")}
          onClick={() => setExpanded(true)}
        >
          <Maximize2 size={19} />
        </button>
      </header>
      <p className="document-summary">{artifact.summary}</p>
      <p className="document-status">
        {t("Generated document · Review before use")}
      </p>
      {error && !expanded && <Erreur erreur={error} />}
      <DocumentView
        artifact={artifact}
        layout={layout}
        theme={theme}
        failed={failed}
        expanded={false}
        svgRef={svg}
      />
      {toolbar}
      <Provenance artifact={artifact} />
      <p className="hint">
        {t("Local processing · Saved with this conversation")}
      </p>
      {expanded && (
        <Modal
          titre={t("Document workspace")}
          fermer={() => setExpanded(false)}
        >
          <div className="artifact-expanded">
            <h2>{artifact.title}</h2>
            <p>{artifact.summary}</p>
            <p className="document-status">
              {t("Generated document · Review before use")}
            </p>
            {error && <Erreur erreur={error} />}
            {toolbar}
            <DocumentView
              artifact={artifact}
              layout={layout}
              theme={theme}
              failed={failed}
              expanded
              svgRef={expandedSvg}
            />
            <Provenance artifact={artifact} />
          </div>
        </Modal>
      )}
      {printing && (
        <PrintDocument artifact={artifact} finish={finishPrinting} />
      )}
    </section>
  );
}
