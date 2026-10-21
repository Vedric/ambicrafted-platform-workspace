import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { setLanguage } from "../i18n";
import { Observabilite } from "./plateforme";
vi.mock("../api", async (original) => ({
  ...(await original<typeof import("../api")>()),
  api: vi.fn(),
}));
let client: QueryClient;
beforeEach(() => {
  setLanguage("en");
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  cleanup();
  client.clear();
  vi.restoreAllMocks();
});
function show() {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Observabilite />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it.each(["en", "fr"] as const)(
  "links six distinct operational dashboards in %s with explicit browser scope",
  async (language) => {
    setLanguage(language);
    vi.mocked(api).mockResolvedValue({
      cibles: [
        {
          nom: "API",
          sante: "up",
          dernier_scrape: "2026-10-21T08:00:00Z",
          duree_s: 0.03,
        },
        {
          nom: "GPU",
          sante: "down",
          dernier_scrape: "2026-10-21T08:00:00Z",
          duree_s: 0.01,
        },
      ],
      journal: [],
    });
    const { container } = show();
    await screen.findByText("API");
    const links = [
      ...container.querySelectorAll<HTMLAnchorElement>(".monitoring-card"),
    ];
    expect(links.map((l) => l.href)).toEqual(
      ["slo", "experience", "traces", "sre", "agentic", "infrastructure"].map(
        (uid) =>
          `http://localhost:3000/d/plateforme-${uid}${language === "fr" ? "-fr" : ""}`,
      ),
    );
    for (const link of links) {
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
      expect(link.querySelector("h2")?.textContent).not.toBe("");
    }
    expect(
      container.querySelector(".observability-kpis")?.textContent,
    ).toContain("1 / 2");
    expect(
      container.querySelector(".observability-note")?.textContent,
    ).toContain(
      language === "fr"
        ? "sans contenu ni URL complète"
        : "no page content or full URLs",
    );
    expect(container.querySelector(".monitoring-grid")?.textContent).toContain(
      language === "fr" ? "première période visible" : "first visible period",
    );
  },
);
it("does not invent healthy targets while data is unavailable", () => {
  vi.mocked(api).mockReturnValue(new Promise(() => {}));
  const { container } = show();
  expect(
    [...container.querySelectorAll(".observability-kpis dd")]
      .slice(0, 2)
      .map((e) => e.textContent),
  ).toEqual(["—", "—"]);
});
it("does not keep cached healthy counters when collection refresh fails", async () => {
  client.setQueryData(["observabilite"], {
    cibles: [
      {
        nom: "API",
        sante: "up",
        dernier_scrape: "2026-10-21T08:00:00Z",
        duree_s: 0.03,
      },
    ],
    journal: [],
  });
  vi.mocked(api).mockRejectedValue(new Error("Collection unavailable"));
  const { container } = show();
  await screen.findByRole("alert");
  expect(
    [...container.querySelectorAll(".observability-kpis dd")]
      .slice(0, 2)
      .map((e) => e.textContent),
  ).toEqual(["Unknown", "Unknown"]);
});
it.each(["en", "fr"] as const)(
  "does not report zero failed targets when collection returns no targets in %s",
  async (language) => {
    setLanguage(language);
    vi.mocked(api).mockResolvedValue({ cibles: [], journal: [] });
    const { container } = show();
    await screen.findByRole("heading", {
      name: language === "fr" ? "Aucune cible remontée" : "No targets reported",
    });
    const values = [...container.querySelectorAll(".observability-kpis dd")]
      .slice(0, 2)
      .map((e) => e.textContent);
    expect(values).toEqual(
      language === "fr"
        ? ["InconnuAucune cible remontée", "Inconnu"]
        : ["UnknownNo targets reported", "Unknown"],
    );
    expect(
      container.querySelector(".observability-kpis > div:nth-child(2) dt")
        ?.textContent,
    ).toBe(language === "fr" ? "Cibles en échec" : "Failed targets");
  },
);
