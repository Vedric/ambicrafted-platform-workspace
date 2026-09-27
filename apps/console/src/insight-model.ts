import type { Analyse, Runbook, Sante } from "./api";

export type StateGroup = {
  id: string;
  label:
    | "In progress"
    | "Human review"
    | "Completed runs"
    | "Rejected runs"
    | "Stopped"
    | "Failed runs"
    | "Other states";
  count: number;
  color: string;
};

function count(value: number | undefined) {
  return Number.isFinite(value) && value! > 0 ? Math.floor(value!) : 0;
}

export function stateGroups(states: Record<string, number>): StateGroup[] {
  const definitions = [
    ["active", "In progress", ["en_file", "en_cours", "decision"], "cyan"],
    ["review", "Human review", ["en_attente_humain"], "amber"],
    ["complete", "Completed runs", ["complet"], "green"],
    ["rejected", "Rejected runs", ["rejete_par_humain"], "violet"],
    ["stopped", "Stopped", ["annule", "interrompu", "budget_epuise"], "slate"],
    ["failed", "Failed runs", ["erreur"], "red"],
  ] as const;
  const known = new Set<string>(
    definitions.flatMap((definition) => [...definition[2]]),
  );
  const groups: StateGroup[] = definitions.map(
    ([id, label, statuses, color]) => ({
      id,
      label,
      color,
      count: statuses.reduce((sum, key) => sum + count(states[key]), 0),
    }),
  );
  const other = Object.entries(states)
    .filter(([key]) => !known.has(key))
    .reduce((sum, [, value]) => sum + count(value), 0);
  if (other)
    groups.push({
      id: "other",
      label: "Other states",
      color: "slate",
      count: other,
    });
  return groups;
}

export function activityWindow(
  activity: { date: string; total: number }[],
  days: 7 | 14,
) {
  return activity
    .slice(-days)
    .map((item) => ({ date: item.date, total: count(item.total) }));
}

export function serviceSnapshot(services: Sante["services"]) {
  return {
    responding: services.filter((service) => service.ok).length,
    total: services.length,
    // Failed probes describe failures/timeouts, not successful response latency.
    maxLatency: Math.max(
      1,
      ...services
        .filter((service) => service.ok)
        .map((service) => count(service.latence_ms)),
    ),
  };
}

/** This is a bounded creation-ordered sample, not an all-history aggregate. */
export const INSIGHT_RUN_LIMIT = 100;

export function processingSummary(runs: Analyse[]) {
  // The worker saves accumulated subprocess time on normal completion/rejection.
  // Cancellations can retain an earlier duration; error paths can overwrite it.
  // Do not turn those incomplete observations into processing-time statistics.
  const eligible = runs.filter(
    (run) =>
      ["complet", "rejete_par_humain"].includes(run.statut) &&
      Number.isFinite(run.duree_s) &&
      run.duree_s > 0,
  );
  const times = eligible.map((run) => run.duree_s).sort((a, b) => a - b);
  const middle = Math.floor(times.length / 2);
  return {
    eligible,
    median: times.length
      ? times.length % 2
        ? times[middle]
        : (times[middle - 1] + times[middle]) / 2
      : null,
    maximum: times.at(-1) ?? null,
    omitted: runs.length - eligible.length,
  };
}

export function workloadGroups(runs: Analyse[]) {
  const groups = [
    { id: "analysis", label: "Supervised analyses", color: "cyan", count: 0 },
    {
      id: "verifier",
      label: "Platform verification",
      color: "violet",
      count: 0,
    },
    { id: "indexer", label: "Runbook reindexing", color: "green", count: 0 },
    { id: "sauvegarder", label: "Platform backup", color: "amber", count: 0 },
    {
      id: "tester-restauration",
      label: "Backup restoration test",
      color: "blue",
      count: 0,
    },
    { id: "other", label: "Other run types", color: "slate", count: 0 },
  ] as const;
  const result = groups.map((group) => ({ ...group, count: 0 }));
  for (const run of runs) {
    const key =
      run.mode === "graphe"
        ? "analysis"
        : run.mode === "operation"
          ? run.options.operation
          : "other";
    const group = result.find((item) => item.id === key) ?? result.at(-1)!;
    group.count++;
  }
  return result;
}

export function pendingReviewAge(runs: Analyse[], now: number) {
  const buckets = [
    { id: "hour", label: "Under 1 hour", upper: 3600, color: "cyan", count: 0 },
    { id: "day", label: "1–24 hours", upper: 86400, color: "blue", count: 0 },
    { id: "week", label: "1–7 days", upper: 604800, color: "amber", count: 0 },
    {
      id: "older",
      label: "7 days or more",
      upper: Infinity,
      color: "violet",
      count: 0,
    },
  ] as const;
  const groups = buckets.map((bucket) => ({ ...bucket, count: 0 }));
  const pending = runs.filter((run) => run.statut === "en_attente_humain");
  let unavailable = 0;
  let oldest: number | null = null;
  for (const run of pending) {
    const timestamp = Date.parse(run.maj_le);
    if (
      !Number.isFinite(timestamp) ||
      !Number.isFinite(now) ||
      timestamp > now
    ) {
      unavailable++;
      continue;
    }
    const seconds = (now - timestamp) / 1000;
    groups.find((group) => seconds < group.upper)!.count++;
    oldest = Math.max(oldest ?? 0, seconds);
  }
  return { groups, total: pending.length, unavailable, oldest };
}

export function corpusVolume(runbooks: Runbook[]) {
  const valid = runbooks.filter(
    (runbook) => Number.isFinite(runbook.octets) && runbook.octets >= 0,
  );
  const sorted = [...valid].sort(
    (a, b) => b.octets - a.octets || a.nom.localeCompare(b.nom),
  );
  const total = valid.reduce((sum, runbook) => sum + runbook.octets, 0);
  return {
    total,
    largest: sorted.slice(0, 5),
    remainingBytes: sorted
      .slice(5)
      .reduce((sum, runbook) => sum + runbook.octets, 0),
    remainingCount: Math.max(0, sorted.length - 5),
    unavailable: runbooks.length - valid.length,
    count: runbooks.length,
  };
}
