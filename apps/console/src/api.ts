export class ErreurAPI extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
let csrf = "";
export function definirCsrf(valeur: string | null) {
  csrf = valeur || "";
}
export async function api<T = unknown>(
  chemin: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/api" + chemin, {
    method,
    credentials: "same-origin",
    signal,
    headers:
      method === "GET"
        ? {}
        : { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: method === "GET" ? undefined : JSON.stringify(body ?? {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !chemin.startsWith("/auth"))
      window.dispatchEvent(new Event("session-expiree"));
    throw new ErreurAPI(
      response.status,
      typeof data.detail === "string"
        ? data.detail
        : "Requête refusée. Vérifier les données saisies.",
    );
  }
  return data as T;
}

export type Session = {
  connecte: boolean;
  mot_de_passe: boolean;
  csrf: string | null;
};
export type Diagnostic = {
  cause_probable: string;
  confiance: string;
  runbook_source: string | null;
  actions_proposees: string[];
  elements_manquants: string[];
};
export type Rapport = {
  statut: string;
  diagnostic?: Diagnostic;
  classification?: { connue: boolean; urgence: number; justification: string };
  message?: string;
  outils_appeles?: string[];
  budget?: Record<string, number>;
  actions_ecartees_sans_source?: string[];
  injections_signalees?: string[];
  trace_id?: string;
};
export type Analyse = {
  id: string;
  titre: string;
  mode: string;
  statut: string;
  cree_le: string;
  maj_le: string;
  stade: string;
  duree_s: number;
  version: number;
  urgence?: number;
  rapport?: Rapport;
  evenements?: { id: number; date: string; stade: string }[];
  options: { operation?: string };
};
export type Liste = { elements: Analyse[]; total: number; page: number };
export type Runbook = {
  nom: string;
  titre: string;
  empreinte: string;
  extrait?: string;
  contenu?: string;
  octets: number;
};
export type Sante = {
  ok: boolean;
  services: {
    id: string;
    nom: string;
    ok: boolean;
    latence_ms: number;
    lien?: string;
  }[];
  modeles: { nom: string; taille: number }[];
  index: { points?: number; statut?: string };
};
export type Journal = {
  id: number;
  date: string;
  action: string;
  reference?: string;
  acteur: string;
};
export type Vue = {
  total: number;
  statuts: Record<string, number>;
  activite: { date: string; total: number }[];
  sante: Sante;
  runbooks: number;
  journal: Journal[];
  version: string;
};

export const statuts: Record<string, string> = {
  en_file: "En file",
  en_cours: "En cours",
  en_attente_humain: "À valider",
  complet: "Terminé",
  rejete_par_humain: "Refusé",
  budget_epuise: "Budget atteint",
  erreur: "Erreur",
  interrompu: "Interrompu",
  annule: "Annulé",
  decision: "Validation en cours",
};
export const actifs = new Set(["en_file", "en_cours", "decision"]);
export const date = (valeur: string) =>
  Number.isNaN(new Date(valeur).getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(valeur));
export function apercu(rapport?: Rapport): Diagnostic | undefined {
  const valide = (d: unknown): d is Diagnostic => {
    if (!d || typeof d !== "object" || Array.isArray(d)) return false;
    const v = d as Record<string, unknown>;
    return (
      typeof v.cause_probable === "string" &&
      ["haute", "moyenne", "faible"].includes(v.confiance as string) &&
      (v.runbook_source === null || typeof v.runbook_source === "string") &&
      Array.isArray(v.actions_proposees) &&
      v.actions_proposees.every((a) => typeof a === "string") &&
      Array.isArray(v.elements_manquants) &&
      v.elements_manquants.every((a) => typeof a === "string")
    );
  };
  if (valide(rapport?.diagnostic)) return rapport.diagnostic;
  if (rapport?.statut === "en_attente_humain" && rapport.message) {
    try {
      const d: unknown = JSON.parse(rapport.message);
      return valide(d) ? d : undefined;
    } catch {
      return undefined;
    }
  }
}

export async function audioLocal(
  texte: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const r = await fetch("/api/voix/parler", {
    method: "POST",
    credentials: "same-origin",
    signal,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify({ texte }),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ErreurAPI(
      r.status,
      typeof d.detail === "string" ? d.detail : "Synthèse vocale indisponible.",
    );
  }
  return r.blob();
}
