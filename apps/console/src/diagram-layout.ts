import type { ElkNode, ElkExtendedEdge } from "elkjs/lib/elk-api";
import type {
  Attribution,
  Basis,
  DiagramDocument,
  DiagramNode,
  DiagramEdge,
  DiagramGroup,
} from "./artifacts";

export type MeasureText = (text: string, size: number, bold: boolean) => number;
export type TextLine = { text: string; width: number };
export type Rect = { x: number; y: number; width: number; height: number };
export type PlacedNode = Rect & {
  item: DiagramNode;
  title: TextLine[];
  description: TextLine[];
  attribution: TextLine[];
};
export type PlacedGroup = Rect & {
  item: DiagramGroup;
  title: TextLine[];
  description: TextLine[];
};
export type PlacedEdge = {
  item: DiagramEdge;
  paths: { x: number; y: number }[][];
  label: (Rect & { lines: TextLine[]; attribution: TextLine[] }) | null;
};
export type DiagramLayout = {
  width: number;
  height: number;
  nodes: PlacedNode[];
  groups: PlacedGroup[];
  edges: PlacedEdge[];
};
type Texts = {
  title: TextLine[];
  description: TextLine[];
  height: number;
  attribution: TextLine[];
};
export type BasisCaptions = Record<Basis, string>;
export type PreparedDiagram = {
  graph: ElkNode;
  nodeText: Map<string, Texts>;
  groupText: Map<string, Texts>;
  edgeText: Map<string, { lines: TextLine[]; attribution: TextLine[] }>;
};
const NODE_WIDTH = 288;
const INNER_WIDTH = NODE_WIDTH - 48;

/** Measured wrapping also splits an unbroken identifier; no clipping or ellipsis. */
export function wrapText(
  value: string,
  maxWidth: number,
  size: number,
  bold: boolean,
  measure: MeasureText,
): TextLine[] {
  if (!value.trim()) return [];
  const result: TextLine[] = [];
  for (const paragraph of value.replace(/\r\n?/g, "\n").split("\n")) {
    let line = "";
    for (const word of paragraph.trim().split(/\s+/)) {
      if (!word) continue;
      const candidate = line ? `${line} ${word}` : word;
      if (measure(candidate, size, bold) <= maxWidth) {
        line = candidate;
        continue;
      }
      if (line) result.push({ text: line, width: measure(line, size, bold) });
      line = "";
      for (const { segment: letter } of new Intl.Segmenter(undefined, {
        granularity: "grapheme",
      }).segment(word)) {
        if (line && measure(line + letter, size, bold) > maxWidth) {
          result.push({ text: line, width: measure(line, size, bold) });
          line = "";
        }
        line += letter;
      }
    }
    if (line) result.push({ text: line, width: measure(line, size, bold) });
  }
  return result;
}

