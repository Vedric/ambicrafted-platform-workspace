import { cleanup, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, type Analyse, type Vue } from "../api";
import { setLanguage } from "../i18n";
import { VueEnsemble } from "./vue-ensemble";

vi.mock("../api", async (original) => ({
  ...(await original<typeof import("../api")>()),
  api: vi.fn(),
}));
vi.mock("../ui", async (original) => ({
  ...(await original<typeof import("../ui")>()),
  Orbit: () => null,
}));

const runs: Analyse[] = Array.from({ length: 5 }, (_, index) => ({
  id: String(index),
  titre: `Actual saved run ${index}`,
  mode: "graphe",
  statut: "complet",
  cree_le: "2026-09-27T00:00:00Z",
  maj_le: "2026-09-27T00:02:00Z",
  stade: "termine",
  duree_s: 5 + index,
  version: 1,
  options: {},
}));
const data: Vue = {
  total: 5,
  statuts: { complet: 5 },
  activite: [],
  sante: { ok: true, services: [], index: {}, modeles: [] },
  runbooks: 1,
  journal: [],
  version: "test",
};

beforeEach(() => {
  localStorage.clear();
  setLanguage("en");
  vi.clearAllMocks();
});
afterEach(() => cleanup());

function page(corpusFails = false) {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/vue-ensemble") return data as never;
    if (path === "/analyses?taille=100")
      return { elements: runs, total: 5, page: 1 } as never;
    if (path === "/runbooks?recherche=") {
      if (corpusFails) throw Error("Source metadata unavailable");
      return [
        {
          nom: "local.md",
          titre: "Operator-written procedure",
          octets: 1000,
          empreinte: "test",
        },
      ] as never;
    }
    throw Error("Unexpected request path");
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <VueEnsemble />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("loads one bounded sample for detailed charts while keeping the recent-run list at four", async () => {
  page();
  expect(await screen.findByText(/Latest 5 of 5 saved runs/)).toBeVisible();
  const recent = screen
    .getByRole("heading", { name: "Recent analyses" })
    .closest("section")!;
  expect(
    within(recent).getByRole("link", { name: /Actual saved run 3/ }),
  ).toBeVisible();
  expect(
    within(recent).queryByRole("link", { name: /Actual saved run 4/ }),
  ).not.toBeInTheDocument();
  const processing = screen.getByRole("region", {
    name: "Recorded processing time",
  });
  expect(
    within(processing).getByRole("link", { name: "Actual saved run 4" }),
  ).toBeVisible();
  expect(
    await screen.findByRole("link", { name: "Operator-written procedure" }),
  ).toHaveAttribute("href", "/runbooks/local.md");
  expect(
    vi.mocked(api).mock.calls.some(([path]) => path === "/analyses?taille=4"),
  ).toBe(false);
  for (const call of vi.mocked(api).mock.calls)
    expect(call[3]).toBeInstanceOf(AbortSignal);
});

it("keeps the overview and run charts available when only source metadata fails", async () => {
  page(true);
  expect(await screen.findByText(/Latest 5 of 5 saved runs/)).toBeVisible();
  const corpus = screen.getByRole("region", { name: "Knowledge footprint" });
  expect(
    await within(corpus).findByText(
      "Chart details are unavailable. No values are inferred.",
    ),
  ).toBeVisible();
  expect(within(corpus).queryByText("0 kB")).not.toBeInTheDocument();
  expect(
    screen.getByRole("region", { name: "Recorded processing time" }),
  ).toHaveTextContent("7 s");
  expect(
    screen.getByRole("heading", { name: "Your intelligence, in motion." }),
  ).toBeVisible();
});
