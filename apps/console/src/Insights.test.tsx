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
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Insights } from "./Insights";
import { setLanguage } from "./i18n";
import type { Vue } from "./api";

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
afterEach(() => cleanup());

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
});
