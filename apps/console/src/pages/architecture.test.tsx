import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Sante } from "../api";
import { setLanguage } from "../i18n";
import { MotionPreference } from "../motion-preferences";
import { Architecture } from "./architecture";

vi.mock("../api", async (original) => ({
  ...(await original<typeof import("../api")>()),
  api: vi.fn(),
}));

const successfulHealth: Sante = {
  ok: true,
  services: [
    "litellm",
    "ollama",
    "qdrant",
    "prometheus",
    "tempo",
    "grafana",
  ].map((id, index) => ({
    id,
    nom: `Server-generated name ${index}`,
    ok: true,
    latence_ms: 10 + index,
  })),
  modeles: [],
  index: {},
};
let client: QueryClient;
let media: MediaQueryList;
let visibility: ReturnType<typeof vi.spyOn>;
let observers: {
  callback: IntersectionObserverCallback;
  disconnect: ReturnType<typeof vi.fn>;
  observe: ReturnType<typeof vi.fn>;
}[];

beforeEach(() => {
  setLanguage("en");
  vi.mocked(api).mockReset().mockResolvedValue(successfulHealth);
  client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
    },
  });
  visibility = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  const events = new EventTarget();
  media = {
    matches: false,
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    dispatchEvent: events.dispatchEvent.bind(events),
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => media),
  );
  observers = [];
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe = vi.fn();
      disconnect = vi.fn();
      constructor(callback: IntersectionObserverCallback) {
        observers.push({
          callback,
          observe: this.observe,
          disconnect: this.disconnect,
        });
      }
    },
  );
});
afterEach(() => {
  cleanup();
  client.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  setLanguage("en");
});

function tree(enabled = true) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MotionPreference.Provider value={enabled}>
          <Architecture />
        </MotionPreference.Provider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}
