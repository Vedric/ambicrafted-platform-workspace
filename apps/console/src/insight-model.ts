import type { Sante } from "./api";

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
