import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Bot,
  Database,
  ExternalLink,
  Gauge,
  GitBranch,
  LockKeyhole,
  Search,
  ShieldCheck,
  SquareTerminal,
  Wrench,
} from "lucide-react";
import {
  api,
  date,
  serviceName,
  type Analyse,
  type Journal,
  type Sante,
} from "../api";
import { Erreur, Chargement, Vide, Titre, Modal } from "../ui";

const indexStatusLabels: Record<string, string> = {
  green: "Green",
  yellow: "Yellow",
  grey: "Grey",
  red: "Red",
};
const auditActions: Record<string, string> = {
  "analyse.creee": "Analysis created",
  "analyse.en_file": "Analysis queued",
  "analyse.en_cours": "Analysis started",
  "analyse.en_attente_humain": "Proposal ready for review",
  "analyse.decision": "Decision submitted",
  "analyse.complet": "Analysis completed",
  "analyse.rejete_par_humain": "Proposal rejected",
  "analyse.budget_epuise": "Analysis budget reached",
  "analyse.erreur": "Analysis failed",
  "analyse.interrompu": "Analysis interrupted",
  "analyse.annule": "Analysis cancelled",
  "analyse.supprimee": "Analysis deleted",
  "analyse.exportee": "Analysis exported",
  "session.ouverte": "Session started",
  "runbook.enregistre": "Runbook saved",
  "retention.appliquee": "Retention policy applied",
  "securite.mot_de_passe_modifie": "Console password changed",
};
const actorLabels: Record<string, string> = {
  systeme: "System",
  operateur: "Operator",
  cli: "CLI",
};
const toolLabels: Record<string, { name: string; description: string }> = {
  list_runbooks: {
    name: "List runbooks",
    description: "Browse the procedures stored on this device.",
  },
  read_runbook: {
    name: "Read a runbook",
    description: "Read a source document and verify its fingerprint.",
  },
  search_runbooks: {
    name: "Search runbook text",
    description: "Find exact text in your procedures.",
  },
  semantic_search: {
    name: "Semantic search",
    description: "Find related passages using local embeddings and Qdrant.",
  },
  plateforme_runbooks: {
    name: "Runbook inventory",
    description:
      "Read the runbook inventory through the control API’s MCP server.",
  },
  plateforme_sante: {
    name: "System health",
    description: "Check local services and models through MCP.",
  },
  plateforme_analyses: {
    name: "Analysis history",
    description: "Read analyses and their current status through MCP.",
  },
  voix_feminine_fr: {
    name: "French voice synthesis",
    description:
      "Generate speech locally with Piper’s female French SIWIS voice.",
  },
  transcription_fr: {
    name: "Local transcription",
    description:
      "Transcribe on the local CPU and review the text before sending.",
  },
  operations_locales: {
    name: "Platform operations",
    description:
      "Verify, reindex, back up and test restoration from the CLI or console.",
  },
};