function diagram() {
  return screen.getByRole("group", { name: "Component map" });
}
function details() {
  return screen.getByRole("complementary", { name: "Component details" });
}
function measured() {
  return screen.getByRole("region", { name: "Measured availability" });
}
function visible(value: boolean) {
  act(() => {
    const observer = observers.at(-1)!;
    observer.callback(
      [{ isIntersecting: value } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
  });
}

describe("architecture: explained flows and measured checks", () => {
  it("keeps the guide readable while initial availability is unknown", () => {
    vi.mocked(api).mockReturnValue(new Promise(() => {}));
    render(tree());
    expect(
      screen.getByRole("heading", {
        name: "From an alert to a reviewed proposal",
      }),
    ).toBeVisible();
    expect(within(measured()).getAllByText("Not measured")).toHaveLength(6);
    expect(
      within(measured()).queryByText("Health check passed"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Checking services…" }),
    ).toBeDisabled();
    expect(screen.getByText("No successful check yet")).toBeVisible();
    expect(
      screen.getByText(/Arrows explain dependencies, not live traffic/),
    ).toBeVisible();
    expect(api).toHaveBeenCalledWith(
      "/sante",
      "GET",
      undefined,
      expect.any(AbortSignal),
    );
  });

  it("maps strict probe IDs and booleans without inferring absent services from overall health", async () => {
    vi.mocked(api).mockResolvedValue({
      ...successfulHealth,
      ok: true,
      services: [
        {
          id: "litellm",
          nom: "Untrusted translated name",
          ok: true,
          latence_ms: 13.4,
        },
        { id: "qdrant", nom: "Whatever", ok: false, latence_ms: 6000 },
        { id: "tempo", ok: "true", latence_ms: 1 },
        { id: "grafana", ok: true, latence_ms: -10 },
        { id: "postgres", ok: true, latence_ms: 1 },
      ],
    });
    render(tree());
    await screen.findByRole("button", { name: "Check services" });
    const health = within(measured());
    expect(health.getAllByText("Health check passed")).toHaveLength(2);
    expect(health.getAllByText("Health check failed")).toHaveLength(1);
    expect(health.getAllByText("Not measured")).toHaveLength(3);
    expect(health.getByText("Probe duration: 13 ms")).toBeVisible();
    expect(
      health.queryByText(/6000|-10|Untrusted translated name|Whatever/),
    ).not.toBeInTheDocument();
    expect(within(details()).getByText("No direct health probe")).toBeVisible();
  });

  it.each([null, {}, "invalid"])(
    "treats malformed service lists as unmeasured (%j)",
    async (services) => {
      vi.mocked(api).mockResolvedValue({ ...successfulHealth, services });
      render(tree());
      await screen.findByRole("button", { name: "Check services" });
      expect(within(measured()).getAllByText("Not measured")).toHaveLength(6);
      expect(
        within(diagram()).getByRole("button", { name: /Supervised agents/ }),
      ).toBeInTheDocument();
    },
  );

  it("marks cached probes unknown after refresh failure, preserves last success time and allows recovery", async () => {
    const user = userEvent.setup();
    vi.mocked(api)
      .mockResolvedValueOnce(successfulHealth)
      .mockRejectedValueOnce(new TypeError("Private upstream failure"))
      .mockResolvedValueOnce(successfulHealth);
    const { container } = render(tree());
    await waitFor(() =>
      expect(
        within(measured()).getAllByText("Health check passed"),
      ).toHaveLength(6),
    );
    const lastCheck = container.querySelector("time")!.getAttribute("datetime");
    await user.click(screen.getByRole("button", { name: "Check services" }));
    await screen.findByRole("status");
    expect(within(measured()).getAllByText("Not measured")).toHaveLength(6);
    expect(
      within(measured()).queryByText("Health check passed"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Private upstream failure"),
    ).not.toBeInTheDocument();
    expect(container.querySelector("time")).toHaveAttribute(
      "datetime",
      lastCheck,
    );
    expect(
      within(diagram()).getByRole("button", { name: /Operator/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check services" }));
    await waitFor(() =>
      expect(
        within(measured()).getAllByText("Health check passed"),
      ).toHaveLength(6),
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("supports keyboard component selection and exposes the real destination and approval boundary", async () => {
    const user = userEvent.setup();
    render(tree());
    const review = within(diagram()).getByRole("button", {
      name: /Human review/,
    });
    review.focus();
    await user.keyboard("{Enter}");
    expect(review).toHaveFocus();
    expect(review).toHaveAttribute("aria-pressed", "true");
    expect(
      within(details()).getByRole("heading", { name: "Human review" }),
    ).toBeInTheDocument();
    expect(
      within(details()).getByText(
        /Approving a proposal does not run remediation/,
      ),
    ).toBeVisible();
    expect(within(details()).getByRole("link")).toHaveAttribute(
      "href",
      "/approbations",
    );
    expect(review).toHaveAttribute("aria-controls", details().id);
  });

  it("changes all four journeys through native keyboard-operable controls", async () => {
    const user = userEvent.setup();
    render(tree());
    const choices = within(
      screen.getByRole("group", { name: "Architecture journeys" }),
    );
    for (const [label, heading] of [
      ["Voice", "From your voice to a local reply"],
      ["Knowledge", "From reviewed procedures to grounded retrieval"],
      ["Telemetry", "From local signals to operational visibility"],
      ["Investigation", "From an alert to a reviewed proposal"],
    ]) {
      const button = choices.getByRole("button", { name: label });
      button.focus();
      await user.keyboard(" ");
      expect(button).toHaveAttribute("aria-pressed", "true");
      expect(
        screen.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
      expect(
        within(diagram()).getAllByRole("button", { pressed: true }),
      ).toHaveLength(1);
    }
    expect(api).toHaveBeenCalledTimes(1);
  });

  it("does not assign voice or PostgreSQL availability from the six successful endpoint probes", async () => {
    const user = userEvent.setup();
    render(tree());
    await waitFor(() =>
      expect(
        within(measured()).getAllByText("Health check passed"),
      ).toHaveLength(6),
    );
    await user.click(screen.getByRole("button", { name: "Voice" }));
    await user.click(
      within(diagram()).getByRole("button", { name: /Local speech/ }),
    );
    expect(
      within(details()).getByText("No direct health probe"),
    ).toBeInTheDocument();
    expect(
      within(details()).getByText(/do not measure transcription accuracy/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Telemetry" }));
    await user.click(
      within(diagram()).getByRole("button", { name: /Gateway database/ }),
    );
    expect(
      within(details()).getByText("No direct health probe"),
    ).toBeInTheDocument();
    expect(
      within(details()).getByText(
        /Gateway availability does not prove database readiness/,
      ),
    ).toBeInTheDocument();
  });

  it("preserves mobile component access, source backup guidance and deployment isolation limits", async () => {
    const user = userEvent.setup();
    render(tree());
    await user.click(screen.getByRole("button", { name: "Knowledge" }));
    const mobile = screen.getByRole("group", { name: "Component list" });
    await user.click(
      within(mobile).getByRole("button", { name: /Reviewed runbooks/ }),
    );
    expect(
      within(details()).getByText(/snapshots do not back up source Markdown/),
    ).toBeInTheDocument();
    expect(within(details()).getByRole("link")).toHaveAttribute(
      "href",
      "/runbooks",
    );
    expect(
      screen.getByText(/this workspace has no tenant isolation/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/similarity is not a confidence score/),
    ).toBeInTheDocument();
  });

  it("changes every journey and selected component to French without changing service or route identifiers", async () => {
    const user = userEvent.setup();
    render(tree());
    await user.click(screen.getByRole("button", { name: "Voice" }));
    await user.click(
      within(diagram()).getByRole("button", { name: /AURA dialogue/ }),
    );
    act(() => setLanguage("fr"));
    expect(
      screen.getByRole("heading", {
        name: "De votre voix à une réponse locale",
      }),
    ).toBeInTheDocument();
    const inspector = screen.getByRole("complementary", {
      name: "Détails du composant",
    });
    expect(
      within(inspector).getByRole("heading", { name: "Dialogue AURA" }),
    ).toBeInTheDocument();
    expect(
      within(inspector).getByText(/Le dialogue n’accède à aucun outil/),
    ).toBeInTheDocument();
    expect(within(inspector).getByRole("link")).toHaveAttribute(
      "href",
      "/assistant",
    );
    for (const [label, heading] of [
      ["Connaissances", "Des procédures relues à une recherche documentée"],
      ["Télémétrie", "Des signaux locaux à la visibilité opérationnelle"],
      ["Investigation", "D’une alerte à une proposition validée"],
    ]) {
      await user.click(screen.getByRole("button", { name: label }));
      expect(
        screen.getByRole("heading", { name: heading }),
      ).toBeInTheDocument();
    }
    const health = screen.getByRole("region", {
      name: "Disponibilité mesurée",
    });
    expect(within(health).getAllByText("Sonde de santé réussie")).toHaveLength(
      6,
    );
    expect(screen.queryByText(/Server-generated name/)).not.toBeInTheDocument();
    expect(api).toHaveBeenCalledTimes(1);
  });
});

describe("architecture motion and lifecycle", () => {
  it("animates only while visible, foregrounded and permitted by user and OS", () => {
    vi.mocked(api).mockReturnValue(new Promise(() => {}));
    const view = render(tree());
    expect(diagram()).toHaveAttribute("data-motion", "off");
    visible(true);
    expect(diagram()).toHaveAttribute("data-motion", "on");
    act(() => {
      visibility.mockReturnValue(true);
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(diagram()).toHaveAttribute("data-motion", "off");
    act(() => {
      visibility.mockReturnValue(false);
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(diagram()).toHaveAttribute("data-motion", "on");
    act(() => {
      Object.defineProperty(media, "matches", {
        configurable: true,
        value: true,
      });
      media.dispatchEvent(new Event("change"));
    });
    expect(diagram()).toHaveAttribute("data-motion", "off");
    act(() => {
      Object.defineProperty(media, "matches", {
        configurable: true,
        value: false,
      });
      media.dispatchEvent(new Event("change"));
    });
    expect(diagram()).toHaveAttribute("data-motion", "on");
    view.rerender(tree(false));
    expect(diagram()).toHaveAttribute("data-motion", "off");
    view.rerender(tree(true));
    visible(false);
    expect(diagram()).toHaveAttribute("data-motion", "off");
  });

  it("keeps a static usable diagram when IntersectionObserver is unavailable", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    render(tree());
    expect(diagram()).toHaveAttribute("data-motion", "off");
    fireEvent.click(
      within(diagram()).getByRole("button", { name: /Human review/ }),
    );
    expect(
      within(details()).getByRole("heading", { name: "Human review" }),
    ).toBeInTheDocument();
  });

  it("disconnects observers and visibility listeners under StrictMode and aborts the pending probe on unmount", () => {
    vi.mocked(api).mockReturnValue(new Promise(() => {}));
    const remove = vi.spyOn(document, "removeEventListener");
    const { unmount } = render(<StrictMode>{tree()}</StrictMode>);
    const signals = vi
      .mocked(api)
      .mock.calls.map((call) => call[3] as AbortSignal);
    expect(signals.length).toBeGreaterThan(0);
    unmount();
    expect(signals.every((signal) => signal.aborted)).toBe(true);
    expect(observers.length).toBeGreaterThan(0);
    expect(
      observers.every(
        (observer) => observer.disconnect.mock.calls.length === 1,
      ),
    ).toBe(true);
    expect(
      remove.mock.calls.some(([name]) => name === "visibilitychange"),
    ).toBe(true);
  });

  it("renders a static server snapshot without browser globals or a fabricated health result", () => {
    vi.stubGlobal("document", undefined);
    vi.stubGlobal("window", undefined);
    let html: string;
    try {
      html = renderToString(tree());
    } finally {
      vi.unstubAllGlobals();
    }
    expect(html!).toContain("From an alert to a reviewed proposal");
    expect(html!).toContain('data-motion="off"');
    expect(html!).not.toContain("Health check passed");
    expect(api).not.toHaveBeenCalled();
  });
});
