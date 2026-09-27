import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { Markdown } from "./App";

vi.mock("./Assistant", () => ({ default: () => <div>Local assistant</div> }));

let clients: QueryClient[] = [];
beforeEach(() => {
  localStorage.clear();
  // Welcome audio has its own lifecycle tests; auth tests do not drive jsdom media.
  localStorage.setItem("ambicrafted-welcome-audio", "off");
  window.history.replaceState(null, "", "/");
  // jsdom has no viewport intersection API; actual animation behavior is
  // exercised in Playwright with the real browser implementation.
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    },
  );
});
afterEach(() => {
  cleanup();
  clients.forEach((client) => client.clear());
  clients = [];
  vi.unstubAllGlobals();
});

function renderApp(strict = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  const application = (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(strict ? <StrictMode>{application}</StrictMode> : application);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

describe("private landing and failure states", () => {
  it("offers the local CLI when a password is not configured", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            connecte: false,
            mot_de_passe: false,
            csrf: null,
          }),
        ),
      ),
    );
    renderApp();
    expect(
      await screen.findByRole("heading", { name: /Intelligence/ }),
    ).toBeVisible();
    expect(screen.getByText("./plateforme ouvrir")).toBeVisible();
    expect(screen.queryByLabelText("Welcome back")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /Sign in from your terminal/ }),
    );
    expect(screen.getByText("./plateforme mot-de-passe")).toBeVisible();
  });

  it("shows an accessible password field and preserves a refused login error", async () => {
    const fetch = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        url === "/api/auth"
          ? new Response(
              JSON.stringify({
                connecte: false,
                mot_de_passe: true,
                csrf: null,
              }),
            )
          : new Response(JSON.stringify({ detail: "Connexion refusée." }), {
              status: 401,
            }),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    renderApp();
    const champ = await screen.findByLabelText("Welcome back");
    expect(champ).toHaveAttribute("type", "password");
    expect(champ).toHaveAttribute("autocomplete", "current-password");
    expect(champ).toHaveAttribute("placeholder", "Enter your password");
    await userEvent.type(champ, "Synthetic input");
    await userEvent.click(
      screen.getByRole("button", { name: "Enter workspace" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sign-in failed. Check your password and try again.",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/connexion",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ mot_de_passe: "Synthetic input" }),
      }),
    );
  });

  it("shows a retryable offline state and recovers after service availability returns", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Local service unavailable."))
      .mockResolvedValue(
        new Response(
          JSON.stringify({ connecte: false, mot_de_passe: false, csrf: null }),
        ),
      );
    vi.stubGlobal("fetch", fetch);
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The local API could not be reached. Check the connection and try again.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("heading", { name: /Intelligence/ }),
    ).toBeVisible();
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.filter(([path]) => path === "/api/auth"),
      ).toHaveLength(2),
    );
  });

  it("opens a ticket session when an older signed-out response arrives after the exchange", async () => {
    const staleSession = deferred<Response>();
    const exchangeRead = deferred<void>();
    let authenticated = false;
    const json = (payload: unknown) => new Response(JSON.stringify(payload));
    const fetch = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/auth") {
        return authenticated
          ? Promise.resolve(
              json({
                connecte: true,
                mot_de_passe: true,
                csrf: "synthetic-csrf",
              }),
            )
          : staleSession.promise;
      }
      if (url === "/api/auth/connexion") {
        authenticated = true;
        const response = json({ connecte: true });
        const read = response.json.bind(response);
        response.json = async () => {
          const payload = await read();
          exchangeRead.resolve();
          return payload;
        };
        return Promise.resolve(response);
      }
      if (url === "/api/vue-ensemble") {
        return Promise.resolve(
          json({
            total: 0,
            statuts: {},
            activite: [],
            runbooks: 0,
            journal: [],
            version: "test",
            sante: { ok: true, services: [], modeles: [], index: {} },
          }),
        );
      }
      if (url === "/api/analyses?taille=4") {
        return Promise.resolve(json({ elements: [], total: 0, page: 1 }));
      }
      throw new Error("Unexpected API request in the ticket exchange test");
    });
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState(
      null,
      "",
      "/#session=synthetic-single-use-ticket",
    );
    renderApp(true);
    await act(async () => {
      await exchangeRead.promise;
    });
    expect(window.location.hash).toBe("");
    expect(
      fetch.mock.calls.filter(([url]) => url === "/api/auth/connexion"),
    ).toHaveLength(1);
    await act(async () => {
      staleSession.resolve(
        json({ connecte: false, mot_de_passe: true, csrf: null }),
      );
    });
    // The route exists before its entrance transition becomes visible.
    // Keep the visibility assertion, but wait for the animation to advance.
    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          name: "Your intelligence, in motion.",
          level: 1,
        }),
      ).toBeVisible(),
    );
    expect(
      screen.queryByRole("heading", { name: /Intelligence/ }),
    ).not.toBeInTheDocument();
  });

  it("shows an expired ticket error and leaves password sign-in available in StrictMode", async () => {
    const fetch = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        url === "/api/auth/connexion"
          ? new Response(
              JSON.stringify({
                detail: "Lien de connexion expiré ou déjà utilisé.",
              }),
              { status: 401 },
            )
          : new Response(
              JSON.stringify({
                connecte: false,
                mot_de_passe: true,
                csrf: null,
              }),
            ),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState(null, "", "/#session=synthetic-expired-ticket");
    renderApp(true);
    expect(
      await screen.findByRole("heading", { name: /Intelligence/ }),
    ).toBeVisible();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This sign-in link has expired or already been used. Open a new one from your terminal.",
    );
    expect(screen.getByLabelText("Welcome back")).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Enter workspace" }),
    ).toBeEnabled();
    expect(window.location.hash).toBe("");
    expect(
      fetch.mock.calls.filter(([url]) => url === "/api/auth/connexion"),
    ).toHaveLength(1);
  });
});

describe("untrusted Markdown rendering", () => {
  it("does not execute or render raw HTML", async () => {
    const { container } = render(
      <Markdown
        texte={
          '# Source\n\n<script>window.stolen=true</script>\n\n<img src="https://outside.invalid/pixel" onerror="alert(1)">\n\n<iframe src="https://outside.invalid" />'
        }
      />,
    );
    expect(
      await screen.findByRole("heading", { name: "Source" }),
    ).toBeVisible();
    expect(container.querySelector("script, img, iframe")).toBeNull();
  });

  it("replaces Markdown images with inert alt text and strips executable link protocols", async () => {
    const { container } = render(
      <Markdown
        texte={
          "![Alternative text](https://outside.invalid/tracker.png)\n\n[Unsafe link](javascript:alert%281%29)\n\n[Documentation](https://example.invalid/docs)"
        }
      />,
    );
    expect(await screen.findByText("Alternative text")).toBeVisible();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    const lien = screen.getByRole("link", { name: "Documentation" });
    expect(lien).toHaveAttribute("rel", "noopener noreferrer");
    expect(lien).toHaveAttribute("target", "_blank");
  });
});
