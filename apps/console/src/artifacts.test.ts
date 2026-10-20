import { describe, expect, it } from "vitest";
import { artifactFileName, memoryDraft, parseArtifacts } from "./artifacts";
import { diagramFixture, reportFixture } from "./artifact-fixtures";

describe("document trust boundary", () => {
  it("retains legacy replies and both supported documents", () => {
    expect(parseArtifacts(undefined)).toEqual([]);
    expect(parseArtifacts([diagramFixture])).toEqual([diagramFixture]);
    expect(parseArtifacts([reportFixture])).toEqual([reportFixture]);
  });
  it("rejects foreign versions, generated markup and unexpected attributes", () => {
    for (const change of [
      { schema_version: 2 },
      { type: "svg" },
      { html: "<script>unsafe()</script>" },
      { document: { svg: "<svg/>" } },
    ]) {
      expect(() =>
        parseArtifacts([{ ...diagramFixture, ...change }]),
      ).toThrow();
    }
  });
  it("rejects fabricated sources, disconnected IDs and repeated graph IDs", () => {
    const cases = [
      structuredClone(diagramFixture),
      structuredClone(diagramFixture),
      structuredClone(diagramFixture),
      structuredClone(diagramFixture),
    ];
    cases[0].document.nodes[0].source_ids = ["not-read"];
    cases[1].document.edges[0].target = "missing-node";
    cases[2].document.nodes[1].id = cases[2].document.nodes[0].id;
    cases[3].sources[0].kind = "generated";
    for (const value of cases) expect(() => parseArtifacts([value])).toThrow();
  });
  it("rejects malformed table dimensions and oversized documents", () => {
    const value = structuredClone(reportFixture);
    value.document.sections[0].table!.rows[0].push("unexpected cell");
    expect(() => parseArtifacts([value])).toThrow();
    expect(() =>
      parseArtifacts([{ ...reportFixture, summary: "x".repeat(1201) }]),
    ).toThrow();
    expect(() => parseArtifacts([diagramFixture, reportFixture])).toThrow();
  });
  it("rejects JSON coercion, direction controls, duplicate legends and empty sections", () => {
    for (const kind of [["service"], { toString: "service" }, null, 1]) {
      const value = structuredClone(diagramFixture) as unknown as {
        document: { nodes: { kind: unknown }[] };
      };
      value.document.nodes[0].kind = kind;
      expect(() => parseArtifacts([value])).toThrow();
    }
    for (const title of [
      "unsafe\u202eheading",
      " ",
      "javascript:run()",
      "<svg/>",
    ])
      expect(() => parseArtifacts([{ ...diagramFixture, title }])).toThrow();
    const duplicate = structuredClone(diagramFixture);
    duplicate.document.legend.push(duplicate.document.legend[0]);
    expect(() => parseArtifacts([duplicate])).toThrow();
    const empty = structuredClone(reportFixture);
    empty.document.sections[0] = {
      ...empty.document.sections[0],
      paragraphs: [],
      bullets: [],
      table: null,
    };
    expect(() => parseArtifacts([empty])).toThrow();
    expect(
      parseArtifacts([
        { ...diagramFixture, title: "Metadata: deployment observations" },
      ]),
    ).toHaveLength(1);
    expect(
      parseArtifacts([{ ...diagramFixture, title: "🛰".repeat(160) }]),
    ).toHaveLength(1);
  });
  it("preserves complete Unicode characters within the memory input limit", () => {
    const value = { ...diagramFixture, title: "A" + "🛰".repeat(80) };
    expect(parseArtifacts([value])).toHaveLength(1);
    const title = memoryDraft(value, "conversation").titre;
    expect(title).toBe("A" + "🛰".repeat(59));
    expect(title.length).toBeLessThanOrEqual(120);
    expect(new TextDecoder().decode(new TextEncoder().encode(title))).toBe(
      title,
    );
    const combined = "a".repeat(119) + "e\u0301";
    expect(
      memoryDraft({ ...value, title: combined }, "conversation").titre,
    ).toBe("a".repeat(119));
  });
  it("keeps arbitrary text inert and never makes generated knowledge a fact", () => {
    const value = structuredClone(diagramFixture);
    value.document.nodes[0].label = "<script>window.alert(1)</script>";
    expect(() => parseArtifacts([value])).toThrow();
    expect(memoryDraft(value, "conversation")).toMatchObject({
      type: "question",
      contenu: value.summary,
    });
    expect(
      artifactFileName({ ...value, title: "../../Private : review /" }, "svg"),
    ).toBe("Private-review.svg");
  });
});
