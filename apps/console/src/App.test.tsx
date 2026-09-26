import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { Markdown } from "./App";

vi.mock("./Assistant", () => ({ default: () => <div>Local assistant</div> }));

let clients: QueryClient[] = [];
beforeEach(() => {
  localStorage.clear();
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

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
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
      await screen.findByRole("heading", { name: /Your next move/ }),
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
      await screen.findByRole("heading", { name: /Your next move/ }),
    ).toBeVisible();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  });
});

describe("untrusted Markdown rendering", () => {
  it("does not execute or render raw HTML", () => {
    const { container } = render(
      <Markdown
        texte={
          '# Source\n\n<script>window.stolen=true</script>\n\n<img src="https://outside.invalid/pixel" onerror="alert(1)">\n\n<iframe src="https://outside.invalid" />'
        }
      />,
    );
    expect(screen.getByRole("heading", { name: "Source" })).toBeVisible();
    expect(container.querySelector("script, img, iframe")).toBeNull();
  });

  it("replaces Markdown images with inert alt text and strips executable link protocols", () => {
    const { container } = render(
      <Markdown
        texte={
          "![Alternative text](https://outside.invalid/tracker.png)\n\n[Unsafe link](javascript:alert%281%29)\n\n[Documentation](https://example.invalid/docs)"
        }
      />,
    );
    expect(screen.getByText("Alternative text")).toBeVisible();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    const lien = screen.getByRole("link", { name: "Documentation" });
    expect(lien).toHaveAttribute("rel", "noopener noreferrer");
    expect(lien).toHaveAttribute("target", "_blank");
  });
});
