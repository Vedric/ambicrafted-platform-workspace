import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import { Insights } from "./Insights";
import { setLanguage, t } from "./i18n";
import type { Vue, Analyse } from "./api";
import { MotionPreference } from "./motion-preferences";

const refreshed = Date.parse("2026-09-27T12:34:00Z");

function snapshot(): Vue {
  return {
    total: 105,
    statuts: {
      complet: 70,
      en_attente_humain: 20,
      erreur: 10,
      future_state: 5,
    },
    activite: Array.from({ length: 14 }, (_, index) => ({
      date: "2026-09-" + String(index + 14),
      total: index + 1,
    })),
    sante: {
      ok: false,
      services: [
        { id: "litellm", nom: "Gateway", ok: true, latence_ms: 8 },
        { id: "ollama", nom: "Local engine", ok: true, latence_ms: 40 },
        { id: "qdrant", nom: "Store", ok: false, latence_ms: 3000 },
      ],
      modeles: [],
      index: {},
    },
    runbooks: 0,
    journal: [],
    version: "test",
  };
}

function dashboard(data = snapshot(), updatedAt = refreshed) {
  return (
    <MemoryRouter>
      <Insights data={data} updatedAt={updatedAt} />
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  setLanguage("en");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function detailed(overrides: Partial<ComponentProps<typeof Insights>> = {}) {
  const base: Analyse = {
    id: "first",
    titre: "Customer-authored incident",
    mode: "graphe",
    statut: "complet",
    cree_le: "2026-09-25T00:00:00Z",
    maj_le: "2026-09-27T10:34:00Z",
    stade: "termine",
    duree_s: 10,
    version: 1,
    options: {},
  };
  return (
    <MemoryRouter>
      <Insights
        data={snapshot()}
        updatedAt={refreshed}
        runs={{
          data: {
            elements: [
              base,
              {
                ...base,
                id: "backup",
                mode: "operation",
                options: { operation: "sauvegarder" },
                duree_s: 30,
              },
              {
                ...base,
                id: "review",
                titre: "Unchanged operator draft",
                statut: "en_attente_humain",
                duree_s: 100,
              },
            ],
            total: 234,
            page: 1,
          },
          updatedAt: refreshed,
          failed: false,
          loading: false,
          retry: vi.fn(),
        }}
        runbooks={{
          data: [
            {
              nom: "database.md",
              titre: "Database rollback",
              octets: 2400,
              empreinte: "hash",
            },
          ],
          updatedAt: refreshed,
          failed: false,
          loading: false,
          retry: vi.fn(),
        }}
        {...overrides}
      />
    </MemoryRouter>
  );
}

describe("operational insights", () => {
  it("switches the UTC activity window without changing the all-time saved states", async () => {
    const data = snapshot();
    render(dashboard(data));
    const activity = screen.getByRole("region", { name: "Created runs" });
    const states = screen.getByRole("region", { name: "Run states" });
    expect(within(activity).getByText("105")).toBeVisible();
    expect(within(states).getByText("105")).toBeVisible();
    expect(screen.getByRole("button", { name: "14 days" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "7 days" }));
    expect(within(activity).getByText("77")).toBeVisible();
    expect(within(states).getByText("105")).toBeVisible();
    expect(screen.getByRole("button", { name: "7 days" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "14 days" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(data.activite).toHaveLength(14);
    expect(data.total).toBe(105);
  });

  it("provides inspectable dates, counts and a data table independent of SVG sight", async () => {
    render(dashboard());
    const slider = screen.getByRole("slider", { name: "Inspect a day" });
    expect(slider).toHaveAttribute("aria-valuetext", "Sep 27, 2026: 14");
    fireEvent.change(slider, { target: { value: "0" } });
    expect(slider).toHaveAttribute("aria-valuetext", "Sep 14, 2026: 1");
    await userEvent.click(screen.getByText("View chart data"));
    const table = screen.getByRole("table", { name: "Created runs" });
    expect(within(table).getAllByRole("row")).toHaveLength(15);
    expect(
      within(table).getByRole("row", { name: "Sep 14, 2026 1" }),
    ).toBeVisible();
    expect(
      within(table).getByRole("row", { name: "Sep 27, 2026 14" }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "7 days" }));
    expect(within(table).getAllByRole("row")).toHaveLength(8);
    expect(
      within(table).queryByRole("row", { name: "Sep 14, 2026 1" }),
    ).not.toBeInTheDocument();
    expect(slider).toHaveAttribute("aria-valuetext", "Sep 27, 2026: 14");
  });

  it("keeps human review distinct from completed records and retains unknown saved states", () => {
    render(dashboard());
    const states = screen.getByRole("region", { name: "Run states" });
    const row = (label: string) =>
      within(states).getByText(label).closest("li")!;
    expect(row("Human review")).toHaveTextContent("20");
    expect(row("Completed runs")).toHaveTextContent("70");
    expect(row("Other states")).toHaveTextContent("5");
    expect(within(states).getByText("105")).toBeVisible();
    expect(states).not.toHaveTextContent(/approval rate|success rate/i);
    expect(
      screen.getByText(
        /Saved runs include analyses and maintenance operations/,
      ),
    ).toBeVisible();
  });

  it("excludes failed probe timeouts from both latency bars and successful-probe counts", () => {
    render(dashboard());
    const services = screen.getByRole("region", { name: "Service response" });
    expect(
      within(services).getByText("2 of 3 service checks passed"),
    ).toBeVisible();
    const gateway = within(services).getByText("AI gateway").closest("li")!;
    const inference = within(services)
      .getByText("Local inference")
      .closest("li")!;
    const failed = within(services).getByText("Vector memory").closest("li")!;
    expect(
      gateway.querySelector<HTMLElement>(".probe-track i")!.style.width,
    ).toBe("20%");
    expect(
      inference.querySelector<HTMLElement>(".probe-track i")!.style.width,
    ).toBe("100%");
    expect(
      failed.querySelector<HTMLElement>(".probe-track i")!.style.width,
    ).toBe("0%");
    expect(within(failed).getByText("Probe failed")).toBeVisible();
    expect(services).not.toHaveTextContent("3000 ms");
    expect(services).toHaveTextContent(
      "Probe time is not inference latency or an availability SLO.",
    );
  });

  it("represents empty history and unavailable probes without fabricated values or broken geometry", () => {
    const data = snapshot();
    data.activite = [];
    data.statuts = {};
    data.total = 0;
    data.sante.services = [];
    const view = render(dashboard(data, 0));
    expect(screen.getByText("No activity recorded yet.")).toBeVisible();
    expect(screen.getByText("No saved states yet")).toBeVisible();
    expect(screen.getByText("No service probes available.")).toBeVisible();
    expect(screen.getByText("No current data")).toBeVisible();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(view.container.querySelector(".ring-arc")).toBeNull();
    expect(view.container.innerHTML).not.toMatch(/NaN|Infinity/);
  });

  it("bounds an active inspector when refreshed history becomes shorter or empty", () => {
    const data = snapshot();
    const view = render(dashboard(data));
    fireEvent.change(screen.getByRole("slider"), { target: { value: "11" } });
    view.rerender(dashboard({ ...data, activite: data.activite.slice(-1) }));
    expect(screen.getByRole("slider")).toHaveAttribute(
      "aria-valuetext",
      "Sep 27, 2026: 14",
    );
    expect(screen.getByRole("slider")).toHaveValue("0");
    view.rerender(dashboard({ ...data, activite: [] }));
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.getByText("No activity recorded yet.")).toBeVisible();
  });

  it("updates labels, accessible date values and links when the interface language changes", () => {
    render(dashboard());
    act(() => setLanguage("fr"));
    expect(
      screen.getByRole("region", { name: "Exécutions créées" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "7 jours" })).toBeVisible();
    expect(
      screen.getByRole("slider", { name: "Examiner une journée" }),
    ).toHaveAttribute("aria-valuetext", "27 sept. 2026: 14");
    expect(
      screen.getByRole("link", { name: "Explorer l’architecture" }),
    ).toHaveAttribute("href", "/architecture");
    expect(document.documentElement.lang).toBe("fr");
    act(() => setLanguage("en"));
    expect(screen.getByRole("region", { name: "Created runs" })).toBeVisible();
  });

  it("keeps gradient references unique when several dashboards share a document", () => {
    const view = render(
      <MemoryRouter>
        <Insights data={snapshot()} updatedAt={refreshed} />
        <Insights data={snapshot()} updatedAt={refreshed} />
      </MemoryRouter>,
    );
    const gradients = [...view.container.querySelectorAll("linearGradient")];
    expect(gradients).toHaveLength(2);
    expect(new Set(gradients.map((gradient) => gradient.id)).size).toBe(2);
    for (const gradient of gradients) {
      expect(
        gradient
          .closest("svg")!
          .querySelector(`path[fill="url(#${gradient.id})"]`),
      ).not.toBeNull();
    }
  });

  it("labels the bounded sample and exposes real process timings, explicit run types and review ages", async () => {
    render(detailed());
    expect(screen.getByText(/Latest 3 of 234 saved runs/)).toBeVisible();
    const duration = screen.getByRole("region", {
      name: "Recorded processing time",
    });
    expect(within(duration).getByText("20 s")).toBeVisible();
    expect(
      within(duration).getByRole("link", {
        name: "Customer-authored incident",
      }),
    ).toHaveAttribute("href", "/analyses/first");
    expect(duration).not.toHaveTextContent("100 s");
    expect(duration).toHaveTextContent(
      "Queue and human waiting time are excluded",
    );
    await userEvent.click(within(duration).getByText("Inspect numeric values"));
    const table = within(duration).getByRole("table", {
      name: "Recorded processing time",
    });
    expect(
      within(table).getByRole("row", {
        name: "Customer-authored incident 10 s",
      }),
    ).toBeVisible();
    const workload = screen.getByRole("region", {
      name: "Recent workload mix",
    });
    expect(
      within(
        within(workload).getByRole("list", { name: "Recent workload mix" }),
      )
        .getByText("Supervised analyses")
        .closest("li"),
    ).toHaveTextContent("2");
    const review = screen.getByRole("region", { name: "Pending review age" });
    expect(
      within(within(review).getByRole("list", { name: "Pending review age" }))
        .getByText("1–24 hours")
        .closest("li"),
    ).toHaveTextContent("1");
    expect(
      within(review).getByRole("link", { name: "Open approvals" }),
    ).toHaveAttribute("href", "/approbations");
    const knowledge = screen.getByRole("region", {
      name: "Knowledge footprint",
    });
    expect(
      within(knowledge).getByRole("link", { name: "Database rollback" }),
    ).toHaveAttribute("href", "/runbooks/database.md");
    expect(knowledge).toHaveTextContent("2.4 kB");
    expect(knowledge).toHaveTextContent(
      "Size does not measure quality, freshness",
    );
  });

  it("bounds the detailed view to 100 records and retains an explicit empty-review message", () => {
    const elements: Analyse[] = Array.from({ length: 120 }, (_, index) => ({
      id: String(index),
      titre: "Run " + index,
      mode: "graphe",
      statut: "complet",
      cree_le: "2026-09-27T00:00:00Z",
      maj_le: "2026-09-27T00:00:00Z",
      stade: "termine",
      duree_s: index + 1,
      version: 1,
      options: {},
    }));
    render(
      detailed({
        runs: {
          data: { elements, total: 400, page: 1 },
          failed: false,
          loading: false,
          retry: vi.fn(),
          updatedAt: refreshed,
        },
      }),
    );
    expect(screen.getByText(/Latest 100 of 400 saved runs/)).toBeVisible();
    const duration = screen.getByRole("region", {
      name: "Recorded processing time",
    });
    expect(within(duration).getByText("50.5 s")).toBeVisible();
    expect(within(duration).getAllByRole("link")).toHaveLength(6);
    expect(
      screen.getByText("No human review is pending in this sample."),
    ).toBeVisible();
    expect(elements).toHaveLength(120);
  });

  it("hides stale detailed values after a failed refresh while retaining independent service and corpus charts", async () => {
    const retry = vi.fn();
    render(
      detailed({
        runs: {
          data: { elements: [], total: 234, page: 1 },
          failed: true,
          loading: false,
          retry,
          updatedAt: refreshed,
        },
      }),
    );
    expect(
      screen.queryByText(/Latest .* of 234 saved runs/),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Chart details are unavailable. No values are inferred.",
      ),
    ).toHaveLength(3);
    await userEvent.click(
      screen.getAllByRole("button", { name: "Reload chart details" })[0],
    );
    expect(retry).toHaveBeenCalledOnce();
    expect(
      screen.getByRole("region", { name: "Service response" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Database rollback" }),
    ).toBeVisible();
  });

  it("distinguishes an empty data set from unavailable measurements without fabricated bar lengths", () => {
    const view = render(
      detailed({
        runs: {
          data: { elements: [], total: 0, page: 1 },
          failed: false,
          loading: false,
          retry: vi.fn(),
          updatedAt: refreshed,
        },
        runbooks: {
          data: [],
          failed: false,
          loading: false,
          retry: vi.fn(),
          updatedAt: refreshed,
        },
      }),
    );
    expect(screen.getByText("No saved runs to compare yet.")).toBeVisible();
    expect(screen.getByText("No runbook sources available yet.")).toBeVisible();
    expect(
      screen.getByText(
        "No completed or rejected runs with a recorded duration in this sample.",
      ),
    ).toBeVisible();
    expect(view.container.querySelector(".metric-fill")).toBeNull();
    expect(view.container.innerHTML).not.toMatch(/NaN|Infinity/);
  });

  it("localizes new chart controls and units without translating source titles or colliding with the Record action", () => {
    render(detailed());
    act(() => setLanguage("fr"));
    expect(
      screen.getByRole("region", { name: "Temps de traitement enregistré" }),
    ).toBeVisible();
    expect(
      screen.getByRole("region", {
        name: "Ancienneté des validations en attente",
      }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Customer-authored incident" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Database rollback" }),
    ).toBeVisible();
    expect(
      screen.getByRole("region", { name: "Volume des connaissances" }),
    ).toHaveTextContent(/2,4\s+ko/);
    expect(t("Record")).toBe("Enregistrer");
  });

  it("stops chart motion off-screen, in a hidden tab, on explicit pause and when OS preference changes", () => {
    const callbacks: IntersectionObserverCallback[] = [];
    const disconnects: ReturnType<typeof vi.fn>[] = [];
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        disconnect = vi.fn();
        constructor(callback: IntersectionObserverCallback) {
          callbacks.push(callback);
          disconnects.push(this.disconnect);
        }
        observe() {}
      },
    );
    let reduced = false;
    const mediaListeners = new Set<() => void>();
    vi.stubGlobal("matchMedia", () => ({
      matches: reduced,
      addEventListener: (_event: string, callback: () => void) =>
        mediaListeners.add(callback),
      removeEventListener: (_event: string, callback: () => void) =>
        mediaListeners.delete(callback),
    }));
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    const view = render(
      <MotionPreference.Provider value={true}>
        {detailed()}
      </MotionPreference.Provider>,
    );
    const panels = () => [
      ...view.container.querySelectorAll(".insight-metric-panel"),
    ];
    expect(
      panels().every(
        (panel) => panel.getAttribute("data-chart-motion") === "off",
      ),
    ).toBe(true);
    act(() =>
      callbacks.forEach((callback) =>
        callback(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          {} as IntersectionObserver,
        ),
      ),
    );
    expect(
      panels().every(
        (panel) => panel.getAttribute("data-chart-motion") === "on",
      ),
    ).toBe(true);
    hidden.mockReturnValue(true);
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(
      panels().every(
        (panel) => panel.getAttribute("data-chart-motion") === "off",
      ),
    ).toBe(true);
    hidden.mockReturnValue(false);
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      reduced = true;
      mediaListeners.forEach((listener) => listener());
    });
    expect(
      panels().every(
        (panel) => panel.getAttribute("data-chart-motion") === "off",
      ),
    ).toBe(true);
    act(() => {
      reduced = false;
      mediaListeners.forEach((listener) => listener());
    });
    view.rerender(
      <MotionPreference.Provider value={false}>
        {detailed()}
      </MotionPreference.Provider>,
    );
    expect(
      panels().every(
        (panel) => panel.getAttribute("data-chart-motion") === "off",
      ),
    ).toBe(true);
    view.unmount();
    expect(
      disconnects.every((disconnect) => disconnect.mock.calls.length === 1),
    ).toBe(true);
    expect(mediaListeners.size).toBe(0);
  });
});
