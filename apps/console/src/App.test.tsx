import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { Markdown } from "./App";

vi.mock("./Assistant", () => ({ default: () => <div>Assistant local</div> }));

let clients: QueryClient[] = [];
beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "/");
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
      await screen.findByRole("heading", { name: /Votre astreinte/ }),
    ).toBeVisible();
    expect(screen.getByText("./plateforme ouvrir")).toBeVisible();
    expect(
      screen.queryByLabelText("Retrouver votre espace"),
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /Connexion depuis le terminal/ }),
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
    const champ = await screen.findByLabelText("Retrouver votre espace");
    expect(champ).toHaveAttribute("type", "password");
    expect(champ).toHaveAttribute("autocomplete", "current-password");
    await userEvent.type(champ, "Saisie synthétique");
    await userEvent.click(screen.getByRole("button", { name: "Entrer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Connexion refusée.",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/connexion",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ mot_de_passe: "Saisie synthétique" }),
      }),
    );
  });

  it("shows a retryable offline state and recovers after service availability returns", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Réseau local indisponible."))
      .mockResolvedValue(
        new Response(
          JSON.stringify({ connecte: false, mot_de_passe: false, csrf: null }),
        ),
      );
    vi.stubGlobal("fetch", fetch);
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Réseau local indisponible.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(
      await screen.findByRole("heading", { name: /Votre astreinte/ }),
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
          "![Texte alternatif](https://outside.invalid/tracker.png)\n\n[Lien dangereux](javascript:alert%281%29)\n\n[Documentation](https://example.invalid/docs)"
        }
      />,
    );
    expect(screen.getByText("Texte alternatif")).toBeVisible();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    const lien = screen.getByRole("link", { name: "Documentation" });
    expect(lien).toHaveAttribute("rel", "noopener noreferrer");
    expect(lien).toHaveAttribute("target", "_blank");
  });
});
