import { t, useI18n, getLocale, number, countLabel } from "../i18n";
import { useEffect, useState } from "react";
import { RunUsage } from "../RunUsage";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  ExternalLink,
  FileText,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  Plus,
  Radio,
  Search,
  ShieldCheck,
  Trash2,
  Workflow,
  Wrench,
  Zap,
} from "lucide-react";
import {
  api,
  apercu,
  actifs,
  date,
  statuts,
  systemMessage,
  type Analyse,
  type Liste,
} from "../api";
import {
  useToast,
  Erreur,
  Chargement,
  Vide,
  Titre,
  Badge,
  Markdown,
  Modal,
} from "../ui";

import { findMission } from "../missions";

const confidenceLabels: Record<string, string> = {
  get haute() {
    return t("High");
  },
  get moyenne() {
    return t("Medium");
  },
  get faible() {
    return t("Low");
  },
};
const operationTitles: Record<string, string> = {
  get verifier() {
    return t("Platform verification");
  },
  get indexer() {
    return t("Runbook reindexing");
  },
  get sauvegarder() {
    return t("Platform backup");
  },
  get "tester-restauration"() {
    return t("Backup restoration test");
  },
};
const analysisTitle = (analysis: Analyse) =>
  analysis.mode === "operation"
    ? operationTitles[analysis.options.operation || ""] ||
      t("Platform operation")
    : analysis.titre;