export function SantePage() {
  const q = useQuery({
    queryKey: ["sante"],
    queryFn: () => api<Sante>("/sante"),
    refetchInterval: 15000,
  });
  return (
    <>
      <Titre
        surligne="LOCAL INFRASTRUCTURE"
        titre="System health"
        texte="Live service availability, installed models and the runbook index."
      >
        <button
          className="btn"
          onClick={() => q.refetch()}
          disabled={q.isFetching}
        >
          <Activity size={17} /> Refresh
        </button>
      </Titre>
      {q.isPending ? (
        <Chargement />
      ) : q.error ? (
        <Erreur erreur={q.error} />
      ) : (
        <>
          <div className="service-grid">
            {q.data!.services.map((s) => (
              <section className="panel service-card" key={s.id}>
                <div className="runbook-card-top">
                  <span className="tile-icon">
                    <Database size={23} />
                  </span>
                  <span
                    className={
                      "badge " + (s.ok ? "status-complet" : "status-erreur")
                    }
                  >
                    <i />
                    {s.ok ? "Available" : "Unavailable"}
                  </span>
                </div>
                <h2>{serviceName(s.id)}</h2>
                <p>
                  Response time{" "}
                  <strong className="mono">{s.latence_ms} ms</strong>
                </p>
                {s.lien && (
                  <a
                    className="text-button"
                    href={s.lien}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open console <ExternalLink size={14} />
                  </a>
                )}
              </section>
            ))}
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading">
                <h2>Models on this device</h2>
                <Bot size={18} />
              </div>
              <div className="model-list">
                {q.data!.modeles.length ? (
                  q.data!.modeles.map((m) => (
                    <div key={m.nom}>
                      <span className="tile-icon">
                        <Bot size={18} />
                      </span>
                      <strong>{m.nom}</strong>
                      <small>{(m.taille / 1e9).toFixed(1)} GB</small>
                    </div>
                  ))
                ) : (
                  <p className="muted">Model inventory unavailable.</p>
                )}
              </div>
            </section>
            <section className="panel instruction-card">
              <span className="tile-icon">
                <Database size={23} />
              </span>
              <h2>Runbook memory</h2>
              <div className="big-number">
                {q.data!.index.points ?? "—"}
                <small>chunks</small>
              </div>
              <p>
                Active collection: <code>runbooks-current</code>
              </p>
              <p>
                Status:{" "}
                {indexStatusLabels[q.data!.index.statut || ""] || "Unavailable"}
              </p>
              <Link className="text-button" to="/operations">
                Refresh the index <ArrowRight size={14} />
              </Link>
            </section>
          </div>
        </>
      )}
    </>
  );
}
export function Observabilite() {
  const q = useQuery({
    queryKey: ["observabilite"],
    queryFn: () =>
      api<{
        cibles: {
          nom: string;
          sante: string;
          dernier_scrape: string;
          duree_s: number;
        }[];
        journal: Journal[];
      }>("/observabilite"),
    refetchInterval: 15000,
  });
  return (
    <>
      <Titre
        surligne="OBSERVABILITY"
        titre="Observability"
        texte="Monitor collected metrics and review activity without exposing alert content."
      >
        <a
          className="btn primary"
          href="http://localhost:3000/d/plateforme-sre"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Gauge size={17} /> Open Grafana <ExternalLink size={14} />
        </a>
      </Titre>
      {q.isPending ? (
        <Chargement />
      ) : q.error ? (
        <Erreur erreur={q.error} />
      ) : (
        <>
          <section className="panel">
            <div className="panel-heading">
              <h2>Prometheus collection</h2>
              <span className="tag">{q.data!.cibles.length} TARGETS</span>
            </div>
            <div className="targets">
              {q.data!.cibles.length ? (
                q.data!.cibles.map((c) => (
                  <div key={c.nom}>
                    <span
                      className={
                        "health-dot " +
                        (c.sante === "up" ? "healthy" : "unhealthy")
                      }
                    />
                    <strong>{c.nom}</strong>
                    <span>
                      {c.sante === "up" ? "Collecting" : "Needs attention"}
                    </span>
                    <small>{date(c.dernier_scrape)}</small>
                    <code>{Math.round(c.duree_s * 1000)} ms</code>
                  </div>
                ))
              ) : (
                <Vide
                  titre="No targets available"
                  texte="Check Prometheus on the System health page."
                />
              )}
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Activity log</h2>
              <span className="muted tiny">60 most recent events</span>
            </div>
            <div className="audit-list">
              {q.data!.journal.map((j) => (
                <div key={j.id}>
                  <span className="audit-icon">
                    <GitBranch size={15} />
                  </span>
                  <div>
                    <strong>
                      {auditActions[j.action] || "Activity recorded"}
                    </strong>
                    <small>
                      {actorLabels[j.acteur] || j.acteur}
                      {j.reference ? " · " + j.reference.slice(0, 24) : ""}
                    </small>
                  </div>
                  <time>{date(j.date)}</time>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}
const operations = [
  {
    id: "verifier",
    titre: "Verify platform",
    texte: "Check configuration and the services your agents depend on.",
    icone: Activity,
    bouton: "Run verification",
  },
  {
    id: "indexer",
    titre: "Refresh runbook memory",
    texte:
      "Rebuild runbook chunks and publish the updated search index atomically.",
    icone: Database,
    bouton: "Reindex runbooks",
  },
  {
    id: "sauvegarder",
    titre: "Create a backup",
    texte: "Save data and configuration to private storage on this device.",
    icone: ArrowDownToLine,
    bouton: "Back up now",
  },
  {
    id: "tester-restauration",
    titre: "Test restoration",
    texte: "Restore the latest backup in isolated, temporary containers.",
    icone: ShieldCheck,
    bouton: "Test backup",
  },
];
export function Operations() {
  const [operation, setOperation] = useState<string | null>(null),
    navigate = useNavigate();
  const lancer = useMutation({
    mutationFn: (id: string) => api<Analyse>("/operations/" + id, "POST"),
    onSuccess: (d) => navigate("/analyses/" + d.id),
  });
  return (
    <>
      <Titre
        surligne="PLATFORM OPERATIONS"
        titre="Operations"
        texte="Run maintenance tasks with explicit controls and a recorded outcome."
      />
      <div className="service-grid operations-grid">
        {operations.map((o) => (
          <section className="panel operation-card" key={o.id}>
            <span className="tile-icon">
              <o.icone size={24} />
            </span>
            <h2>{o.titre}</h2>
            <p>{o.texte}</p>
            <button className="btn" onClick={() => setOperation(o.id)}>
              {o.bouton}
              <ArrowRight size={16} />
            </button>
          </section>
        ))}
      </div>
      <div className="notice inline-notice">
        <ShieldCheck size={20} />
        <span>
          Operations share a bounded queue with analyses. Backups may contain
          confidential data and remain on this device.
        </span>
      </div>
      {operation && (
        <Modal
          titre={operations.find((o) => o.id === operation)!.titre}
          fermer={() => setOperation(null)}
        >
          <p>{operations.find((o) => o.id === operation)!.texte}</p>
          <p className="muted">
            This operation will join the queue. Track its progress and result in
            Analyses.
          </p>
          {lancer.error && <Erreur erreur={lancer.error} />}
          <div className="form-actions">
            <button className="btn" onClick={() => setOperation(null)}>
              Back
            </button>
            <button
              className="btn primary"
              disabled={lancer.isPending}
              onClick={() => lancer.mutate(operation)}
            >
              Confirm operation <ArrowRight size={16} />
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
export function Agents() {
  const q = useQuery({
    queryKey: ["outils"],
    queryFn: () =>
      api<{
        outils: { nom: string; description: string; lecture_seule: boolean }[];
      }>("/outils"),
  });
  return (
    <>
      <Titre
        surligne="AGENTS & TOOLS"
        titre="Specialists working toward one outcome."
        texte="A coordinated team of local specialists, with you in control of approval."
      />
      <div className="agents-flow">
        {[
          {
            nom: "Extraction",
            role: "Understand the signal",
            texte: "Structures symptoms and flags suspicious instructions.",
            icon: Search,
          },
          {
            nom: "Triage",
            role: "Assess the situation",
            texte: "Suggests a classification and urgency for your review.",
            icon: Activity,
          },
          {
            nom: "Investigation",
            role: "Follow the evidence",
            texte: "Consults runbooks through MCP within a defined budget.",
            icon: BookOpen,
          },
          {
            nom: "Supervision",
            role: "Keep you in control",
            texte: "Checks the sources and waits for your approval.",
            icon: ShieldCheck,
          },
        ].map((a, i) => (
          <section className="panel agent-card" key={a.nom}>
            <span className="agent-number">0{i + 1}</span>
            <span className="tile-icon">
              <a.icon size={24} />
            </span>
            <h2>{a.nom}</h2>
            <strong>{a.role}</strong>
            <p>{a.texte}</p>
            <span className="tag">
              {i === 3 ? "CODE + HUMAN" : "LOCAL MODEL"}
            </span>
          </section>
        ))}
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Approved tools & connectors</h2>
          <span className="tag">LOCAL MCP</span>
        </div>
        {q.isPending ? (
          <Chargement />
        ) : q.error ? (
          <Erreur erreur={q.error} />
        ) : (
          <div className="tools-grid">
            {q.data!.outils.map((o) => (
              <div key={o.nom}>
                <span className="tile-icon">
                  <Wrench size={18} />
                </span>
                <div>
                  <strong>{toolLabels[o.nom]?.name || "Platform tool"}</strong>
                  <p>
                    {toolLabels[o.nom]?.description ||
                      "A capability provided by the local platform."}
                  </p>
                  <code className="tiny muted">{o.nom}</code>
                  <span className="tiny muted">
                    {o.lecture_seule ? "Read-only" : "Operator action required"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
      <div className="notice inline-notice">
        <LockKeyhole size={20} />
        <span>
          Analysis roles run sequentially on your local engine. Agents cannot
          approve their own diagnosis or execute remediation.
        </span>
      </div>
    </>
  );
}
export function Parametres() {
  const q = useQuery({
    queryKey: ["parametres"],
    queryFn: () =>
      api<{
        version: string;
        acces: string;
        alias: string;
        file_max: number;
        retention_jours: number;
        duree_session_heures: number;
      }>("/parametres"),
  });
  const [mot, setMot] = useState(""),
    [confirmation, setConfirmation] = useState("");
  const client = useQueryClient();
  const changer = useMutation({
    mutationFn: () => api("/auth/mot-de-passe", "PUT", { valeur: mot }),
    onSuccess: () => {
      setMot("");
      setConfirmation("");
      client.clear();
      location.assign("/");
    },
  });
  return (
    <>
      <Titre
        surligne="YOUR WORKSPACE"
        titre="Settings & help"
        texte="Manage local access, understand session limits and work from your terminal."
      />
      <div className="dashboard-grid">
        <section className="panel settings-panel">
          <h2>
            <LockKeyhole size={19} /> Access & privacy
          </h2>
          {q.isPending ? (
            <Chargement />
          ) : q.error ? (
            <Erreur erreur={q.error} />
          ) : (
            <dl>
              <dt>Version</dt>
              <dd>{q.data!.version}</dd>
              <dt>Access mode</dt>
              <dd>
                {q.data!.acces === "Local privé"
                  ? "Private local access"
                  : "Unknown access mode"}
              </dd>
              <dt>Analysis alias</dt>
              <dd>{q.data!.alias}</dd>
              <dt>Queue capacity</dt>
              <dd>{q.data!.file_max} tasks</dd>
              <dt>Session duration</dt>
              <dd>{q.data!.duree_session_heures} hours</dd>
              <dt>Analysis retention</dt>
              <dd>{q.data!.retention_jours} days</dd>
            </dl>
          )}
          <p className="hint">
            Change the theme or pause animations from the top bar. Your choices
            are saved on this browser. Animations also respect your system’s
            reduced-motion preference.
          </p>
        </section>
        <section className="panel settings-panel">
          <h2>
            <ShieldCheck size={19} /> Console password
          </h2>
          <p>
            You can also start a secure session from the CLI without entering a
            password.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              changer.mutate();
            }}
          >
            <label htmlFor="nouveau-mdp">New password</label>
            <input
              id="nouveau-mdp"
              type="password"
              autoComplete="new-password"
              minLength={14}
              maxLength={128}
              required
              value={mot}
              onChange={(e) => setMot(e.target.value)}
            />
            <label htmlFor="confirmer-mdp">Confirm password</label>
            <input
              id="confirmer-mdp"
              type="password"
              autoComplete="new-password"
              required
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
            <p className="hint">
              Use at least 14 characters. Saving signs out all existing
              sessions.
            </p>
            {changer.error && <Erreur erreur={changer.error} />}
            <button
              className="btn primary"
              disabled={
                changer.isPending || mot.length < 14 || mot !== confirmation
              }
            >
              Save and sign in again
            </button>
          </form>
        </section>
      </div>
      <section className="panel settings-panel">
        <h2>
          <SquareTerminal size={20} /> The same platform, from your terminal.
        </h2>
        <p>
          Run these commands from the project directory. Alert text is read from
          standard input and stays out of the process list.
        </p>
        <div className="cli-examples">
          <code>./plateforme ouvrir</code>
          <span>Start a console session</span>
          <code>./plateforme statut</code>
          <span>Check local services</span>
          <code>./plateforme analyses lister</code>
          <span>List analyses</span>
          <code>./plateforme --help</code>
          <span>Browse all commands</span>
        </div>
      </section>
    </>
  );
}
