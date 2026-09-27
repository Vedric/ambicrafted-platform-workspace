import { t, useI18n, number, countLabel } from "../i18n";
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
  get green() {
    return t("Green");
  },
  get yellow() {
    return t("Yellow");
  },
  get grey() {
    return t("Grey");
  },
  get red() {
    return t("Red");
  },
};
const auditActions: Record<string, string> = {
  get "analyse.creee"() {
    return t("Analysis created");
  },
  get "analyse.en_file"() {
    return t("Analysis queued");
  },
  get "analyse.en_cours"() {
    return t("Analysis started");
  },
  get "analyse.en_attente_humain"() {
    return t("Proposal ready for review");
  },
  get "analyse.decision"() {
    return t("Decision submitted");
  },
  get "analyse.complet"() {
    return t("Analysis completed");
  },
  get "analyse.rejete_par_humain"() {
    return t("Proposal rejected");
  },
  get "analyse.budget_epuise"() {
    return t("Analysis budget reached");
  },
  get "analyse.erreur"() {
    return t("Analysis failed");
  },
  get "analyse.interrompu"() {
    return t("Analysis interrupted");
  },
  get "analyse.annule"() {
    return t("Analysis cancelled");
  },
  get "analyse.supprimee"() {
    return t("Analysis deleted");
  },
  get "analyse.exportee"() {
    return t("Analysis exported");
  },
  get "session.ouverte"() {
    return t("Session started");
  },
  get "runbook.enregistre"() {
    return t("Runbook saved");
  },
  get "retention.appliquee"() {
    return t("Retention policy applied");
  },
  get "securite.mot_de_passe_modifie"() {
    return t("Console password changed");
  },
};
const actorLabels: Record<string, string> = {
  get systeme() {
    return t("System");
  },
  get operateur() {
    return t("Operator");
  },
  cli: "CLI",
};
const toolLabels: Record<string, { name: string; description: string }> = {
  plateforme_preparation: {
    get name() {
      return t("Readiness checks");
    },
    get description() {
      return t("Inspect local readiness without executing maintenance.");
    },
  },
  plateforme_outils: {
    get name() {
      return t("Tool inventory");
    },
    get description() {
      return t("Inspect the approved local tools and their capabilities.");
    },
  },
  plateforme_analyse: {
    get name() {
      return t("Read an analysis");
    },
    get description() {
      return t("Read one analysis and its current result.");
    },
  },
  plateforme_lire_runbook: {
    get name() {
      return t("Read a runbook");
    },
    get description() {
      return t("Read a local runbook through the control API.");
    },
  },
  plateforme_recherche: {
    get name() {
      return t("Search runbooks");
    },
    get description() {
      return t("Search local procedures through the control API.");
    },
  },
  plateforme_journal: {
    get name() {
      return t("Activity log");
    },
    get description() {
      return t("Read the activity log without exposing alert content.");
    },
  },
  voix_feminine_en: {
    get name() {
      return t("English voice synthesis");
    },
    get description() {
      return t(
        "Generate speech locally with the high-quality English female voice.",
      );
    },
  },
  transcription_en: {
    get name() {
      return t("English transcription");
    },
    get description() {
      return t("Transcribe English speech locally on the CPU.");
    },
  },
  list_runbooks: {
    get name() {
      return t("List runbooks");
    },
    get description() {
      return t("Browse the procedures stored on this device.");
    },
  },
  read_runbook: {
    get name() {
      return t("Read a runbook");
    },
    get description() {
      return t("Read a source document and verify its fingerprint.");
    },
  },
  search_runbooks: {
    get name() {
      return t("Search runbook text");
    },
    get description() {
      return t("Find exact text in your procedures.");
    },
  },
  semantic_search: {
    get name() {
      return t("Semantic search");
    },
    get description() {
      return t("Find related passages using local embeddings and Qdrant.");
    },
  },
  plateforme_runbooks: {
    get name() {
      return t("Runbook inventory");
    },
    get description() {
      return t(
        "Read the runbook inventory through the control API’s MCP server.",
      );
    },
  },
  plateforme_sante: {
    get name() {
      return t("System health");
    },
    get description() {
      return t("Check local services and models through MCP.");
    },
  },
  plateforme_analyses: {
    get name() {
      return t("Analysis history");
    },
    get description() {
      return t("Read analyses and their current status through MCP.");
    },
  },
  voix_feminine_fr: {
    get name() {
      return t("French voice synthesis");
    },
    get description() {
      return t(
        "Generate speech locally with Piper’s female French SIWIS voice.",
      );
    },
  },
  transcription_fr: {
    get name() {
      return t("Local transcription");
    },
    get description() {
      return t(
        "Transcribe on the local CPU and review the text before sending.",
      );
    },
  },
  operations_locales: {
    get name() {
      return t("Platform operations");
    },
    get description() {
      return t(
        "Verify, reindex, back up and test restoration from the CLI or console.",
      );
    },
  },
};