export function ListeAnalyses({ elements }: { elements: Analyse[] }) {
  useI18n();
  return (
    <div className="analysis-list">
      {elements.map((a) => (
        <Link to={"/analyses/" + a.id} key={a.id} className="analysis-row">
          <span
            className={
              "analysis-icon " + (actifs.has(a.statut) ? "active-icon" : "")
            }
          >
            {a.mode === "operation" ? (
              <Wrench size={18} />
            ) : (
              <Workflow size={18} />
            )}
          </span>
          <div className="analysis-name">
            <strong>{analysisTitle(a)}</strong>
            <small>
              {date(a.cree_le)} ·{" "}
              {a.mode === "operation"
                ? t("Operation")
                : t("Supervised analysis")}
            </small>
          </div>
          <Badge statut={a.statut} />
          <ChevronRight size={16} />
        </Link>
      ))}
    </div>
  );
}
export function Analyses({ approbations = false }: { approbations?: boolean }) {
  useI18n();
  const [filtre, setFiltre] = useState(""),
    [recherche, setRecherche] = useState(""),
    [page, setPage] = useState(1);
  const statut = approbations ? "en_attente_humain" : filtre;
  const q = useQuery({
    queryKey: ["analyses", statut, recherche, page],
    queryFn: () =>
      api<Liste>(
        `/analyses?statut=${statut}&recherche=${encodeURIComponent(recherche)}&page=${page}`,
      ),
    refetchInterval: 5000,
  });
  return (
    <>
      <Titre
        surligne={approbations ? t("HUMAN OVERSIGHT") : "ORCHESTRATION"}
        titre={approbations ? t("Approvals") : t("Analyses")}
        texte={
          approbations
            ? t(
                "Review the evidence and prerequisites before approving a proposal.",
              )
            : t("Follow every run from the first signal to a reviewed result.")
        }
      >
        <Link to="/analyses/nouvelle" className="btn primary">
          <Plus size={18} /> {t("New analysis")}
        </Link>
      </Titre>
      <section className="panel">
        <div className="toolbar">
          <div className="search-input">
            <Search size={17} />
            <input
              aria-label={t("Search analyses")}
              placeholder={t("Search analyses…")}
              value={recherche}
              onChange={(e) => {
                setRecherche(e.target.value);
                setPage(1);
              }}
            />
          </div>
          {!approbations && (
            <select
              aria-label={t("Filter by status")}
              value={filtre}
              onChange={(e) => {
                setFiltre(e.target.value);
                setPage(1);
              }}
            >
              <option value="">{t("All statuses")}</option>
              {Object.entries(statuts).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          )}
          <span className="muted tiny">
            {q.data ? countLabel(q.data.total, "result") : "—"}
          </span>
        </div>
        {q.isPending ? (
          <Chargement />
        ) : q.error ? (
          <Erreur erreur={q.error} recommencer={() => q.refetch()} />
        ) : q.data?.elements.length ? (
          <ListeAnalyses elements={q.data.elements} />
        ) : (
          <Vide
            titre={
              approbations ? t("No pending approvals") : t("No analyses yet")
            }
            texte={
              approbations
                ? t(
                    "Proposals appear here when they are ready for your review.",
                  )
                : t("Start an analysis or adjust your search.")
            }
          />
        )}
        <div className="pagination">
          <button
            className="btn small"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            {t("Previous")}
          </button>
          <span>{t("Page {page}", { page: number(page) })}</span>
          <button
            className="btn small"
            disabled={!q.data || page * 25 >= q.data.total}
            onClick={() => setPage(page + 1)}
          >
            {t("Next")}
          </button>
        </div>
      </section>
    </>
  );
}
export function NouvelleAnalyse() {
  useI18n();
  const [searchParams] = useSearchParams();
  const mission = findMission(searchParams.get("mission"));
  const [titre, setTitre] = useState<string>(() => mission?.draftTitle || ""),
    [alerte, setAlerte] = useState<string>(() => mission?.draft || "");
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: () => api<Analyse>("/analyses", "POST", { titre, alerte }),
    onSuccess: (d) => {
      setAlerte("");
      navigate("/analyses/" + d.id);
    },
  });
  return (
    <>
      <Titre
        surligne={t("NEW ANALYSIS")}
        titre={t("New analysis")}
        texte={t(
          "Describe what you observed. Your agents will investigate against your runbooks.",
        )}
      />
      {mission && (
        <div className="mission-brief">
          <span>{mission.category}</span>
          <strong>{mission.title}</strong>
          <p>
            {t(
              "Replace the prompts with observed facts before launching. This draft has not been submitted.",
            )}
          </p>
        </div>
      )}
      <div className="form-grid">
        <form
          className="panel form-panel"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <label htmlFor="titre">
            {t("Analysis title")}{" "}
            <span>{t("A clear name for this investigation")}</span>
          </label>
          <input
            id="titre"
            required
            maxLength={100}
            placeholder={t("e.g. PostgreSQL connection pool exhausted")}
            value={titre}
            onChange={(e) => setTitre(e.target.value)}
          />
          <label htmlFor="alerte">
            {t("Alert & context")}{" "}
            <span>{t("Symptoms, metrics and error messages")}</span>
          </label>
          <textarea
            id="alerte"
            required
            minLength={1}
            maxLength={20000}
            rows={13}
            placeholder={t(
              "Describe the issue, when it started and what you have already checked…",
            )}
            value={alerte}
            onChange={(e) => setAlerte(e.target.value)}
          />
          <div className="field-foot">
            <span>
              <LockKeyhole size={13} /> {t("Processed locally")}
            </span>
            <span>
              {t("{count} / 20,000", { count: number(alerte.length) })}
            </span>
          </div>
          {mutation.error && <Erreur erreur={mutation.error} />}
          <div className="form-actions">
            <Link className="btn" to="/analyses">
              {t("Cancel")}
            </Link>
            <button
              className="btn primary"
              disabled={mutation.isPending || !alerte.trim() || !titre.trim()}
            >
              {mutation.isPending ? (
                <LoaderCircle className="spin" size={17} />
              ) : (
                <Zap size={17} />
              )}{" "}
              {t("Run analysis")}
            </button>
          </div>
        </form>
        <aside className="form-aside">
          <div className="panel instruction-card">
            <span className="tile-icon">
              <GitBranch size={24} />
            </span>
            <h2>{t("Evidence at every step.")}</h2>
            <ol className="numbered-steps">
              <li>
                <strong>{t("Understand")}</strong>
                <p>{t("Extract symptoms and flag suspicious instructions.")}</p>
              </li>
              <li>
                <strong>{t("Investigate")}</strong>
                <p>
                  {t("Classify the alert and consult relevant procedures.")}
                </p>
              </li>
              <li>
                <strong>{t("Verify")}</strong>
                <p>{t("Trace every proposed action to a source passage.")}</p>
              </li>
              <li>
                <strong>{t("Decide")}</strong>
                <p>{t("Review the diagnosis before it is delivered.")}</p>
              </li>
            </ol>
          </div>
          <p className="hint">
            <ShieldCheck size={16} />{" "}
            {t(
              "Agents propose actions for your review. Remediation stays under your control. Analysis data remains private on this device.",
            )}
          </p>
        </aside>
      </div>
    </>
  );
}
export function DetailAnalyse() {
  useI18n();
  const { id } = useParams();
  const client = useQueryClient(),
    notifier = useToast(),
    navigate = useNavigate();
  const [decision, setDecision] = useState<"oui" | "non" | "supprimer" | null>(
      null,
    ),
    [accord, setAccord] = useState(false);
  const q = useQuery({
    queryKey: ["analyse", id],
    queryFn: () => api<Analyse>("/analyses/" + id),
    refetchInterval: (query) =>
      actifs.has(query.state.data?.statut || "") ? 5000 : false,
  });
  useEffect(() => {
    if (!actifs.has(q.data?.statut || "")) return;
    const flux = new EventSource(`/api/analyses/${id}/evenements`);
    flux.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data) as Analyse;
        client.setQueryData(["analyse", id], d);
        if (!actifs.has(d.statut)) flux.close();
      } catch {
        flux.close();
      }
    };
    flux.onerror = () => flux.close();
    return () => flux.close();
  }, [id, q.data?.statut, client]);
  const action = useMutation({
    mutationFn: (choix: string) =>
      api(
        `/analyses/${id}${choix === "supprimer" ? "" : choix === "annuler" ? "/annuler" : "/decision"}`,
        choix === "supprimer" ? "DELETE" : "POST",
        choix === "oui" || choix === "non"
          ? { approuver: choix === "oui" }
          : {},
      ),
    onSuccess: (_, choix) => {
      setDecision(null);
      setAccord(false);
      client.invalidateQueries();
      notifier(
        choix === "oui"
          ? t("Approval submitted.")
          : choix === "non"
            ? t("Rejection submitted.")
            : choix === "supprimer"
              ? t("Analysis deleted.")
              : t("Analysis cancelled."),
      );
      if (choix === "supprimer") navigate("/analyses");
    },
    onError: (e) => notifier(e.message, true),
  });
  if (q.isPending) return <Chargement />;
  if (q.error)
    return <Erreur erreur={q.error} recommencer={() => q.refetch()} />;
  const a = q.data!,
    r = a.rapport,
    d = apercu(r),
    attente = a.statut === "en_attente_humain",
    livre = a.statut === "complet" && r?.statut === "complet";
  const exportFichier = (format: string) => {
    location.assign(`/api/analyses/${id}/export?format=${format}`);
  };
  return (
    <>
      <Link to="/analyses" className="back-link">
        <ArrowLeft size={15} /> {t("All analyses")}
      </Link>
      <Titre
        surligne={
          a.mode === "operation" ? t("OPERATION") : t("SUPERVISED ANALYSIS")
        }
        titre={analysisTitle(a)}
        texte={t("Created {date} · {duration}", {
          date: date(a.cree_le),
          duration: a.duree_s
            ? t("{seconds} s runtime", {
                seconds: number(Math.round(a.duree_s)),
              })
            : t("Awaiting results"),
        })}
      >
        <Badge statut={a.statut} />
        <button className="btn" onClick={() => exportFichier("json")}>
          <ArrowDownToLine size={16} /> JSON
        </button>
        <button
          className="icon-button"
          onClick={() => setDecision("supprimer")}
          disabled={actifs.has(a.statut)}
          aria-label={t("Delete analysis")}
        >
          <Trash2 size={17} />
        </button>
      </Titre>
      {attente && (
        <div className="approval-banner">
          <ShieldCheck size={25} />
          <div>
            <strong>{t("Ready for your review")}</strong>
            <p>
              {t(
                "Review the proposed actions, supporting evidence and prerequisites before making your decision.",
              )}
            </p>
          </div>
          <button className="btn" onClick={() => setDecision("non")}>
            {t("Reject proposal")}
          </button>
          <button
            className="btn primary"
            onClick={() => {
              setAccord(false);
              setDecision("oui");
            }}
          >
            <Check size={17} /> {t("Approve proposal")}
          </button>
        </div>
      )}
      {actifs.has(a.statut) && (
        <div className="running-banner">
          <LoaderCircle className="spin" />
          <div>
            <strong>
              {a.statut === "en_file"
                ? t("Your run is queued.")
                : a.statut === "decision"
                  ? t("Applying your decision.")
                  : a.mode === "operation"
                    ? t("Your operation is running.")
                    : t("Your agents are investigating.")}
            </strong>
            <p>{t("The timeline updates as each step runs.")}</p>
          </div>
          <button
            className="btn"
            disabled={action.isPending}
            onClick={() => action.mutate("annuler")}
          >
            {t("Cancel run")}
          </button>
        </div>
      )}
      <div className="detail-grid">
        <div>
          {d ? (
            <section className="panel diagnostic-panel">
              <div className="panel-heading">
                <h2>
                  {livre ? t("Completed diagnosis") : t("Proposal for review")}
                </h2>
                <span className="tag">
                  {t("REPORTED CONFIDENCE:")}{" "}
                  {confidenceLabels[d.confiance] || t("Unspecified")}
                </span>
              </div>
              <div className="diagnostic-content">
                <h3>{t("Likely cause")}</h3>
                <p className="diagnostic-cause">{d.cause_probable}</p>
                <div className="source-card">
                  <BookOpen size={19} />
                  <div>
                    <small>{t("SUPPORTING SOURCE")}</small>
                    {d.runbook_source ? (
                      <Link
                        to={"/runbooks/" + encodeURIComponent(d.runbook_source)}
                      >
                        {d.runbook_source} <ExternalLink size={13} />
                      </Link>
                    ) : (
                      <strong>{t("No verified source")}</strong>
                    )}
                  </div>
                </div>
                <h3>
                  {!livre
                    ? t("Actions awaiting review")
                    : t("Recommended actions")}
                </h3>
                {d.actions_proposees?.length ? (
                  <ol className="actions-list">
                    {d.actions_proposees.map((t, i) => (
                      <li key={i}>
                        <span>{String(i + 1).padStart(2, "0")}</span>
                        <Markdown texte={t} />
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="muted">{t("No actions proposed.")}</p>
                )}
                {!!d.elements_manquants?.length && (
                  <div className="notice">
                    <strong>{t("Open questions & limitations")}</strong>
                    <ul>
                      {d.elements_manquants.map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <button
                  className="btn small"
                  onClick={() => exportFichier("md")}
                >
                  <FileText size={15} /> {t("Export Markdown")}
                </button>
              </div>
            </section>
          ) : (
            !actifs.has(a.statut) && (
              <section className="panel">
                <Vide
                  titre={
                    a.statut === "rejete_par_humain"
                      ? t("Proposal rejected")
                      : a.statut === "complet"
                        ? t("Operation completed")
                        : t("No diagnosis available")
                  }
                  texte={systemMessage(
                    r?.message || "",
                    t("This run has no approved diagnosis."),
                  )}
                />
              </section>
            )
          )}
          {r?.injections_signalees?.length ? (
            <section className="panel warning-panel">
              <h2>{t("Suspicious instructions detected")}</h2>
              <p>
                {t(
                  "Verify the source of the alert. Treat these instructions as untrusted content, not commands to execute.",
                )}
              </p>
              <ul>
                {r.injections_signalees.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          ) : null}
          {r?.actions_ecartees_sans_source?.length ? (
            <details className="panel disclosure">
              <summary>
                {t("Actions excluded without supporting evidence")}{" "}
                <span>{r.actions_ecartees_sans_source.length}</span>
              </summary>
              <ul>
                {r.actions_ecartees_sans_source.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
        <aside>
          <section className="panel">
            <div className="panel-heading">
              <h2>{t("Execution timeline")}</h2>
              <Radio size={17} />
            </div>
            <div className="timeline">
              <div>
                <span className="timeline-dot" />
                <strong>{t("Analysis created")}</strong>
                <small>{date(a.cree_le)}</small>
              </div>
              {a.evenements?.map((e, i) => (
                <div key={e.id}>
                  <span className="timeline-dot" />
                  <strong>
                    {{
                      demarrage: t("Engine started"),
                      modele: t("Local model call"),
                      outil: t("Tool call"),
                      termine: t("Run finished"),
                    }[e.stade] || t("Run updated")}
                  </strong>
                  <small>
                    {new Date(e.date).toLocaleTimeString(getLocale())}
                    {e.stade === "modele"
                      ? t(" · call {count}", {
                          count: number(
                            a
                              .evenements!.slice(0, i + 1)
                              .filter((s) => s.stade === "modele").length,
                          ),
                        })
                      : ""}
                  </small>
                </div>
              ))}
            </div>
          </section>
          <section className="panel metadata">
            <h2>{t("Run details")}</h2>
            <dl>
              <dt>{t("Routing")}</dt>
              <dd>
                <LockKeyhole size={13} /> {t("Private & local")}
              </dd>
              <dt>{t("Automatic remediation")}</dt>
              <dd>{t("Disabled")}</dd>
              <dt>{t("Tool calls")}</dt>
              <dd>{r?.outils_appeles?.length ?? "—"}</dd>
              <dt>{t("Model calls")}</dt>
              <dd>{r?.budget?.appels_llm ?? "—"}</dd>
            </dl>
            {r?.classification && (
              <div className="notice">
                <strong>
                  {t("Reported urgency:")} {r.classification.urgence}/5
                </strong>
                <p>{r.classification.justification}</p>
                <small>
                  {t("Model assessment. Verify against the observed facts.")}
                </small>
              </div>
            )}
            <span className="mono tiny muted break-all">{a.id}</span>
          </section>
          <RunUsage budget={r?.budget} />
        </aside>
      </div>
      {decision && (
        <Modal
          titre={
            decision === "oui"
              ? t("Approve proposal")
              : decision === "non"
                ? t("Reject proposal")
                : t("Delete analysis")
          }
          fermer={() => setDecision(null)}
        >
          <p>
            {decision === "oui"
              ? t(
                  "Approve this diagnosis for delivery. Remediation remains a separate, operator-led action.",
                )
              : decision === "non"
                ? t(
                    "Reject this proposal. Its recommended actions will not be delivered.",
                  )
                : t(
                    "Delete this report and its checkpoints from active storage. Existing backups follow their own retention policy.",
                  )}
          </p>
          {decision === "oui" && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={accord}
                onChange={(e) => setAccord(e.target.checked)}
              />{" "}
              {t(
                "I have reviewed the source, proposed actions and their prerequisites.",
              )}
            </label>
          )}
          <div className="form-actions">
            <button className="btn" onClick={() => setDecision(null)}>
              {t("Back")}
            </button>
            <button
              className={"btn " + (decision === "oui" ? "primary" : "danger")}
              disabled={action.isPending || (decision === "oui" && !accord)}
              onClick={() => action.mutate(decision)}
            >
              {action.isPending
                ? t("Processing…")
                : decision === "oui"
                  ? t("Approve proposal")
                  : decision === "non"
                    ? t("Reject proposal")
                    : t("Delete analysis")}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
