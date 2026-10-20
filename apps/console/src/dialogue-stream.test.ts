import { afterEach, describe, expect, it, vi } from "vitest";
import { savedDialogue, definirCsrf } from "./api";
import { diagramFixture, reportFixture } from "./artifact-fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  definirCsrf(null);
});
function stream(lines: unknown[], bytewise = false) {
  const bytes = new TextEncoder().encode(
    lines.map((line) => JSON.stringify(line)).join("\n") + "\n",
  );
  return new Response(
    new ReadableStream({
      start(controller) {
        if (bytewise)
          for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
        else controller.enqueue(bytes);
        controller.close();
      },
    }),
    { headers: { "Content-Type": "application/x-ndjson" } },
  );
}
describe("saved dialogue stream boundary", () => {
  it("retains a complete document across fragmented UTF-8 without streaming its JSON", async () => {
    const update = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        stream(
          [
            {
              type: "done",
              texte: diagramFixture.summary,
              artefacts: [diagramFixture],
            },
          ],
          true,
        ),
      ),
    );
    const reply = await savedDialogue(
      "id",
      { format: "diagram" },
      new AbortController().signal,
      update,
    );
    expect(reply.artefacts).toEqual([diagramFixture]);
    expect(update).not.toHaveBeenCalled();
  });
  it.each([
    [diagramFixture, reportFixture],
    [{ ...diagramFixture, document: { svg: "<svg onload='alert(1)'/>" } }],
    [{ ...diagramFixture, summary: "data:text/html,unsafe" }],
  ])(
    "rejects an invalid artifact even when its summary is a valid reply",
    async (...artefacts) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValue(
            stream([{ type: "done", texte: "Valid summary", artefacts }]),
          ),
      );
      await expect(
        savedDialogue("id", {}, new AbortController().signal, vi.fn()),
      ).rejects.toThrow();
    },
  );
  it("renders fragmented UTF-8 progressively and sends authenticated bounded input", async () => {
    const fetch = vi.fn().mockResolvedValue(
      stream(
        [
          { type: "token", text: "Bonjour, " },
          { type: "token", text: "Védric." },
          {
            type: "done",
            texte: "Bonjour, Védric.",
            usage: { total_tokens: 14 },
          },
        ],
        true,
      ),
    );
    vi.stubGlobal("fetch", fetch);
    definirCsrf("synthetic-csrf");
    const update = vi.fn();
    const result = await savedDialogue(
      "id",
      { message: "Hello" },
      new AbortController().signal,
      update,
    );
    expect(update.mock.calls.map(([text]) => text)).toEqual([
      "Bonjour, ",
      "Bonjour, Védric.",
    ]);
    expect(result.usage).toEqual({ total_tokens: 14 });
    expect(fetch).toHaveBeenCalledWith(
      "/api/conversations/id/messages",
      expect.objectContaining({
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": "synthetic-csrf",
        },
      }),
    );
  });
  it.each(
    [
      [{ type: "token", text: "Partial" }],
      [
        { type: "token", text: "Partial" },
        { type: "error", message: "Private upstream error" },
      ],
      [
        { type: "token", text: "One" },
        { type: "done", texte: "Another" },
      ],
      [
        { type: "done", texte: "Finished" },
        { type: "token", text: "Extra" },
      ],
      [{ type: "done", texte: "" }],
      [{ type: "token", text: "x".repeat(6001) }],
    ].map((events) => [events]),
  )(
    "rejects incomplete, contradictory or oversized responses",
    async (events) => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(stream(events)));
      await expect(
        savedDialogue("id", {}, new AbortController().signal, vi.fn()),
      ).rejects.toThrow();
    },
  );
  it("accepts an idempotent completed response with no repeated token events", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(stream([{ type: "done", texte: "Saved answer" }])),
    );
    const update = vi.fn();
    expect(
      (await savedDialogue("id", {}, new AbortController().signal, update))
        .texte,
    ).toBe("Saved answer");
    expect(update).not.toHaveBeenCalled();
  });
});
