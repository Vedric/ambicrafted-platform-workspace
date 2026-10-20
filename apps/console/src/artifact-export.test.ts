import { afterEach, describe, expect, it, vi } from "vitest";
import {
  exportDiagram,
  exportStoredDocument,
  serializeDiagram,
} from "./artifact-export";
import { diagramFixture } from "./artifact-fixtures";
afterEach(() => vi.unstubAllGlobals());
describe("private document exports", () => {
  it("signals session expiry and refuses to download an error as a document", async () => {
    const expired = vi.fn();
    window.addEventListener("session-expiree", expired);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response('{"detail":"private diagnostic"}', { status: 401 }),
        ),
    );
    await expect(
      exportStoredDocument("conversation", diagramFixture, "json"),
    ).rejects.toThrow("could not be exported");
    expect(expired).toHaveBeenCalledOnce();
    expect(document.querySelector("a[download]")).toBeNull();
    window.removeEventListener("session-expiree", expired);
  });
  it("bounds a download even when content length is absent or false", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response("x".repeat(262145), {
        headers: {
          "Content-Type": "application/json",
          "Content-Length": "10",
        },
      }),
    );
    vi.stubGlobal("fetch", fetch);
    await expect(
      exportStoredDocument("conversation", diagramFixture, "json"),
    ).rejects.toThrow();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/conversations/conversation/artefacts/"),
      expect.objectContaining({
        credentials: "same-origin",
        redirect: "error",
      }),
    );
  });
  it("keeps SVG dimensions in exports and refuses a PNG that would silently lose readability", async () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "9000");
    svg.setAttribute("height", "8000");
    svg.setAttribute("style", "transform:scale(0.2)");
    svg.setAttribute("class", "document-flow");
    const title = document.createElementNS(svg.namespaceURI, "title");
    title.textContent = "Observations & proposals";
    svg.append(title);
    const output = serializeDiagram(svg);
    expect(output).toContain('width="9000"');
    expect(output).not.toContain("transform");
    expect(output).toContain("Observations &amp; proposals");
    await expect(exportDiagram(svg, diagramFixture, "png")).rejects.toThrow(
      "too large",
    );
  });
});
