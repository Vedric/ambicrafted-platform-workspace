import { describe, expect, it } from "vitest";
import { activityWindow, serviceSnapshot, stateGroups } from "./insight-model";

describe("operational chart data", () => {
  it("keeps human review separate from execution and preserves every saved status", () => {
    const groups = stateGroups({
      en_file: 2,
      en_cours: 1,
      decision: 1,
      en_attente_humain: 4,
      complet: 6,
      rejete_par_humain: 3,
      erreur: 2,
      budget_epuise: 1,
      annule: 1,
      interrompu: 1,
      future_state: 2,
    });
    expect(groups.find((group) => group.id === "active")?.count).toBe(4);
    expect(groups.find((group) => group.id === "review")?.count).toBe(4);
    expect(groups.find((group) => group.id === "stopped")?.count).toBe(3);
    expect(groups.find((group) => group.id === "other")?.count).toBe(2);
    expect(groups.reduce((sum, group) => sum + group.count, 0)).toBe(24);
  });
  it("represents empty and invalid counts without invented activity", () => {
    expect(stateGroups({}).every((group) => group.count === 0)).toBe(true);
    expect(
      stateGroups({ en_cours: -1, complet: NaN, erreur: Infinity }).every(
        (group) => group.count === 0,
      ),
    ).toBe(true);
  });
  it("changes only the activity window without mutating the source", () => {
    const days = Array.from({ length: 14 }, (_, index) => ({
      date: "2026-09-" + String(index + 1).padStart(2, "0"),
      total: index,
    }));
    expect(activityWindow(days, 7)).toEqual(days.slice(7));
    expect(activityWindow(days, 14)).toEqual(days);
    expect(days).toHaveLength(14);
    expect(activityWindow([], 7)).toEqual([]);
  });
  it("does not treat a failed probe timeout as successful response latency", () => {
    const snapshot = serviceSnapshot([
      { id: "fast", nom: "Fast", ok: true, latence_ms: 8 },
      { id: "down", nom: "Down", ok: false, latence_ms: 3000 },
      { id: "slow", nom: "Slow", ok: true, latence_ms: 45 },
    ]);
    expect(snapshot).toEqual({ responding: 2, total: 3, maxLatency: 45 });
    expect(serviceSnapshot([])).toEqual({
      responding: 0,
      total: 0,
      maxLatency: 1,
    });
  });
});