export function SantePage() {
  useI18n();
  const q = useQuery({
    queryKey: ["sante"],
    queryFn: () => api<Sante>("/sante"),
    refetchInterval: 15000,
  });
  return (
    <>
      <Titre
        surligne={t("LOCAL INFRASTRUCTURE")}
        titre={t("System health")}
        texte={t(
          "Live service availability, installed models and the runbook index.",
        )}
      >
        <button
          className="btn"
          onClick={() => q.refetch()}
          disabled={q.isFetching}
        >
          <Activity size={17} /> {t("Refresh")}
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
                    {s.ok ? t("Available") : t("Unavailable")}
                  </span>
                </div>
                <h2>{serviceName(s.id)}</h2>
                <p>
                  {t("Response time")}{" "}
                  <strong className="mono">{number(s.latence_ms)} ms</strong>
                </p>
                {s.lien && (
                  <a
                    className="text-button"
                    href={s.lien}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t("Open console")} <ExternalLink size={14} />
                  </a>
                )}
              </section>
            ))}
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading">
                <h2>{t("Models on this device")}</h2>
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
                      <small>
                        {t("{count} GB", {
                          count: number(m.taille / 1e9, {
                            minimumFractionDigits: 1,
                            maximumFractionDigits: 1,
                          }),
                        })}
                      </small>
                    </div>
                  ))
                ) : (
                  <p className="muted">{t("Model inventory unavailable.")}</p>
                )}
              </div>
            </section>
            <section className="panel instruction-card">
              <span className="tile-icon">
                <Database size={23} />
              </span>
              <h2>{t("Runbook memory")}</h2>
              <div className="big-number">
                {q.data!.index.points === undefined
                  ? "—"
                  : number(q.data!.index.points)}
                <small>{t("chunks")}</small>
              </div>
              <p>
                {t("Active collection:")} <code>runbooks-current</code>
              </p>
              <p>
                {t("Status:")}{" "}
                {indexStatusLabels[q.data!.index.statut || ""] ||
                  t("Unavailable")}
              </p>
              <Link className="text-button" to="/operations">
                {t("Refresh the index")} <ArrowRight size={14} />
              </Link>
            </section>
          </div>
        </>
      )}
    </>
  );
}
export function Observabilite() {
  useI18n();
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
        surligne={t("OBSERVABILITY")}
        titre={t("Observability")}
        texte={t(
          "Monitor collected metrics and review activity without exposing alert content.",
        )}
      >
        <a
          className="btn primary"
          href="http://localhost:3000/d/plateforme-sre"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Gauge size={17} /> {t("Open Grafana")} <ExternalLink size={14} />
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
              <h2>{t("Prometheus collection")}</h2>
              <span className="tag">
                {countLabel(q.data!.cibles.length, "target")}
              </span>
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
                      {c.sante === "up"
                        ? t("Collecting")
                        : t("Needs attention")}
                    </span>
                    <small>{date(c.dernier_scrape)}</small>
                    <code>{number(Math.round(c.duree_s * 1000))} ms</code>
                  </div>
                ))
              ) : (
                <Vide
                  titre={t("No targets available")}
                  texte={t("Check Prometheus on the System health page.")}
                />
              )}
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>{t("Activity log")}</h2>
              <span className="muted tiny">{t("60 most recent events")}</span>
            </div>
            <div
              className="audit-list"
              tabIndex={0}
              role="region"
              aria-label={t("Activity log")}
            >
              {q.data!.journal.map((j) => (
                <div key={j.id}>
                  <span className="audit-icon">
                    <GitBranch size={15} />
                  </span>
                  <div>
                    <strong>
                      {auditActions[j.action] || t("Activity recorded")}
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
    get titre() {
      return t("Verify platform");
    },
    get texte() {
      return t("Check configuration and the services your agents depend on.");
    },
    icone: Activity,
    get bouton() {
      return t("Run verification");
    },
  },
  {
    id: "indexer",
    get titre() {
      return t("Refresh runbook memory");
    },
    get texte() {
      return t(
        "Rebuild runbook chunks and publish the updated search index atomically.",
      );
    },
    icone: Database,
    get bouton() {
      return t("Reindex runbooks");
    },
  },
  {
    id: "sauvegarder",
    get titre() {
      return t("Create a backup");
    },
    get texte() {
      return t(
        "Save data and configuration to private storage on this device.",
      );
    },
    icone: ArrowDownToLine,
    get bouton() {
      return t("Back up now");
    },
  },
  {
    id: "tester-restauration",
    get titre() {
      return t("Test restoration");
    },
    get texte() {
      return t("Restore the latest backup in isolated, temporary containers.");
    },
    icone: ShieldCheck,
    get bouton() {
      return t("Test backup");
    },
  },
];
export function Operations() {
  useI18n();
  const [operation, setOperation] = useState<string | null>(null),
    navigate = useNavigate();
  const lancer = useMutation({
    mutationFn: (id: string) => api<Analyse>("/operations/" + id, "POST"),
    onSuccess: (d) => navigate("/analyses/" + d.id),
  });
  return (
    <>
      <Titre
        surligne={t("PLATFORM OPERATIONS")}
        titre={t("Operations")}
        texte={t(
          "Run maintenance tasks with explicit controls and a recorded outcome.",
        )}
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
          {t(
            "Operations share a bounded queue with analyses. Backups may contain confidential data and remain on this device.",
          )}
        </span>
      </div>
      {operation && (
        <Modal
          titre={operations.find((o) => o.id === operation)!.titre}
          fermer={() => setOperation(null)}
        >
          <p>{operations.find((o) => o.id === operation)!.texte}</p>
          <p className="muted">
            {t(
              "This operation will join the queue. Track its progress and result in Analyses.",
            )}
          </p>
          {lancer.error && <Erreur erreur={lancer.error} />}
          <div className="form-actions">
            <button className="btn" onClick={() => setOperation(null)}>
              {t("Back")}
            </button>
            <button
              className="btn primary"
              disabled={lancer.isPending}
              onClick={() => lancer.mutate(operation)}
            >
              {t("Confirm operation")} <ArrowRight size={16} />
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
export function Agents() {
  useI18n();
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
        surligne={t("AGENTS & TOOLS")}
        titre={t("Specialists working toward one outcome.")}
        texte={t(
          "A coordinated team of local specialists, with you in control of approval.",
        )}
      />
      <div className="agents-flow">
        {[
          {
            nom: "Extraction",
            role: t("Understand the signal"),
            texte: t("Structures symptoms and flags suspicious instructions."),
            icon: Search,
          },
          {
            nom: "Triage",
            role: t("Assess the situation"),
            texte: t("Suggests a classification and urgency for your review."),
            icon: Activity,
          },
          {
            nom: "Investigation",
            role: t("Follow the evidence"),
            texte: t("Consults runbooks through MCP within a defined budget."),
            icon: BookOpen,
          },
          {
            nom: "Supervision",
            role: t("Keep you in control"),
            texte: t("Checks the sources and waits for your approval."),
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
              {i === 3 ? t("CODE + HUMAN") : t("LOCAL MODEL")}
            </span>
          </section>
        ))}
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>{t("Approved tools & connectors")}</h2>
          <span className="tag">{t("LOCAL MCP")}</span>
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
                  <strong>
                    {toolLabels[o.nom]?.name || t("Platform tool")}
                  </strong>
                  <p>
                    {toolLabels[o.nom]?.description ||
                      t("A capability provided by the local platform.")}
                  </p>
                  <code className="tiny muted">{o.nom}</code>
                  <span className="tiny muted">
                    {o.lecture_seule
                      ? t("Read-only")
                      : t("Operator action required")}
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
          {t(
            "Analysis roles run sequentially on your local engine. Agents cannot approve their own diagnosis or execute remediation.",
          )}
        </span>
      </div>
    </>
  );
}
export function Parametres() {
  useI18n();
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
        surligne={t("YOUR WORKSPACE")}
        titre={t("Settings & help")}
        texte={t(
          "Manage local access, understand session limits and work from your terminal.",
        )}
      />
      <div className="dashboard-grid">
        <section className="panel settings-panel">
          <h2>
            <LockKeyhole size={19} /> {t("Access & privacy")}
          </h2>
          {q.isPending ? (
            <Chargement />
          ) : q.error ? (
            <Erreur erreur={q.error} />
          ) : (
            <dl>
              <dt>Version</dt>
              <dd>{q.data!.version}</dd>
              <dt>{t("Access mode")}</dt>
              <dd>
                {q.data!.acces === "Local privé"
                  ? t("Private local access")
                  : t("Unknown access mode")}
              </dd>
              <dt>{t("Analysis alias")}</dt>
              <dd>{q.data!.alias}</dd>
              <dt>{t("Queue capacity")}</dt>
              <dd>{countLabel(q.data!.file_max, "task")}</dd>
              <dt>{t("Session duration")}</dt>
              <dd>{countLabel(q.data!.duree_session_heures, "hour")}</dd>
              <dt>{t("Analysis retention")}</dt>
              <dd>{countLabel(q.data!.retention_jours, "day")}</dd>
            </dl>
          )}
          <p className="hint">
            {t(
              "Change the theme or pause animations from the top bar. Your choices are saved on this browser. Animations also respect your system’s reduced-motion preference.",
            )}
          </p>
        </section>
        <section className="panel settings-panel">
          <h2>
            <ShieldCheck size={19} /> {t("Console password")}
          </h2>
          <p>
            {t(
              "You can also start a secure session from the CLI without entering a password.",
            )}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              changer.mutate();
            }}
          >
            <label htmlFor="nouveau-mdp">{t("New password")}</label>
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
            <label htmlFor="confirmer-mdp">{t("Confirm password")}</label>
            <input
              id="confirmer-mdp"
              type="password"
              autoComplete="new-password"
              required
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
            <p className="hint">
              {t(
                "Use at least 14 characters. Saving signs out all existing sessions.",
              )}
            </p>
            {changer.error && <Erreur erreur={changer.error} />}
            <button
              className="btn primary"
              disabled={
                changer.isPending || mot.length < 14 || mot !== confirmation
              }
            >
              {t("Save and sign in again")}
            </button>
          </form>
        </section>
      </div>
      <section className="panel settings-panel">
        <h2>
          <SquareTerminal size={20} />{" "}
          {t("The same platform, from your terminal.")}
        </h2>
        <p>
          {t(
            "Run these commands from the project directory. Alert text is read from standard input and stays out of the process list.",
          )}
        </p>
        <div className="cli-examples">
          <code>./plateforme ouvrir</code>
          <span>{t("Start a console session")}</span>
          <code>./plateforme statut</code>
          <span>{t("Check local services")}</span>
          <code>./plateforme analyses lister</code>
          <span>{t("List analyses")}</span>
          <code>./plateforme --help</code>
          <span>{t("Browse all commands")}</span>
        </div>
      </section>
    </>
  );
}
