import { describe, expect, it } from "vitest";
import ELK from "elkjs/lib/elk.bundled.js";
import { diagramFixture } from "./artifact-fixtures";
import {
  prepareDiagram,
  readLayout,
  wrapText,
  type MeasureText,
} from "./diagram-layout";

const measure: MeasureText = (text, size, bold) =>
  [...text].reduce(
    (width, letter) =>
      width + (/W|M/.test(letter) ? size * 0.9 : size * (bold ? 0.62 : 0.56)),
    0,
  );

describe("readable diagram geometry", () => {
  it("wraps complete labels, including long identifiers, without truncation", () => {
    const value = "Kubernetes W".repeat(8);
    const lines = wrapText(value, 200, 17, true, measure);
    expect(lines.length).toBeGreaterThan(2);
    expect(lines.every((line) => line.width <= 200)).toBe(true);
    expect(
      lines
        .map((line) => line.text)
        .join("")
        .replace(/\s/g, ""),
    ).toBe(value.replace(/\s/g, ""));
  });
  it.each(["LR", "TB"] as const)(
    "lays out measured nodes, group headers and edge labels in %s",
    async (direction) => {
      const document = structuredClone(diagramFixture.document);
      document.direction = direction;
      const prepared = prepareDiagram(document, measure);
      const graph = await new ELK().layout(prepared.graph);
      const result = readLayout(graph, document, prepared);
      expect(result.nodes).toHaveLength(4);
      expect(result.groups).toHaveLength(1);
      expect(
        result.edges.every((edge) => edge.paths.length > 0 && edge.label),
      ).toBe(true);
    },
  );
  it("preserves long French labels in a branching cyclic graph", async () => {
    const document = structuredClone(diagramFixture.document);
    document.nodes[0].label =
      "Évaluation des accès et des dépendances de l’application";
    document.nodes[1].description =
      "Une observation reste une observation. La consultation d’un document ne prouve pas la cause de l’incident.";
    document.edges.push({
      ...document.edges[0],
      id: "feedback",
      source: "review",
      target: "operator",
      label: "Correction ou informations supplémentaires",
    });
    const prepared = prepareDiagram(document, measure, true);
    const graph = await new ELK().layout(prepared.graph);
    const result = readLayout(graph, document, prepared);
    expect(result.nodes[0].title.length).toBeGreaterThan(1);
    expect(result.edges).toHaveLength(4);
  });
  it("refuses a layout that drops content or clips its measured text", async () => {
    const document = structuredClone(diagramFixture.document);
    const prepared = prepareDiagram(document, measure);
    const graph = await new ELK().layout(prepared.graph);
    graph.children![0].width = 10;
    expect(() => readLayout(graph, document, prepared)).toThrow("clipped");
  });
  it("keeps the maximum node and edge counts readable across six groups", async () => {
    const document = structuredClone(diagramFixture.document);
    document.groups = Array.from({ length: 6 }, (_, i) => ({
      id: `group-${i}`,
      label: `Boundary ${i + 1}`,
      description: "Independent operational responsibility",
    }));
    document.nodes = Array.from({ length: 24 }, (_, i) => ({
      ...document.nodes[0],
      id: `node-${i}`,
      group_id: `group-${Math.floor(i / 4)}`,
      label: `Component ${i + 1} · observed scope and evidence`,
      description:
        "Compare the requested scope with the supplied observations. Record uncertainties before deciding.",
    }));
    document.edges = Array.from({ length: 40 }, (_, i) => ({
      ...document.edges[0],
      id: `edge-${i}`,
      source: `node-${i % 24}`,
      target: `node-${(i + (i < 24 ? 1 : 5)) % 24}`,
      label: `Context ${i + 1} and investigation findings`,
    }));
    let result;
    for (const spacious of [false, true]) {
      const prepared = prepareDiagram(document, measure, spacious);
      const graph = await new ELK().layout(prepared.graph);
      try {
        result = readLayout(graph, document, prepared);
        break;
      } catch (error) {
        if (spacious) throw error;
      }
    }
    expect(result?.nodes).toHaveLength(24);
    expect(result?.edges).toHaveLength(40);
    expect(result?.groups).toHaveLength(6);
  });
});
