import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  apercu,
  definirCsrf,
  ErreurAPI,
  type Diagnostic,
  type Rapport,
} from "./api";

const diagnostic: Diagnostic = {
  cause_probable: "Connexions saturées",
  confiance: "moyenne",
  runbook_source: "postgres.md",
  actions_proposees: ["Vérifier le nombre de connexions."],
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
      await api("/analyses", method, { titre: "Synthétique" });
      expect(fetch).toHaveBeenCalledWith(
        "/api/analyses",
        expect.objectContaining({
          method,
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": "synthetic-csrf-value",
          },
          body: JSON.stringify({ titre: "Synthétique" }),
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
        message: "Session expirée.",
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
    for (let i = 0; i < 2; i++) {
      await expect(api("/analyses")).rejects.toMatchObject({
        message: "Requête refusée. Vérifier les données saisies.",
      });
    }
  });

  it("propagates network and abort failures without substituting a successful result", async () => {
    const erreur = new DOMException("Aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(erreur));
    await expect(api("/analyses")).rejects.toBe(erreur);
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
