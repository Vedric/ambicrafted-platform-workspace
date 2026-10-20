/** Versioned, data-only documents. Generated markup is never a rendering input. */
export type ArtifactFormat = "auto" | "text" | "diagram" | "report";
export type Basis = "provided" | "proposed" | "unknown";
export type NodeKind = "service" | "data" | "actor" | "external" | "control";
export type EdgeKind = "flow" | "dependency" | "trust";
export type ArtifactSource = {
  id: string;
  label: string;
  kind: "request" | "history" | "attachment" | "generated";
  sha256: string;
  truncated: boolean;
  verified: false;
};
export type Attribution = { basis: Basis; source_ids: string[] };
export type DiagramNode = Attribution & {
  id: string;
  label: string;
  description: string;
  kind: NodeKind;
  group_id: string | null;
};
export type DiagramEdge = Attribution & {
  id: string;
  source: string;
  target: string;
  label: string;
  kind: EdgeKind;
};
export type DiagramGroup = { id: string; label: string; description: string };
export type DiagramDocument = {
  direction: "LR" | "TB";
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  groups: DiagramGroup[];
  legend: { kind: NodeKind | EdgeKind; label: string }[];
};
export type ReportSection = Attribution & {
  id: string;
  heading: string;
  paragraphs: string[];
  bullets: string[];
  table: { columns: string[]; rows: string[][] } | null;
};
export type ReportDocument = { sections: ReportSection[] };
type ArtifactBase = {
  id: string;
  schema_version: 1;
  title: string;
  summary: string;
  sources: ArtifactSource[];
};
export type Artifact = ArtifactBase &
  (
    | { type: "diagram"; document: DiagramDocument }
    | { type: "report"; document: ReportDocument }
  );
export type DialogueReply = {
  texte: string;
  usage?: unknown;
  artefacts?: Artifact[];
};

const nodeKinds = ["service", "data", "actor", "external", "control"];
const edgeKinds = ["flow", "dependency", "trust"];
const identifier = /^[a-z][a-z0-9_-]{0,47}$/;
const uuid = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;