export function sourceMarkers(document: DiagramDocument): Map<string, string> {
  return new Map(
    [
      ...new Set(
        [...document.nodes, ...document.edges].flatMap(
          (item) => item.source_ids,
        ),
      ),
    ]
      .sort()
      .map((id, index) => [id, `R${index + 1}`]),
  );
}
export function prepareDiagram(
  document: DiagramDocument,
  measure: MeasureText,
  spacious = false,
  captions: BasisCaptions = {
    provided: "Supplied context",
    proposed: "Proposed",
    unknown: "Unconfirmed",
  },
): PreparedDiagram {
  const nodeText = new Map<string, Texts>(),
    groupText = new Map<string, Texts>(),
    edgeText: PreparedDiagram["edgeText"] = new Map();
  const refs = sourceMarkers(document);
  const attribution = (item: Attribution, width: number) =>
    wrapText(
      `${captions[item.basis]}${item.source_ids.length ? ` · ${item.source_ids.map((id) => refs.get(id)).join(", ")}` : ""}`,
      width,
      12,
      false,
      measure,
    );
  const nodes: ElkNode[] = document.nodes.map((item) => {
    const title = wrapText(item.label, INNER_WIDTH, 17, true, measure);
    const description = wrapText(
      item.description,
      INNER_WIDTH,
      15,
      false,
      measure,
    );
    const origin = attribution(item, INNER_WIDTH);
    const height =
      58 +
      title.length * 24 +
      (description.length ? 12 + description.length * 22 : 0) +
      16 +
      origin.length * 18;
    nodeText.set(item.id, { title, description, height, attribution: origin });
    return { id: item.id, width: NODE_WIDTH, height };
  });
  const groups: ElkNode[] = document.groups.map((item) => {
    const title = wrapText(item.label, INNER_WIDTH, 17, true, measure);
    const description = wrapText(
      item.description,
      INNER_WIDTH,
      14,
      false,
      measure,
    );
    const height =
      30 +
      title.length * 24 +
      description.length * 20 +
      (description.length ? 8 : 0);
    groupText.set(item.id, { title, description, height, attribution: [] });
    const children = nodes.filter(
      (node) =>
        document.nodes.find((item) => item.id === node.id)?.group_id ===
        item.id,
    );
    return {
      id: item.id,
      width: NODE_WIDTH + 56,
      height: height + 48,
      children,
      layoutOptions: {
        "elk.padding": `[top=${height + 20},left=28,bottom=28,right=28]`,
        "elk.nodeSize.constraints": "MINIMUM_SIZE",
        "elk.nodeSize.minimum": `(${NODE_WIDTH + 56},${height + 48})`,
      },
    };
  });
  const edges: ElkExtendedEdge[] = document.edges.map((item) => {
    const lines = wrapText(item.label, 196, 14, false, measure);
    const origin = attribution(item, 196);
    edgeText.set(item.id, { lines, attribution: origin });
    return {
      id: item.id,
      sources: [item.source],
      targets: [item.target],
      labels: [
        {
          id: `label:${item.id}`,
          text: item.label || " ",
          width:
            Math.max(...[...lines, ...origin].map((line) => line.width)) + 24,
          height: lines.length * 20 + origin.length * 18 + 22,
        },
      ],
      layoutOptions: { "elk.edgeLabels.placement": "CENTER" },
    };
  });
  return {
    nodeText,
    groupText,
    edgeText,
    graph: {
      id: ":root",
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": document.direction === "LR" ? "RIGHT" : "DOWN",
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.hierarchyHandling": "INCLUDE_CHILDREN",
        "elk.padding": "[top=36,left=36,bottom=36,right=36]",
        "elk.spacing.nodeNode": spacious ? "110" : "64",
        "elk.layered.spacing.nodeNodeBetweenLayers": spacious ? "156" : "100",
        "elk.spacing.edgeNode": "30",
        "elk.spacing.edgeEdge": "22",
        "elk.spacing.edgeLabel": "16",
        "elk.spacing.labelNode": "20",
        "elk.layered.spacing.edgeNodeBetweenLayers": spacious ? "64" : "36",
        "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
        "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
        "elk.randomSeed": "1",
        "elk.layered.mergeEdges": "false",
      },
      children: [
        ...nodes.filter(
          (node) =>
            !document.nodes.find((item) => item.id === node.id)?.group_id,
        ),
        ...groups,
      ],
      edges,
    },
  };
}

export function rectanglesOverlap(a: Rect, b: Rect, gap = 0): boolean {
  return (
    a.x < b.x + b.width + gap &&
    a.x + a.width + gap > b.x &&
    a.y < b.y + b.height + gap &&
    a.y + a.height + gap > b.y
  );
}
function geometry(
  shape: { x?: number; y?: number; width?: number; height?: number },
  x = 0,
  y = 0,
): Rect {
  const result = {
    x: (shape.x ?? 0) + x,
    y: (shape.y ?? 0) + y,
    width: shape.width ?? 0,
    height: shape.height ?? 0,
  };
  if (
    Object.values(result).some((number) => !Number.isFinite(number)) ||
    result.width <= 0 ||
    result.height <= 0
  )
    throw new Error("Invalid layout geometry");
  return result;
}

