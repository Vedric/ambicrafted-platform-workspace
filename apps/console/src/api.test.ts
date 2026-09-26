import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  apercu,
  definirCsrf,
  ErreurAPI,
  date,
  type Diagnostic,
  type Rapport,
} from "./api";

const diagnostic: Diagnostic = {
  cause_probable: "Connection pool exhausted",
  confiance: "moyenne",
  runbook_source: "postgres.md",
  actions_proposees: ["Check the connection count."],
  elements_manquants: [],
};

beforeEach(() => definirCsrf(null));
afterEach(() => vi.unstubAllGlobals());

describe("authenticated API contract", () => {
  it("uses same-origin credentials and forwards cancellation for reads", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetch);
    const signal = new AbortController().signal;
    await expect(api("/sante", "GET", undefined, signal)).resolves.toEqual({
      ok: true,
    });
    expect(fetch).toHaveBeenCalledWith("/api/sante", {
      method: "GET",
      credentials: "same-origin",
      signal,
      headers: {},
      body: undefined,
    });
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"])(
    "sends JSON and the current CSRF token on %s",
    async (method) => {
      const fetch = vi.fn().mockResolvedValue(new Response("{}"));
      vi.stubGlobal("fetch", fetch);
      definirCsrf("synthetic-csrf-value");
      await api("/analyses", method, { titre: "Synthetic" });
      expect(fetch).toHaveBeenCalledWith(
        "/api/analyses",
        expect.objectContaining({
          method,
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": "synthetic-csrf-value",
          },
          body: JSON.stringify({ titre: "Synthetic" }),
        }),
      );
    },
  );

  it("clears stale CSRF tokens and sends an explicit empty JSON object", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    definirCsrf("previous-session");
    definirCsrf(null);
    await api("/auth/deconnexion", "POST");
    expect(fetch.mock.calls[0][1]).toMatchObject({
      headers: { "X-CSRF-Token": "" },
      body: "{}",
    });
  });

  it("announces expiration on a protected 401 and preserves the status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Session expirée." }), {
          status: 401,
        }),
      ),
    );
    const expiree = vi.fn();
    window.addEventListener("session-expiree", expiree);
    try {
      await expect(api("/analyses")).rejects.toMatchObject({
        status: 401,
        message: "Your session has expired. Sign in again.",
      });
      expect(expiree).toHaveBeenCalledOnce();
    } finally {
      window.removeEventListener("session-expiree", expiree);
    }
  });

  it("does not announce expiration for a refused login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
    );
    const expiree = vi.fn();
    window.addEventListener("session-expiree", expiree);
    try {
      await expect(api("/auth/connexion", "POST", {})).rejects.toBeInstanceOf(
        ErreurAPI,
      );
      expect(expiree).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("session-expiree", expiree);
    }
  });

  it.each([
    {
      status: 409,
      detail:
        "Ce runbook a changé. Recharger sa dernière version avant d'enregistrer.",
      message:
        "This runbook has changed. Reload the latest version before saving.",
    },
    {
      status: 403,
      detail: "Validation de la session requise. Actualiser la page.",
      message: "Refresh the page to validate your session.",
    },
    {
      status: 503,
      detail: "Unrecognized diagnostic containing synthetic-private-data",
      message:
        "This service is unavailable. Check system health and try again.",
    },
  ])(
    "renders a safe English error for status $status",
    async ({ status, detail, message }) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValue(
            new Response(JSON.stringify({ detail }), { status }),
          ),
      );
      await expect(api("/runbooks/postgres.md")).rejects.toMatchObject({
        status,
        message,
      });
    },
  );

  it("replaces structured validation details and malformed error bodies with a safe message", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ detail: [{ input: "not for display" }] }),
          { status: 422 },
        ),
      )
      .mockResolvedValueOnce(
        new Response("<html>proxy error</html>", { status: 503 }),
      );
    vi.stubGlobal("fetch", fetch);
    for (const message of [
      "Check your input and try again.",
      "This service is unavailable. Check system health and try again.",
    ]) {
      await expect(api("/analyses")).rejects.toMatchObject({
        message,
      });
    }
  });

  it("propagates network and abort failures without substituting a successful result", async () => {
    const erreur = new DOMException("Aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(erreur));
    await expect(api("/analyses")).rejects.toBe(erreur);
  });
});

describe("English display locale", () => {
  it("formats valid dates in English and keeps invalid dates inert", () => {
    expect(date("2026-09-26T15:20:00Z")).toContain("Sep 26, 2026");
    expect(date("not a date")).toBe("—");
  });
});

describe("diagnostic preview", () => {
  it("returns a delivered diagnostic and a valid pending preview", () => {
    expect(apercu({ statut: "complet", diagnostic })).toEqual(diagnostic);
    expect(
      apercu({
        statut: "en_attente_humain",
        message: JSON.stringify(diagnostic),
      }),
    ).toEqual(diagnostic);
  });

  it("does not interpret rejected or arbitrary messages as a diagnosis", () => {
    expect(apercu(undefined)).toBeUndefined();
    expect(
      apercu({
        statut: "rejete_par_humain",
        message: JSON.stringify(diagnostic),
      }),
    ).toBeUndefined();
    expect(
      apercu({ statut: "en_attente_humain", message: "incomplete {" }),
    ).toBeUndefined();
  });

  it.each([
    null,
    [],
    42,
    "unexpected",
    {},
    { cause_probable: "missing fields" },
    {
      ...diagnostic,
      actions_proposees: [42],
    },
    { ...diagnostic, elements_manquants: "wrong type" },
  ])("rejects malformed pending diagnostic shape: %j", (valeur) => {
    expect(
      apercu({ statut: "en_attente_humain", message: JSON.stringify(valeur) }),
    ).toBeUndefined();
  });

  it("rejects malformed delivered diagnostics instead of trusting a TypeScript cast", () => {
    expect(
      apercu({
        statut: "complet",
        diagnostic: { cause_probable: "missing fields" },
      } as Rapport),
    ).toBeUndefined();
  });
});
