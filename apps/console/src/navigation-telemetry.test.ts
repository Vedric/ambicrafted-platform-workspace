import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Metric } from "web-vitals";
import {
  creerTelemetrieNavigation,
  routeMesuree,
} from "./navigation-telemetry";
import { definirCsrf, envoyerMesuresNavigation } from "./api";

let state: DocumentVisibilityState;
const cleanups: (() => void)[] = [];
beforeEach(() => {
  state = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => state);
  vi.spyOn(document, "hidden", "get").mockImplementation(
    () => state === "hidden",
  );
});
afterEach(() => {
  cleanups.splice(0).forEach((f) => f());
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  definirCsrf(null);
});
function fixture() {
  const callbacks: ((metric: Metric) => void)[] = [];
  const register = vi.fn((callback: (metric: Metric) => void) => {
    callbacks.push(callback);
  });
  const loader = vi
    .fn()
    .mockResolvedValue({ onLCP: register, onINP: register, onCLS: register });
  const send = vi.fn().mockResolvedValue(undefined);
  const collector = creerTelemetrieNavigation(loader, send);
  const cleanup = collector.monter();
  cleanups.push(cleanup);
  return {
    collector,
    loader,
    send,
    register,
    cleanup,
    emit: (name: string, value: number) =>
      callbacks[0]?.({
        name,
        value,
        entries: [{ target: "PRIVATE" }],
        navigationURL: "https://private/client",
        id: "PRIVATE",
      } as unknown as Metric),
  };
}
async function hide() {
  state = "hidden";
  document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
  await Promise.resolve();
}

describe("bounded first-visible-period RUM", () => {
  it("excludes initially anonymous documents even after login and never registers before authentication", async () => {
    const f = fixture();
    f.collector.session(undefined, "/welcome");
    expect(f.loader).not.toHaveBeenCalled();
    f.collector.session(false, "/welcome");
    f.collector.session(true, "/");
    await hide();
    expect(f.loader).not.toHaveBeenCalled();
    expect(f.send).not.toHaveBeenCalled();
  });
  it("excludes background-loaded documents", async () => {
    state = "hidden";
    const f = fixture();
    f.collector.session(true, "/");
    state = "visible";
    f.collector.session(true, "/");
    await hide();
    expect(f.loader).not.toHaveBeenCalled();
  });
  it("sends only the latest value of each metric once, with a frozen allowlisted route", async () => {
    const f = fixture();
    f.collector.session(true, "/analyses/private-id?secret=PRIVATE");
    await Promise.resolve();
    f.emit("CLS", 0.03);
    f.emit("CLS", 0.08);
    f.emit("INP", 140);
    f.emit("LCP", 1200);
    f.collector.session(true, "/assistant");
    // A capture-phase SDK final report must be included before our bubble flush.
    const final = () => f.emit("INP", 170);
    window.addEventListener("visibilitychange", final, {
      capture: true,
      once: true,
    });
    await hide();
    expect(f.send).toHaveBeenCalledExactlyOnceWith([
      { metric: "CLS", route: "analyses", value: 0.08 },
      { metric: "INP", route: "analyses", value: 170 },
      { metric: "LCP", route: "analyses", value: 1200 },
    ]);
    state = "visible";
    window.dispatchEvent(
      new PageTransitionEvent("pageshow", { persisted: true }),
    );
    f.emit("CLS", 0.9);
    await hide();
    expect(f.send).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(f.send.mock.calls)).not.toContain("PRIVATE");
  });
  it("drops invalid values and unsupported metrics without inventing zero observations", async () => {
    const f = fixture();
    f.collector.session(true, "/");
    await Promise.resolve();
    for (const value of [NaN, Infinity, -1, 300001]) f.emit("LCP", value);
    f.emit("CLS", 101);
    f.emit("TTFB", 5);
    await hide();
    expect(f.send).not.toHaveBeenCalled();
  });
  it("keeps a single registration across StrictMode-style cleanup/remount", async () => {
    const f = fixture();
    f.collector.session(true, "/");
    f.cleanup();
    cleanups.pop();
    cleanups.push(f.collector.monter());
    f.collector.session(true, "/assistant");
    await Promise.resolve();
    expect(f.loader).toHaveBeenCalledTimes(1);
    expect(f.register).toHaveBeenCalledTimes(3);
    f.emit("LCP", 900);
    await hide();
    expect(f.send).toHaveBeenCalledTimes(1);
  });
  it("makes unmounted callbacks inert and unregisters its own listener", async () => {
    const f = fixture();
    f.collector.session(true, "/");
    await Promise.resolve();
    f.emit("LCP", 900);
    f.cleanup();
    cleanups.pop();
    f.emit("INP", 100);
    await hide();
    expect(f.send).not.toHaveBeenCalled();
  });
  it("drops pending observations on logout without retrying after login", async () => {
    const f = fixture();
    f.collector.session(true, "/");
    await Promise.resolve();
    f.emit("LCP", 900);
    f.collector.session(false, "/");
    f.collector.session(true, "/");
    await hide();
    expect(f.send).not.toHaveBeenCalled();
    expect(f.loader).toHaveBeenCalledTimes(1);
  });
  it("ignores late SDK loading after first hide", async () => {
    let resolve!: (v: typeof sdk) => void;
    const sdk = { onLCP: vi.fn(), onINP: vi.fn(), onCLS: vi.fn() };
    const f = creerTelemetrieNavigation(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
      vi.fn(),
    );
    cleanups.push(f.monter());
    f.session(true, "/");
    await hide();
    resolve(sdk);
    await Promise.resolve();
    expect(sdk.onLCP).not.toHaveBeenCalled();
  });
  it.each([
    ["/", "workspace"],
    ["/memoire", "memory"],
    ["/runbooks/private.md", "knowledge"],
    ["/recherche", "knowledge"],
    ["/observabilite", "observability"],
    ["/parametres", "settings"],
    ["/architecture", "architecture"],
    ["/guide", "guide"],
    ["/private-client", "other"],
    ["/constructor", "other"],
  ])("maps %s to a finite label %s", (path, expected) =>
    expect(routeMesuree(path)).toBe(expected),
  );
});

describe("authenticated telemetry transport", () => {
  it("sends same-origin JSON with CSRF and keepalive, without reading the response", async () => {
    const json = vi.fn();
    const fetch = vi.fn().mockResolvedValue({ status: 429, json });
    vi.stubGlobal("fetch", fetch);
    definirCsrf("synthetic-csrf");
    const samples = [
      { metric: "CLS" as const, route: "workspace" as const, value: 0 },
    ];
    await envoyerMesuresNavigation(samples);
    expect(fetch).toHaveBeenCalledExactlyOnceWith(
      "/api/telemetrie/navigation",
      {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": "synthetic-csrf",
        },
        body: JSON.stringify({ samples }),
      },
    );
    expect(json).not.toHaveBeenCalled();
  });
  it("skips missing authentication and oversized batches, and swallows offline failure without retries", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetch);
    const sample = {
      metric: "CLS" as const,
      route: "workspace" as const,
      value: 0,
    };
    await envoyerMesuresNavigation([sample]);
    definirCsrf("synthetic-csrf");
    await envoyerMesuresNavigation(Array(4).fill(sample));
    await envoyerMesuresNavigation([]);
    expect(fetch).not.toHaveBeenCalled();
    await envoyerMesuresNavigation([sample]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