/** Reject unreadable layouts rather than drawing overlapping labels silently. */
export function readLayout(
  graph: ElkNode,
  document: DiagramDocument,
  prepared: PreparedDiagram,
): DiagramLayout {
  const result: DiagramLayout = {
    width: graph.width ?? 0,
    height: graph.height ?? 0,
    nodes: [],
    groups: [],
    edges: [],
  };
  const rects: Rect[] = [];
  const origins = new Map<string, { x: number; y: number }>();
  function locate(node: ElkNode, x = 0, y = 0) {
    const origin = { x: x + (node.x ?? 0), y: y + (node.y ?? 0) };
    origins.set(node.id, origin);
    for (const child of node.children ?? []) locate(child, origin.x, origin.y);
  }
  locate(graph);
  function visit(parent: ElkNode, parentX = 0, parentY = 0) {
    for (const child of parent.children ?? []) {
      const box = geometry(child, parentX, parentY);
      const item = document.nodes.find((node) => node.id === child.id);
      if (item) {
        const texts = prepared.nodeText.get(item.id)!;
        if (box.width < NODE_WIDTH - 0.01 || box.height < texts.height - 0.01)
          throw new Error("Node text would be clipped");
        result.nodes.push({
          ...box,
          item,
          title: texts.title,
          description: texts.description,
          attribution: texts.attribution,
        });
        rects.push(box);
      } else {
        const group = document.groups.find((item) => item.id === child.id);
        if (!group) throw new Error("Unknown layout group");
        const texts = prepared.groupText.get(group.id)!;
        result.groups.push({
          ...box,
          item: group,
          title: texts.title,
          description: texts.description,
        });
        rects.push({
          x: box.x + 28,
          y: box.y + 12,
          width: INNER_WIDTH,
          height: texts.height,
        });
        visit(child, box.x, box.y);
      }
    }
    for (const raw of parent.edges ?? []) {
      const edge = raw as ElkExtendedEdge;
      const item = document.edges.find((entry) => entry.id === edge.id);
      if (!item || !edge.sections?.length)
        throw new Error("Missing edge route");
      // ELK retains edges in the input array but returns coordinates relative
      // to their lowest common container, which can be a nested group.
      const container = (edge as ElkExtendedEdge & { container?: string })
        .container;
      const origin = container
        ? origins.get(container)
        : { x: parentX, y: parentY };
      if (!origin) throw new Error("Unknown edge container");
      const paths = edge.sections.map((section) =>
        [
          section.startPoint,
          ...(section.bendPoints ?? []),
          section.endPoint,
        ].map((point) => ({ x: point.x + origin.x, y: point.y + origin.y })),
      );
      if (
        paths
          .flat()
          .some(
            (point) => !Number.isFinite(point.x) || !Number.isFinite(point.y),
          )
      )
        throw new Error("Invalid edge route");
      const texts = prepared.edgeText.get(item.id)!;
      const label = {
        ...geometry(edge.labels?.[0] ?? {}, origin.x, origin.y),
        ...texts,
      };
      if (label) rects.push(label);
      result.edges.push({ item, paths, label });
    }
  }
  visit(graph);
  if (
    !Number.isFinite(result.width) ||
    !Number.isFinite(result.height) ||
    result.width <= 0 ||
    result.height <= 0 ||
    result.width > 30_000 ||
    result.height > 30_000
  )
    throw new Error("Diagram exceeds the readable canvas");
  if (
    result.nodes.length !== document.nodes.length ||
    result.edges.length !== document.edges.length
  )
    throw new Error("Incomplete diagram layout");
  for (let i = 0; i < rects.length; i++) {
    const box = rects[i];
    if (
      box.x < -0.1 ||
      box.y < -0.1 ||
      box.x + box.width > result.width + 0.1 ||
      box.y + box.height > result.height + 0.1
    )
      throw new Error("Diagram content is clipped");
    for (let j = i + 1; j < rects.length; j++)
      if (rectanglesOverlap(box, rects[j], 3))
        throw new Error("Diagram labels overlap");
  }
  return result;
}
