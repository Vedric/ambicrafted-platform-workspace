import { useId, useMemo } from "react";
import type { Artifact, Basis, NodeKind, EdgeKind } from "./artifacts";
import {
  sourceMarkers,
  wrapText,
  type DiagramLayout,
  type TextLine,
  type MeasureText,
} from "./diagram-layout";
import { t, useI18n } from "./i18n";

type DiagramArtifact = Extract<Artifact, { type: "diagram" }>;
export const kindLabel = (kind: NodeKind | EdgeKind): string =>
  ({
    service: t("Service"),
    data: t("Data store"),
    actor: t("Actor"),
    external: t("External system"),
    control: t("Control point"),
    flow: t("Flow"),
    dependency: t("Dependency"),
    trust: t("Trust boundary"),
  })[kind];
export const basisLabel = (basis: Basis): string =>
  ({
    provided: t("Supplied context"),
    proposed: t("Proposed"),
    unknown: t("Unconfirmed"),
  })[basis];
const palettes = {
  dark: {
    background: "#091522",
    card: "#13263a",
    group: "#0e2030",
    ink: "#edf5ff",
    muted: "#b3c5d8",
    border: "#526c86",
    service: "#72dded",
    data: "#b8a4ff",
    actor: "#8dd9b3",
    external: "#f4c887",
    control: "#ffaaa5",
    flow: "#72dded",
    dependency: "#b8a4ff",
    trust: "#f4c887",
  },
  light: {
    background: "#f8fafc",
    card: "#ffffff",
    group: "#edf3f8",
    ink: "#152a42",
    muted: "#455c73",
    border: "#6e8296",
    service: "#09677b",
    data: "#6545a6",
    actor: "#216f50",
    external: "#8d560b",
    control: "#a43545",
    flow: "#09677b",
    dependency: "#6545a6",
    trust: "#8d560b",
  },
};

function Lines({
  lines,
  x,
  y,
  size,
  color,
  bold = false,
  step,
}: {
  lines: TextLine[];
  x: number;
  y: number;
  size: number;
  color: string;
  bold?: boolean;
  step: number;
}) {
  return (
    <>
      {lines.map((line, index) => (
        <text
          key={index}
          x={x}
          y={y + index * step}
          fill={color}
          fontSize={size}
          fontWeight={bold ? 600 : 400}
          textLength={line.width || undefined}
          lengthAdjust="spacingAndGlyphs"
        >
          {line.text}
        </text>
      ))}
    </>
  );
}

