import { describe, expect, it } from "vitest";
import {
  activityWindow,
  serviceSnapshot,
  stateGroups,
  processingSummary,
  workloadGroups,
  pendingReviewAge,
  corpusVolume,
} from "./insight-model";
import type { Analyse, Runbook } from "./api";

function run(overrides: Partial<Analyse> = {}): Analyse {
  return {
    id: "run",
    titre: "User-written title",
    mode: "graphe",
    statut: "complet",
    cree_le: "2026-09-25T00:00:00Z",
    maj_le: "2026-09-26T00:00:00Z",
    stade: "termine",
    duree_s: 12,
    version: 1,
    options: {},
    ...overrides,
  };
}

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

  it("summarizes only saved terminal process timings, never wall-clock or partial failure time", () => {
    const runs = [
      run({ duree_s: 10 }),
      run({ statut: "rejete_par_humain", duree_s: 30 }),
      ...[
        "en_cours",
        "en_attente_humain",
        "annule",
        "erreur",
        "interrompu",
        "budget_epuise",
      ].map((statut) => run({ statut, duree_s: 9000 })),
      ...[0, -2, NaN, Infinity].map((duree_s) => run({ duree_s })),
    ];
    const result = processingSummary(runs);
    expect(result.eligible).toHaveLength(2);
    expect(result.median).toBe(20);
    expect(result.maximum).toBe(30);
    expect(result.omitted).toBe(10);
    expect(result.eligible[0]).toBe(runs[0]);
    expect(processingSummary([]).median).toBeNull();
    expect(
      processingSummary([
        run({ duree_s: 5 }),
        run({ duree_s: 2 }),
        run({ duree_s: 100 }),
      ]).median,
    ).toBe(5);
  });

  it("uses explicit mode and operation, not words in a user title, and preserves unknown categories", () => {
    const runs = [
      run({ titre: "Backup the database" }),
      run({ mode: "operation", options: { operation: "sauvegarder" } }),
      run({ mode: "operation", options: { operation: "tester-restauration" } }),
      run({ mode: "operation", options: { operation: "future-operation" } }),
      run({ mode: "future-mode" }),
    ];
    const groups = workloadGroups(runs);
    expect(groups.find((group) => group.id === "analysis")?.count).toBe(1);
    expect(groups.find((group) => group.id === "sauvegarder")?.count).toBe(1);
    expect(
      groups.find((group) => group.id === "tester-restauration")?.count,
    ).toBe(1);
    expect(groups.find((group) => group.id === "other")?.count).toBe(2);
    expect(groups.reduce((sum, group) => sum + group.count, 0)).toBe(5);
  });

  it("groups review ages on exact boundaries and does not turn invalid/future dates into zero wait", () => {
    const now = Date.parse("2026-09-27T12:00:00Z");
    const ages = [0, 3599, 3600, 86399, 86400, 604799, 604800];
    const pending = ages.map((age) =>
      run({
        statut: "en_attente_humain",
        maj_le: new Date(now - age * 1000).toISOString(),
      }),
    );
    const result = pendingReviewAge(
      [
        ...pending,
        run({ statut: "en_attente_humain", maj_le: "broken" }),
        run({
          statut: "en_attente_humain",
          maj_le: new Date(now + 1).toISOString(),
        }),
        run({ statut: "en_cours" }),
      ],
      now,
    );
    expect(result.groups.map((group) => group.count)).toEqual([2, 2, 2, 1]);
    expect(result.total).toBe(9);
    expect(result.unavailable).toBe(2);
    expect(result.oldest).toBe(604800);
    expect(pendingReviewAge(pending, NaN).unavailable).toBe(7);
    expect(pendingReviewAge([], now).oldest).toBeNull();
  });

  it("conserves document bytes when showing the five largest and an other-documents group", () => {
    const docs: Runbook[] = Array.from({ length: 7 }, (_, index) => ({
      nom: `${index}.md`,
      titre: `Document ${index}`,
      empreinte: "hash",
      octets: index * 1000,
    }));
    const original = docs.map((doc) => doc.nom);
    const result = corpusVolume([
      ...docs,
      { ...docs[0], nom: "missing.md", octets: NaN },
    ]);
    expect(result.total).toBe(21000);
    expect(result.largest.map((doc) => doc.octets)).toEqual([
      6000, 5000, 4000, 3000, 2000,
    ]);
    expect(result.remainingBytes).toBe(1000);
    expect(result.remainingCount).toBe(2);
    expect(result.unavailable).toBe(1);
    expect(result.count).toBe(8);
    expect(docs.map((doc) => doc.nom)).toEqual(original);
    expect(corpusVolume([])).toMatchObject({
      total: 0,
      largest: [],
      remainingBytes: 0,
    });
  });
});