function requireValue(condition: unknown): asserts condition {
  if (!condition) throw new Error("Invalid document");
}
function object(value: unknown, keys: string[]): Record<string, unknown> {
  requireValue(
    value !== null && typeof value === "object" && !Array.isArray(value),
  );
  const item = value as Record<string, unknown>;
  requireValue(
    Object.keys(item).length === keys.length &&
      keys.every((key) => Object.hasOwn(item, key)),
  );
  return item;
}
function text(value: unknown, max: number, min = 0): asserts value is string {
  requireValue(
    typeof value === "string" &&
      [...value].length >= min &&
      [...value].length <= max,
  );
  requireValue(min === 0 || value.trim().length > 0);
  requireValue(
    !/<\s*\/?\s*[a-z!][^>]*>|https?:\/\/|\bjavascript:|\bdata:|```/i.test(
      value,
    ),
  );
  requireValue(!/[\p{Cc}\p{Cf}]/u.test(value.replace(/[\n\r\t]/g, "")));
}
function array(value: unknown, max: number, min = 0): unknown[] {
  requireValue(
    Array.isArray(value) &&
      [...value].length >= min &&
      [...value].length <= max,
  );
  return value;
}

/** Check the complete client boundary before retaining a streamed document. */
export function parseArtifacts(value: unknown): Artifact[] {
  if (value === undefined) return [];
  return array(value, 1).map((input) => {
    requireValue(
      new TextEncoder().encode(JSON.stringify(input)).length <= 65_536,
    );
    const item = object(input, [
      "id",
      "schema_version",
      "type",
      "title",
      "summary",
      "sources",
      "document",
    ]);
    requireValue(
      typeof item.id === "string" &&
        uuid.test(item.id) &&
        item.schema_version === 1,
    );
    text(item.title, 160, 1);
    text(item.summary, 1200, 1);
    const sourceIds = new Set<string>();
    const providedIds = new Set<string>();
    for (const raw of array(item.sources, 20, 1)) {
      const source = object(raw, [
        "id",
        "label",
        "kind",
        "sha256",
        "truncated",
        "verified",
      ]);
      text(source.id, 48, 1);
      requireValue(identifier.test(source.id));
      text(source.label, 160, 1);
      requireValue(!sourceIds.has(source.id));
      sourceIds.add(source.id);
      requireValue(
        typeof source.kind === "string" &&
          ["request", "history", "attachment", "generated"].includes(
            source.kind,
          ),
      );
      requireValue(
        typeof source.sha256 === "string" &&
          /^[a-f0-9]{64}$/.test(source.sha256),
      );
      requireValue(
        typeof source.truncated === "boolean" && source.verified === false,
      );
      if (source.kind !== "generated") providedIds.add(source.id);
    }
    function attribution(record: Record<string, unknown>) {
      requireValue(
        typeof record.basis === "string" &&
          ["provided", "proposed", "unknown"].includes(record.basis),
      );
      const refs = array(record.source_ids, 16);
      requireValue(
        refs.every((ref) => typeof ref === "string" && sourceIds.has(ref)),
      );
      requireValue(new Set(refs).size === refs.length);
      if (record.basis === "provided")
        requireValue(refs.some((ref) => providedIds.has(String(ref))));
    }
    const ids = new Set<string>();
    function id(value: unknown): string {
      requireValue(
        typeof value === "string" && identifier.test(value) && !ids.has(value),
      );
      ids.add(value);
      return value;
    }
    if (item.type === "diagram") {
      const document = object(item.document, [
        "direction",
        "nodes",
        "edges",
        "groups",
        "legend",
      ]);
      requireValue(document.direction === "LR" || document.direction === "TB");
      const groups = new Set<string>();
      for (const raw of array(document.groups, 6)) {
        const group = object(raw, ["id", "label", "description"]);
        groups.add(id(group.id));
        text(group.label, 100, 1);
        text(group.description, 300);
      }
      const nodes = new Set<string>();
      for (const raw of array(document.nodes, 24, 1)) {
        const node = object(raw, [
          "id",
          "label",
          "description",
          "kind",
          "group_id",
          "basis",
          "source_ids",
        ]);
        nodes.add(id(node.id));
        text(node.label, 100, 1);
        text(node.description, 240);
        requireValue(
          typeof node.kind === "string" && nodeKinds.includes(node.kind),
        );
        requireValue(
          node.group_id === null ||
            (typeof node.group_id === "string" && groups.has(node.group_id)),
        );
        attribution(node);
      }
      for (const raw of array(document.edges, 40)) {
        const edge = object(raw, [
          "id",
          "source",
          "target",
          "label",
          "kind",
          "basis",
          "source_ids",
        ]);
        id(edge.id);
        requireValue(
          typeof edge.source === "string" &&
            typeof edge.target === "string" &&
            nodes.has(edge.source) &&
            nodes.has(edge.target) &&
            edge.source !== edge.target,
        );
        text(edge.label, 100);
        requireValue(
          typeof edge.kind === "string" && edgeKinds.includes(edge.kind),
        );
        attribution(edge);
      }
      const legendKinds = new Set<string>();
      for (const raw of array(document.legend, 8)) {
        const legend = object(raw, ["kind", "label"]);
        requireValue(
          typeof legend.kind === "string" &&
            [...nodeKinds, ...edgeKinds].includes(legend.kind) &&
            !legendKinds.has(legend.kind),
        );
        legendKinds.add(legend.kind);
        text(legend.label, 160, 1);
      }
    } else if (item.type === "report") {
      const document = object(item.document, ["sections"]);
      for (const raw of array(document.sections, 10, 1)) {
        const section = object(raw, [
          "id",
          "heading",
          "paragraphs",
          "bullets",
          "table",
          "basis",
          "source_ids",
        ]);
        id(section.id);
        text(section.heading, 160, 1);
        for (const paragraph of array(section.paragraphs, 6))
          text(paragraph, 1800, 1);
        for (const bullet of array(section.bullets, 12)) text(bullet, 600, 1);
        attribution(section);
        requireValue(
          (section.paragraphs as unknown[]).length ||
            (section.bullets as unknown[]).length ||
            section.table !== null,
        );
        if (section.table !== null) {
          const table = object(section.table, ["columns", "rows"]);
          const columns = array(table.columns, 8, 1);
          for (const column of columns) text(column, 100, 1);
          for (const row of array(table.rows, 30)) {
            const cells = array(row, columns.length, columns.length);
            for (const cell of cells) text(cell, 500);
          }
        }
      }
    } else throw new Error("Invalid document type");
    return input as Artifact;
  });
}

export function artifactFileName(
  artifact: Artifact,
  extension: string,
): string {
  const title = artifact.title
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return `${title || artifact.type}.${extension}`;
}

/** HTML maxlength counts UTF-16 units; retain whole graphemes at its boundary. */
function truncateInput(value: string, maximum: number): string {
  let result = "";
  const segments = new Intl.Segmenter(undefined, {
    granularity: "grapheme",
  }).segment(value);
  for (const { segment } of segments) {
    if (result.length + segment.length > maximum) break;
    result += segment;
  }
  return result;
}

/** A reviewable note, never an automatic fact or a copy of the full client document. */
export function memoryDraft(artifact: Artifact, conversation: string) {
  return {
    titre: truncateInput(artifact.title, 120),
    contenu: artifact.summary,
    source: `Conversation ${conversation}; document ${artifact.id}`,
    type: "question" as const,
  };
}
