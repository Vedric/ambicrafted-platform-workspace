import { afterEach, describe, expect, it, vi } from "vitest";
import {
  exportDiagram,
  exportStoredDocument,
  serializeDiagram,
} from "./artifact-export";
import { diagramFixture } from "./artifact-fixtures";
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
describe("private document exports", () => {
  it.each(["image", "canvas"])(
    "releases a revoked PNG export during %s conversion",
    async (stage) => {
      let bitmap!: {
        onload: (() => void) | null;
        onerror: (() => void) | null;
        src: string;
      };
      vi.stubGlobal(
        "Image",
        class {
          onload = null;
          onerror = null;
          src = "";
          constructor() {
            bitmap = this;
          }
        },
      );
      let encode!: BlobCallback;
      let canvas!: HTMLCanvasElement;
      vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
        function (this: HTMLCanvasElement) {
          canvas = this;
          return { drawImage: vi.fn() } as unknown as CanvasRenderingContext2D;
        },
      );
      vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(
        (callback) => {
          encode = callback;
        },
      );
      const click = vi
        .spyOn(HTMLAnchorElement.prototype, "click")
        .mockImplementation(() => {});
      const added = vi.spyOn(window, "addEventListener"),
        removed = vi.spyOn(window, "removeEventListener");
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("width", "800");
      svg.setAttribute("height", "600");
      const pending = exportDiagram(svg, diagramFixture, "png");
      const rejected = expect(pending).rejects.toThrow();
      const loaded = bitmap.onload;
      if (stage === "canvas") {
        loaded?.();
        await vi.waitFor(() => expect(encode).toBeTypeOf("function"));
      }
      window.dispatchEvent(new Event("session-expiree"));
      await rejected;
      expect(canvas.width).toBe(0);
      expect(canvas.height).toBe(0);
      expect(bitmap.src).toBe("");
      expect(bitmap.onload).toBeNull();
      if (stage === "canvas") encode(new Blob(["synthetic PNG"]));
      else loaded?.();
      await Promise.resolve();
      expect(click).not.toHaveBeenCalled();
      const listener = added.mock.calls.find(
        ([event]) => event === "session-expiree",
      )![1];
      expect(removed).toHaveBeenCalledWith("session-expiree", listener);
    },
  );
  it("aborts a pending export on session revocation and rejects a late success", async () => {
    let complete!: (response: Response) => void;
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, options) => {
        signal = options.signal;
        return new Promise<Response>((resolve) => {
          complete = resolve;
        });
      }),
    );
    const pending = exportStoredDocument(
      "conversation",
      diagramFixture,
      "json",
    );
    const rejected = expect(pending).rejects.toThrow();
    window.dispatchEvent(new Event("session-expiree"));
    expect(signal?.aborted).toBe(true);
    // Even a transport that delivers an already-buffered result after abort
    // must not reach the irreversible browser download step.
    complete(
      new Response(JSON.stringify(diagramFixture), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    await rejected;
    expect(document.querySelector("a[download]")).toBeNull();
  });
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
