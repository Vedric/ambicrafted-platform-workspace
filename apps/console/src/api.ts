export class ErreurAPI extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
let csrf = "";
// Presentation labels are separate from the stable French API identifiers.
const messages: Record<string, string> = {
  "Ce runbook a changé. Recharger sa dernière version avant d'enregistrer.":
    "This runbook has changed. Reload the latest version before saving.",
  "Runbook introuvable.": "This runbook could not be found.",
  "Analyse introuvable.": "This analysis could not be found.",
  "L'état de cette analyse a changé. Actualiser avant de poursuivre.":
    "This analysis has changed. Refresh before continuing.",
  "Annuler l'analyse avant de la supprimer.":
    "Cancel this analysis before deleting it.",
  "File pleine. Attendre la fin d'une analyse.":
    "The queue is full. Wait for an analysis to finish.",
  "File pleine. Réessayer après une analyse.":
    "The queue is full. Wait for an analysis to finish.",
  "Le moteur local traite une analyse. Réessayer lorsqu'elle sera terminée.":
    "The local model is analysing an incident. Try again when it finishes.",
  "Recherche sémantique indisponible. Vérifier l'index et l'inférence locale.":
    "Semantic search is unavailable. Check the index and local inference.",
  "Session expirée.": "Your session has expired. Sign in again.",
  "Session expirée. Reconnectez-vous.":
    "Your session has expired. Sign in again.",
  "Authentification requise.": "Sign in to continue.",
  "Connexion refusée.": "Sign-in failed. Check your password and try again.",
  "Lien de connexion expiré ou déjà utilisé.":
    "This sign-in link has expired or already been used. Open a new one from your terminal.",
  "Validation de la session requise. Actualiser la page.":
    "Refresh the page to validate your session.",
  "Origine de la requête refusée.": "This request origin is not allowed.",
  "Commande réservée au CLI local.":
    "This command is only available through the local CLI.",
  "Données invalides : vérifier les champs et leurs limites.":
    "Check your input and the field limits, then try again.",
  "Données ou configuration invalides.":
    "Check your input and the platform configuration.",
  "Ressource locale indisponible.":
    "This local resource is unavailable. Check system health.",
  "Trop de connexions en direct.":
    "Too many live connections. Close an unused tab and try again.",
  "Opération inconnue.": "This operation is not available.",
  "Route inconnue.": "This page could not be found.",
  "Le dernier message doit être celui de l'opérateur.":
    "Add your message before sending the conversation.",
  "Moteur vocal absent. Installer apps/voice puis ses modèles.":
    "The voice engine is not installed. Install apps/voice and its models.",
  "Moteur vocal indisponible ou délai dépassé.":
    "The voice engine is unavailable or timed out. Try again.",
  "Le moteur vocal traite déjà une demande.":
    "The voice engine is busy. Wait a moment and try again.",
  "Réponse vocale trop volumineuse.":
    "The voice response exceeded the size limit.",
  "Réponse audio non régulière.":
    "The voice engine returned an invalid audio file.",
  "Réponse audio invalide.": "The voice engine returned invalid audio.",
  "Audio encodé invalide.":
    "This audio recording could not be read. Record a new message.",
  "Audio limité à 8 Mio.": "Audio recordings must be smaller than 8 MiB.",
  "Transcription invalide.":
    "The recording could not be transcribed. Try again or type your message.",
  "Le modèle local n'a pas répondu. Vérifier la passerelle et réessayer.":
    "The local model did not respond. Check the AI gateway and try again.",
  "Mot de passe enregistré. Reconnectez-vous.":
    "Password saved. Sign in again to continue.",
  "Opération terminée.": "Operation completed successfully.",
  "Opération échouée. Consulter le diagnostic de la plateforme.":
    "Operation failed. Check the platform diagnostics.",
};
export function systemMessage(
  value: string,
  fallback = "Details are unavailable. Check system health and try again.",
): string {
  if (messages[value]) return messages[value];
  if (value.startsWith("Exécution interrompue ("))
    return "Execution was interrupted. Check system health before trying again.";
  return fallback;
}
export function serviceName(id: string): string {
  return (
    (
      {
        litellm: "AI gateway",
        ollama: "Local inference",
        qdrant: "Vector memory",
        prometheus: "Metrics",
        tempo: "Traces",
        grafana: "Observability",
      } as Record<string, string>
    )[id] || "Local service"
  );
}
function errorMessage(detail: unknown, status: number): string {
  const fallback =
    (
      {
        400: "Check your input and try again.",
        401: "Your session has expired. Sign in again.",
        403: "This request is not allowed. Refresh the page and try again.",
        404: "This resource could not be found.",
        409: "This item changed or the service is busy. Refresh and try again.",
        413: "This request exceeds the size limit.",
        422: "Check your input and try again.",
        429: "Too many requests. Wait a moment and try again.",
        502: "A local service returned an invalid response. Try again.",
        503: "This service is unavailable. Check system health and try again.",
      } as Record<number, string>
    )[status] || "The request could not be completed. Try again.";
  return typeof detail === "string"
    ? systemMessage(detail, fallback)
    : fallback;
}
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
      errorMessage(data.detail, response.status),
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
  en_file: "Queued",
  en_cours: "Running",
  en_attente_humain: "Needs approval",
  complet: "Completed",
  rejete_par_humain: "Rejected",
  budget_epuise: "Budget reached",
  erreur: "Failed",
  interrompu: "Interrupted",
  annule: "Cancelled",
  decision: "Processing decision",
};
export const actifs = new Set(["en_file", "en_cours", "decision"]);
export const date = (valeur: string) =>
  Number.isNaN(new Date(valeur).getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-US", {
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
    throw new ErreurAPI(r.status, errorMessage(d.detail, r.status));
  }
  return r.blob();
}
