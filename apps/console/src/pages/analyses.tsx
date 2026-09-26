import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
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

const confidenceLabels: Record<string, string> = {
  haute: "High",
  moyenne: "Medium",
  faible: "Low",
};
const operationTitles: Record<string, string> = {
  verifier: "Platform verification",
  indexer: "Runbook reindexing",
  sauvegarder: "Platform backup",
  "tester-restauration": "Backup restoration test",
};
const analysisTitle = (analysis: Analyse) =>
  analysis.mode === "operation"
    ? operationTitles[analysis.options.operation || ""] || "Platform operation"
    : analysis.titre;

export function ListeAnalyses({ elements }: { elements: Analyse[] }) {
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
              {a.mode === "operation" ? "Operation" : "Supervised analysis"}
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
        surligne={approbations ? "HUMAN OVERSIGHT" : "ORCHESTRATION"}
        titre={approbations ? "Approvals" : "Analyses"}
        texte={
          approbations
            ? "Review the evidence and prerequisites before approving a proposal."
            : "Follow every run from the first signal to a reviewed result."
        }
      >
        <Link to="/analyses/nouvelle" className="btn primary">
          <Plus size={18} /> New analysis
        </Link>
      </Titre>
      <section className="panel">
        <div className="toolbar">
          <div className="search-input">
            <Search size={17} />
            <input
              aria-label="Search analyses"
              placeholder="Search analyses…"
              value={recherche}
              onChange={(e) => {
                setRecherche(e.target.value);
                setPage(1);
              }}
            />
          </div>
          {!approbations && (
            <select
              aria-label="Filter by status"
              value={filtre}
              onChange={(e) => {
                setFiltre(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All statuses</option>
              {Object.entries(statuts).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          )}
          <span className="muted tiny">
            {q.data?.total ?? "—"} {q.data?.total === 1 ? "result" : "results"}
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
            titre={approbations ? "No pending approvals" : "No analyses yet"}
            texte={
              approbations
                ? "Proposals appear here when they are ready for your review."
                : "Start an analysis or adjust your search."
            }
          />
        )}
        <div className="pagination">
          <button
            className="btn small"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <span>Page {page}</span>
          <button
            className="btn small"
            disabled={!q.data || page * 25 >= q.data.total}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      </section>
    </>
  );
}
export function NouvelleAnalyse() {
  const [titre, setTitre] = useState(""),
    [alerte, setAlerte] = useState("");
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
        surligne="NEW ANALYSIS"
        titre="New analysis"
        texte="Describe what you observed. Your agents will investigate against your runbooks."
      />
      <div className="form-grid">
        <form
          className="panel form-panel"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <label htmlFor="titre">
            Analysis title <span>A clear name for this investigation</span>
          </label>
          <input
            id="titre"
            required
            maxLength={100}
            placeholder="e.g. PostgreSQL connection pool exhausted"
            value={titre}
            onChange={(e) => setTitre(e.target.value)}
          />
          <label htmlFor="alerte">
            Alert & context <span>Symptoms, metrics and error messages</span>
          </label>
          <textarea
            id="alerte"
            required
            minLength={1}
            maxLength={20000}
            rows={13}
            placeholder="Describe the issue, when it started and what you have already checked…"
            value={alerte}
            onChange={(e) => setAlerte(e.target.value)}
          />
          <div className="field-foot">
            <span>
              <LockKeyhole size={13} /> Processed locally
            </span>
            <span>{alerte.length.toLocaleString("en-US")} / 20,000</span>
          </div>
          {mutation.error && <Erreur erreur={mutation.error} />}
          <div className="form-actions">
            <Link className="btn" to="/analyses">
              Cancel
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
              Run analysis
            </button>
          </div>
        </form>
        <aside className="form-aside">
          <div className="panel instruction-card">
            <span className="tile-icon">
              <GitBranch size={24} />
            </span>
            <h2>Evidence at every step.</h2>
            <ol className="numbered-steps">
              <li>
                <strong>Understand</strong>
                <p>Extract symptoms and flag suspicious instructions.</p>
              </li>
              <li>
                <strong>Investigate</strong>
                <p>Classify the alert and consult relevant procedures.</p>
              </li>
              <li>
                <strong>Verify</strong>
                <p>Trace every proposed action to a source passage.</p>
              </li>
              <li>
                <strong>Decide</strong>
                <p>Review the diagnosis before it is delivered.</p>
              </li>
            </ol>
          </div>
          <p className="hint">
            <ShieldCheck size={16} /> Agents propose actions for your review.
            Remediation stays under your control. Analysis data remains private
            on this device.
          </p>
        </aside>
      </div>
    </>
  );
}
export function DetailAnalyse() {
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
          ? "Approval submitted."
          : choix === "non"
            ? "Rejection submitted."
            : choix === "supprimer"
              ? "Analysis deleted."
              : "Analysis cancelled.",
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
        <ArrowLeft size={15} /> All analyses
      </Link>
      <Titre
        surligne={a.mode === "operation" ? "OPERATION" : "SUPERVISED ANALYSIS"}
        titre={analysisTitle(a)}
        texte={`Created ${date(a.cree_le)} · ${a.duree_s ? Math.round(a.duree_s) + " s runtime" : "Awaiting results"}`}
      >
        <Badge statut={a.statut} />
        <button className="btn" onClick={() => exportFichier("json")}>
          <ArrowDownToLine size={16} /> JSON
        </button>
        <button
          className="icon-button"
          onClick={() => setDecision("supprimer")}
          disabled={actifs.has(a.statut)}
          aria-label="Delete analysis"
        >
          <Trash2 size={17} />
        </button>
      </Titre>
      {attente && (
        <div className="approval-banner">
          <ShieldCheck size={25} />
          <div>
            <strong>Ready for your review</strong>
            <p>
              Review the proposed actions, supporting evidence and prerequisites
              before making your decision.
            </p>
          </div>
          <button className="btn" onClick={() => setDecision("non")}>
            Reject proposal
          </button>
          <button
            className="btn primary"
            onClick={() => {
              setAccord(false);
              setDecision("oui");
            }}
          >
            <Check size={17} /> Approve proposal
          </button>
        </div>
      )}
      {actifs.has(a.statut) && (
        <div className="running-banner">
          <LoaderCircle className="spin" />
          <div>
            <strong>
              {a.statut === "en_file"
                ? "Your run is queued."
                : a.statut === "decision"
                  ? "Applying your decision."
                  : a.mode === "operation"
                    ? "Your operation is running."
                    : "Your agents are investigating."}
            </strong>
            <p>The timeline updates as each step runs.</p>
          </div>
          <button
            className="btn"
            disabled={action.isPending}
            onClick={() => action.mutate("annuler")}
          >
            Cancel run
          </button>
        </div>
      )}
      <div className="detail-grid">
        <div>
          {d ? (
            <section className="panel diagnostic-panel">
              <div className="panel-heading">
                <h2>{livre ? "Completed diagnosis" : "Proposal for review"}</h2>
                <span className="tag">
                  REPORTED CONFIDENCE:{" "}
                  {confidenceLabels[d.confiance] || "Unspecified"}
                </span>
              </div>
              <div className="diagnostic-content">
                <h3>Likely cause</h3>
                <p className="diagnostic-cause">{d.cause_probable}</p>
                <div className="source-card">
                  <BookOpen size={19} />
                  <div>
                    <small>SUPPORTING SOURCE</small>
                    {d.runbook_source ? (
                      <Link
                        to={"/runbooks/" + encodeURIComponent(d.runbook_source)}
                      >
                        {d.runbook_source} <ExternalLink size={13} />
                      </Link>
                    ) : (
                      <strong>No verified source</strong>
                    )}
                  </div>
                </div>
                <h3>
                  {!livre ? "Actions awaiting review" : "Recommended actions"}
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
                  <p className="muted">No actions proposed.</p>
                )}
                {!!d.elements_manquants?.length && (
                  <div className="notice">
                    <strong>Open questions & limitations</strong>
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
                  <FileText size={15} /> Export Markdown
                </button>
              </div>
            </section>
          ) : (
            !actifs.has(a.statut) && (
              <section className="panel">
                <Vide
                  titre={
                    a.statut === "rejete_par_humain"
                      ? "Proposal rejected"
                      : a.statut === "complet"
                        ? "Operation completed"
                        : "No diagnosis available"
                  }
                  texte={systemMessage(
                    r?.message || "",
                    "This run has no approved diagnosis.",
                  )}
                />
              </section>
            )
          )}
          {r?.injections_signalees?.length ? (
            <section className="panel warning-panel">
              <h2>Suspicious instructions detected</h2>
              <p>
                Verify the source of the alert. Treat these instructions as
                untrusted content, not commands to execute.
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
                Actions excluded without supporting evidence{" "}
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
              <h2>Execution timeline</h2>
              <Radio size={17} />
            </div>
            <div className="timeline">
              <div>
                <span className="timeline-dot" />
                <strong>Analysis created</strong>
                <small>{date(a.cree_le)}</small>
              </div>
              {a.evenements?.map((e, i) => (
                <div key={e.id}>
                  <span className="timeline-dot" />
                  <strong>
                    {{
                      demarrage: "Engine started",
                      modele: "Local model call",
                      outil: "Tool call",
                      termine: "Run finished",
                    }[e.stade] || "Run updated"}
                  </strong>
                  <small>
                    {new Date(e.date).toLocaleTimeString("en-US")}
                    {e.stade === "modele"
                      ? ` · call ${a.evenements!.slice(0, i + 1).filter((s) => s.stade === "modele").length}`
                      : ""}
                  </small>
                </div>
              ))}
            </div>
          </section>
          <section className="panel metadata">
            <h2>Run details</h2>
            <dl>
              <dt>Routing</dt>
              <dd>
                <LockKeyhole size={13} /> Private & local
              </dd>
              <dt>Automatic remediation</dt>
              <dd>Disabled</dd>
              <dt>Tool calls</dt>
              <dd>{r?.outils_appeles?.length ?? "—"}</dd>
              <dt>Model calls</dt>
              <dd>{r?.budget?.appels_llm ?? "—"}</dd>
              <dt>Reported API cost</dt>
              <dd>
                {r?.budget?.cout_usd !== undefined
                  ? "$" + r.budget.cout_usd.toFixed(4)
                  : "—"}
              </dd>
            </dl>
            {r?.classification && (
              <div className="notice">
                <strong>Reported urgency: {r.classification.urgence}/5</strong>
                <p>{r.classification.justification}</p>
                <small>
                  Model assessment. Verify against the observed facts.
                </small>
              </div>
            )}
            <span className="mono tiny muted break-all">{a.id}</span>
          </section>
        </aside>
      </div>
      {decision && (
        <Modal
          titre={
            decision === "oui"
              ? "Approve proposal"
              : decision === "non"
                ? "Reject proposal"
                : "Delete analysis"
          }
          fermer={() => setDecision(null)}
        >
          <p>
            {decision === "oui"
              ? "Approve this diagnosis for delivery. Remediation remains a separate, operator-led action."
              : decision === "non"
                ? "Reject this proposal. Its recommended actions will not be delivered."
                : "Delete this report and its checkpoints from active storage. Existing backups follow their own retention policy."}
          </p>
          {decision === "oui" && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={accord}
                onChange={(e) => setAccord(e.target.checked)}
              />{" "}
              I have reviewed the source, proposed actions and their
              prerequisites.
            </label>
          )}
          <div className="form-actions">
            <button className="btn" onClick={() => setDecision(null)}>
              Back
            </button>
            <button
              className={"btn " + (decision === "oui" ? "primary" : "danger")}
              disabled={action.isPending || (decision === "oui" && !accord)}
              onClick={() => action.mutate(decision)}
            >
              {action.isPending
                ? "Processing…"
                : decision === "oui"
                  ? "Approve proposal"
                  : decision === "non"
                    ? "Reject proposal"
                    : "Delete analysis"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