export function DiagramSvg({
  artifact,
  layout,
  theme,
  svgRef,
}: {
  artifact: DiagramArtifact;
  layout: DiagramLayout;
  theme: "dark" | "light";
  svgRef?: React.Ref<SVGSVGElement>;
}) {
  const { language } = useI18n();
  const unique = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const p = palettes[theme];
  const frame = useMemo(() => {
    const canvas = document.createElement("canvas"),
      context = canvas.getContext("2d");
    const measure: MeasureText = (text, size, bold) => {
      if (!context) return [...text].length * size * 0.6;
      context.font = `${bold ? 600 : 400} ${size}px "Manrope Variable", sans-serif`;
      return context.measureText(text).width;
    };
    const width = Math.max(600, layout.width);
    const title = wrapText(
      artifact.title,
      Math.min(900, width - 72),
      26,
      true,
      measure,
    );
    const summary = wrapText(
      artifact.summary,
      Math.min(900, width - 72),
      16,
      false,
      measure,
    );
    const top = 92 + title.length * 34 + summary.length * 24;
    const kinds = [
      ...new Set([
        ...artifact.document.nodes.map((node) => node.kind),
        ...artifact.document.edges.map((edge) => edge.kind),
      ]),
    ];
    const entries = kinds.map((kind) => ({
      kind,
      text:
        kindLabel(kind) +
        (artifact.document.legend.find((entry) => entry.kind === kind)
          ? ` · ${artifact.document.legend.find((entry) => entry.kind === kind)!.label}`
          : ""),
    }));
    const columns = Math.max(1, Math.min(4, Math.floor((width - 72) / 310))),
      columnWidth = (width - 72) / columns;
    let bottom = top + layout.height + 70;
    const legend = entries.map((entry) => ({
      ...entry,
      lines: wrapText(entry.text, columnWidth - 48, 14, false, measure),
      x: 0,
      y: 0,
    }));
    for (let index = 0; index < legend.length; index += columns) {
      const row = legend.slice(index, index + columns);
      row.forEach((item, column) => {
        item.x = 36 + column * columnWidth;
        item.y = bottom;
      });
      bottom += Math.max(...row.map((item) => item.lines.length * 20)) + 22;
    }
    const statusLines = wrapText(
      `${t("Node borders")}: ${t("Solid")} — ${basisLabel("provided")} · ${t("Dashed")} — ${basisLabel("proposed")} · ${t("Dotted")} — ${basisLabel("unknown")}`,
      Math.min(900, width - 72),
      14,
      false,
      measure,
    );
    const statusY = bottom + 12;
    bottom = statusY + statusLines.length * 20 + 12;
    const refs = sourceMarkers(artifact.document);
    const note = wrapText(
      t(
        "References identify the supplied context. They do not verify the generated claims.",
      ),
      Math.min(900, width - 72),
      14,
      false,
      measure,
    );
    const noteY = bottom + 12;
    bottom = noteY + note.length * 20 + 14;
    const sources = artifact.sources.map((source) => {
      const lines = wrapText(
        `${refs.get(source.id) || source.id} · ${source.id} · ${source.label}${source.truncated ? ` · ${t("Partial source")}` : ""}`,
        width - 72,
        14,
        false,
        measure,
      );
      const y = bottom;
      bottom += lines.length * 20 + 12;
      return { source, lines, y };
    });
    return {
      width,
      height: bottom + 28,
      title,
      summary,
      top,
      legend,
      note,
      noteY,
      sources,
      statusLines,
      statusY,
    };
  }, [artifact, layout, language]);
  return (
    <svg
      ref={svgRef}
      xmlns="http://www.w3.org/2000/svg"
      className="document-diagram"
      viewBox={`0 ${frame.top} ${frame.width} ${frame.height - frame.top}`}
      width={frame.width}
      height={frame.height - frame.top}
      role="img"
      aria-labelledby={`${unique}-title ${unique}-description`}
      fontFamily="Manrope Variable, sans-serif"
      data-diagram-width={frame.width}
      data-diagram-height={frame.height - frame.top}
      data-export-width={frame.width}
      data-export-height={frame.height}
    >
      <title id={`${unique}-title`}>{artifact.title}</title>
      <desc id={`${unique}-description`}>
        {artifact.summary} {t("Complete text outline")}
      </desc>
      <defs>
        {(["flow", "dependency", "trust"] as const).map((kind) => (
          <marker
            key={kind}
            id={`${unique}-arrow-${kind}`}
            viewBox="0 0 12 10"
            refX="11"
            refY="5"
            markerWidth="10"
            markerHeight="9"
            orient="auto-start-reverse"
            markerUnits="userSpaceOnUse"
          >
            <path
              d="M1 1 L10 5 L1 9"
              fill="none"
              stroke={p[kind]}
              strokeWidth="2"
              strokeLinejoin="round"
            />
          </marker>
        ))}
      </defs>
      <rect
        width={frame.width}
        height={frame.height}
        rx="16"
        fill={p.background}
      />
      <text x="36" y="35" fill={p.muted} fontSize="13" letterSpacing="1.3">
        {t("Generated document · Review before use")}
      </text>
      <Lines
        lines={frame.title}
        x={36}
        y={76}
        size={26}
        step={34}
        color={p.ink}
        bold
      />
      <Lines
        lines={frame.summary}
        x={36}
        y={92 + frame.title.length * 34}
        size={16}
        step={24}
        color={p.muted}
      />
      <g transform={`translate(0 ${frame.top})`}>
        {layout.groups.map((group) => (
          <g key={group.item.id} data-diagram-group={group.item.id}>
            <rect
              x={group.x}
              y={group.y}
              width={group.width}
              height={group.height}
              rx="20"
              fill={p.group}
              stroke={p.border}
              strokeDasharray="6 5"
            />
            <Lines
              lines={group.title}
              x={group.x + 28}
              y={group.y + 36}
              size={17}
              step={24}
              color={p.ink}
              bold
            />
            <Lines
              lines={group.description}
              x={group.x + 28}
              y={group.y + 44 + group.title.length * 24}
              size={14}
              step={20}
              color={p.muted}
            />
          </g>
        ))}
        {layout.edges.map((edge) => (
          <g key={edge.item.id} data-diagram-edge={edge.item.id}>
            {edge.paths.map((points, index) => (
              <path
                key={index}
                className={
                  edge.item.kind === "flow" ? "document-flow" : undefined
                }
                d={points
                  .map((point, i) => `${i ? "L" : "M"}${point.x},${point.y}`)
                  .join(" ")}
                fill="none"
                stroke={p[edge.item.kind]}
                strokeWidth="2"
                strokeDasharray={
                  edge.item.kind === "dependency"
                    ? "7 5"
                    : edge.item.kind === "trust"
                      ? "2 5"
                      : undefined
                }
                markerEnd={`url(#${unique}-arrow-${edge.item.kind})`}
                strokeLinejoin="round"
              />
            ))}
          </g>
        ))}
        {layout.nodes.map((node) => (
          <g key={node.item.id} data-diagram-node={node.item.id}>
            <title>{`${node.item.label} · ${basisLabel(node.item.basis)} · ${node.item.source_ids.join(", ")}`}</title>
            <rect
              x={node.x}
              y={node.y}
              width={node.width}
              height={node.height}
              rx={node.item.kind === "control" ? 5 : 15}
              fill={p.card}
              stroke={p[node.item.kind]}
              strokeWidth="1.5"
              strokeDasharray={
                node.item.basis === "proposed"
                  ? "8 4"
                  : node.item.basis === "unknown"
                    ? "2 4"
                    : undefined
              }
            />
            <circle
              cx={node.x + 28}
              cy={node.y + 24}
              r="4"
              fill={p[node.item.kind]}
            />
            <text
              x={node.x + 40}
              y={node.y + 28}
              fill={p[node.item.kind]}
              fontSize="12"
            >
              {kindLabel(node.item.kind)}
            </text>
            <Lines
              lines={node.title}
              x={node.x + 24}
              y={node.y + 55}
              size={17}
              step={24}
              color={p.ink}
              bold
            />
            <Lines
              lines={node.description}
              x={node.x + 24}
              y={node.y + 67 + node.title.length * 24}
              size={15}
              step={22}
              color={p.muted}
            />
            <Lines
              lines={node.attribution}
              x={node.x + 24}
              y={node.y + node.height - 18 - (node.attribution.length - 1) * 18}
              size={12}
              step={18}
              color={p.muted}
            />
          </g>
        ))}
        {layout.edges.map(
          (edge) =>
            edge.label && (
              <g key={edge.item.id} data-diagram-label={edge.item.id}>
                <rect
                  x={edge.label.x}
                  y={edge.label.y}
                  width={edge.label.width}
                  height={edge.label.height}
                  rx="7"
                  fill={p.background}
                  stroke={p.border}
                  strokeWidth="0.7"
                />
                <Lines
                  lines={edge.label.lines}
                  x={edge.label.x + 12}
                  y={edge.label.y + 23}
                  size={14}
                  step={20}
                  color={p.ink}
                />
                <Lines
                  lines={edge.label.attribution}
                  x={edge.label.x + 12}
                  y={edge.label.y + 22 + edge.label.lines.length * 20}
                  size={12}
                  step={18}
                  color={p.muted}
                />
              </g>
            ),
        )}
      </g>
      <text
        x="36"
        y={frame.top + layout.height + 34}
        fontSize="17"
        fontWeight="600"
        fill={p.ink}
      >
        {t("Legend and provenance")}
      </text>
      {frame.legend.map((entry) => (
        <g key={entry.kind}>
          <rect
            x={entry.x}
            y={entry.y - 12}
            width="10"
            height="10"
            rx="3"
            fill={p[entry.kind]}
          />
          <Lines
            lines={entry.lines}
            x={entry.x + 22}
            y={entry.y}
            size={14}
            step={20}
            color={p.ink}
          />
        </g>
      ))}
      <Lines
        lines={frame.statusLines}
        x={36}
        y={frame.statusY}
        size={14}
        step={20}
        color={p.muted}
      />
      <Lines
        lines={frame.note}
        x={36}
        y={frame.noteY}
        size={14}
        step={20}
        color={p.muted}
      />
      {frame.sources.map((entry) => (
        <Lines
          key={entry.source.id}
          lines={entry.lines}
          x={36}
          y={entry.y}
          size={14}
          step={20}
          color={p.muted}
        />
      ))}
    </svg>
  );
}
