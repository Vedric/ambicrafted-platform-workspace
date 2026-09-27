import { t, getLocale } from "./i18n";
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
  get "Ce runbook a changé. Recharger sa dernière version avant d'enregistrer."() {
    return t(
      "This runbook has changed. Reload the latest version before saving.",
    );
  },
  get "Runbook introuvable."() {
    return t("This runbook could not be found.");
  },
  get "Analyse introuvable."() {
    return t("This analysis could not be found.");
  },
  get "L'état de cette analyse a changé. Actualiser avant de poursuivre."() {
    return t("This analysis has changed. Refresh before continuing.");
  },
  get "Annuler l'analyse avant de la supprimer."() {
    return t("Cancel this analysis before deleting it.");
  },
  get "File pleine. Attendre la fin d'une analyse."() {
    return t("The queue is full. Wait for an analysis to finish.");
  },
  get "File pleine. Réessayer après une analyse."() {
    return t("The queue is full. Wait for an analysis to finish.");
  },
  get "Le moteur local traite une analyse. Réessayer lorsqu'elle sera terminée."() {
    return t(
      "The local model is analysing an incident. Try again when it finishes.",
    );
  },
  get "Recherche sémantique indisponible. Vérifier l'index et l'inférence locale."() {
    return t(
      "Semantic search is unavailable. Check the index and local inference.",
    );
  },
  get "Session expirée."() {
    return t("Your session has expired. Sign in again.");
  },
  get "Session expirée. Reconnectez-vous."() {
    return t("Your session has expired. Sign in again.");
  },
  get "Authentification requise."() {
    return t("Sign in to continue.");
  },
  get "Connexion refusée."() {
    return t("Sign-in failed. Check your password and try again.");
  },
  get "Lien de connexion expiré ou déjà utilisé."() {
    return t(
      "This sign-in link has expired or already been used. Open a new one from your terminal.",
    );
  },
  get "Validation de la session requise. Actualiser la page."() {
    return t("Refresh the page to validate your session.");
  },
  get "Origine de la requête refusée."() {
    return t("This request origin is not allowed.");
  },
  get "Commande réservée au CLI local."() {
    return t("This command is only available through the local CLI.");
  },
  get "Données invalides : vérifier les champs et leurs limites."() {
    return t("Check your input and the field limits, then try again.");
  },
  get "Données ou configuration invalides."() {
    return t("Check your input and the platform configuration.");
  },
  get "Ressource locale indisponible."() {
    return t("This local resource is unavailable. Check system health.");
  },
  get "Trop de connexions en direct."() {
    return t("Too many live connections. Close an unused tab and try again.");
  },
  get "Opération inconnue."() {
    return t("This operation is not available.");
  },
  get "Route inconnue."() {
    return t("This page could not be found.");
  },
  get "Le dernier message doit être celui de l'opérateur."() {
    return t("Add your message before sending the conversation.");
  },
  get "Moteur vocal absent. Installer apps/voice puis ses modèles."() {
    return t(
      "The voice engine is not installed. Install apps/voice and its models.",
    );
  },
  get "Moteur vocal indisponible ou délai dépassé."() {
    return t("The voice engine is unavailable or timed out. Try again.");
  },
  get "Le moteur vocal traite déjà une demande."() {
    return t("The voice engine is busy. Wait a moment and try again.");
  },
  get "Réponse vocale trop volumineuse."() {
    return t("The voice response exceeded the size limit.");
  },
  get "Réponse audio non régulière."() {
    return t("The voice engine returned an invalid audio file.");
  },
  get "Réponse audio invalide."() {
    return t("The voice engine returned invalid audio.");
  },
  get "Audio encodé invalide."() {
    return t("This audio recording could not be read. Record a new message.");
  },
  get "Audio limité à 8 Mio."() {
    return t("Audio recordings must be smaller than 8 MiB.");
  },
  get "Transcription invalide."() {
    return t(
      "The recording could not be transcribed. Try again or type your message.",
    );
  },
  get "Le modèle local n'a pas répondu. Vérifier la passerelle et réessayer."() {
    return t(
      "The local model did not respond. Check the AI gateway and try again.",
    );
  },
  get "Mot de passe enregistré. Reconnectez-vous."() {
    return t("Password saved. Sign in again to continue.");
  },
  get "Opération terminée."() {
    return t("Operation completed successfully.");
  },
  get "Opération échouée. Consulter le diagnostic de la plateforme."() {
    return t("Operation failed. Check the platform diagnostics.");
  },
};
export function systemMessage(
  value: string,
  fallback = t("Details are unavailable. Check system health and try again."),
): string {
  if (messages[value]) return messages[value];
  if (value.startsWith("Exécution interrompue ("))
    return t(
      "Execution was interrupted. Check system health before trying again.",
    );
  return fallback;
}
export function serviceName(id: string): string {
  return (
    (
      {
        litellm: t("AI gateway"),
        ollama: t("Local inference"),
        qdrant: t("Vector memory"),
        prometheus: t("Metrics"),
        tempo: t("Traces"),
        grafana: t("Observability"),
      } as Record<string, string>
    )[id] || t("Local service")
  );
}
function errorMessage(detail: unknown, status: number): string {
  const fallback =
    (
      {
        400: t("Check your input and try again."),
        401: t("Your session has expired. Sign in again."),
        403: t("This request is not allowed. Refresh the page and try again."),
        404: t("This resource could not be found."),
        409: t(
          "This item changed or the service is busy. Refresh and try again.",
        ),
        413: t("This request exceeds the size limit."),
        422: t("Check your input and try again."),
        429: t("Too many requests. Wait a moment and try again."),
        502: t("A local service returned an invalid response. Try again."),
        503: t(
          "This service is unavailable. Check system health and try again.",
        ),
      } as Record<number, string>
    )[status] || t("The request could not be completed. Try again.");
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
  get en_file() {
    return t("Queued");
  },
  get en_cours() {
    return t("Running");
  },
  get en_attente_humain() {
    return t("Needs approval");
  },
  get complet() {
    return t("Completed");
  },
  get rejete_par_humain() {
    return t("Rejected");
  },
  get budget_epuise() {
    return t("Budget reached");
  },
  get erreur() {
    return t("Failed");
  },
  get interrompu() {
    return t("Interrupted");
  },
  get annule() {
    return t("Cancelled");
  },
  get decision() {
    return t("Processing decision");
  },
};
export const actifs = new Set(["en_file", "en_cours", "decision"]);
export const date = (valeur: string) =>
  Number.isNaN(new Date(valeur).getTime())
    ? "—"
    : new Intl.DateTimeFormat(getLocale(), {
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
  langue: "en" | "fr" = "en",
): Promise<Blob> {
  const r = await fetch("/api/voix/parler", {
    method: "POST",
    credentials: "same-origin",
    signal,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify({ texte, langue }),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ErreurAPI(r.status, errorMessage(d.detail, r.status));
  }
  return r.blob();
}
