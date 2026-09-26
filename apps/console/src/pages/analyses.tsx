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
            <strong>{a.titre}</strong>
            <small>
              {date(a.cree_le)} ·{" "}
              {a.mode === "operation" ? "Opération" : "Analyse supervisée"}
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
        surligne={approbations ? "DÉCISION HUMAINE" : "ORCHESTRATION"}
        titre={
          approbations
            ? "Vous avez le dernier mot."
            : "Vos analyses, de bout en bout."
        }
        texte={
          approbations
            ? "Vérifiez la pertinence des sources et les conditions avant toute approbation."
            : "Suivez chaque exécution, consultez ses preuves et retrouvez son résultat."
        }
      >
        <Link to="/analyses/nouvelle" className="btn primary">
          <Plus size={18} /> Nouvelle analyse
        </Link>
      </Titre>
      <section className="panel">
        <div className="toolbar">
          <div className="search-input">
            <Search size={17} />
            <input
              aria-label="Rechercher une analyse"
              placeholder="Rechercher une analyse…"
              value={recherche}
              onChange={(e) => {
                setRecherche(e.target.value);
                setPage(1);
              }}
            />
          </div>
          {!approbations && (
            <select
              aria-label="Filtrer par état"
              value={filtre}
              onChange={(e) => {
                setFiltre(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Tous les états</option>
              {Object.entries(statuts).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          )}
          <span className="muted tiny">{q.data?.total ?? "—"} résultat(s)</span>
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
              approbations
                ? "Aucune décision en attente."
                : "Aucune analyse ici pour le moment."
            }
            texte={
              approbations
                ? "Les propositions du moteur apparaîtront ici lorsqu’elles seront prêtes à être examinées."
                : "Lancez une analyse ou adaptez votre recherche."
            }
          />
        )}
        <div className="pagination">
          <button
            className="btn small"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Précédent
          </button>
          <span>Page {page}</span>
          <button
            className="btn small"
            disabled={!q.data || page * 25 >= q.data.total}
            onClick={() => setPage(page + 1)}
          >
            Suivant
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
        surligne="NOUVELLE MISSION"
        titre="Donnez du sens à un signal."
        texte="Décrivez les faits observés. Le moteur confronte l’alerte à vos runbooks."
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
            Intitulé de l’analyse <span>Un repère pour la retrouver</span>
          </label>
          <input
            id="titre"
            required
            maxLength={100}
            placeholder="Ex. Connexions PostgreSQL saturées"
            value={titre}
            onChange={(e) => setTitre(e.target.value)}
          />
          <label htmlFor="alerte">
            Alerte & contexte{" "}
            <span>Symptômes, métriques et message d’erreur</span>
          </label>
          <textarea
            id="alerte"
            required
            minLength={1}
            maxLength={20000}
            rows={13}
            placeholder="Décrivez ce qui se passe, depuis quand et les vérifications déjà effectuées…"
            value={alerte}
            onChange={(e) => setAlerte(e.target.value)}
          />
          <div className="field-foot">
            <span>
              <LockKeyhole size={13} /> Traitement local uniquement
            </span>
            <span>{alerte.length.toLocaleString("fr-FR")} / 20 000</span>
          </div>
          {mutation.error && <Erreur erreur={mutation.error} />}
          <div className="form-actions">
            <Link className="btn" to="/analyses">
              Annuler
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
              Lancer l’analyse
            </button>
          </div>
        </form>
        <aside className="form-aside">
          <div className="panel instruction-card">
            <span className="tile-icon">
              <GitBranch size={24} />
            </span>
            <h2>Un parcours supervisé.</h2>
            <ol className="numbered-steps">
              <li>
                <strong>Comprendre</strong>
                <p>
                  Extraire les symptômes et repérer les instructions suspectes.
                </p>
              </li>
              <li>
                <strong>Confronter</strong>
                <p>Classer l’alerte et consulter les procédures disponibles.</p>
              </li>
              <li>
                <strong>Vérifier</strong>
                <p>Rattacher les actions à des passages réellement lus.</p>
              </li>
              <li>
                <strong>Décider</strong>
                <p>Vous soumettre le diagnostic avant sa livraison.</p>
              </li>
            </ol>
          </div>
          <p className="hint">
            <ShieldCheck size={16} /> L’agent propose. Il n’exécute aucune
            remédiation. Les contenus dérivés restent confidentiels et sont
            conservés localement.
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
          ? "Approbation transmise."
          : choix === "non"
            ? "Refus transmis."
            : choix === "supprimer"
              ? "Analyse supprimée."
              : "Analyse annulée.",
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
        <ArrowLeft size={15} /> Toutes les analyses
      </Link>
      <Titre
        surligne={a.mode === "operation" ? "OPÉRATION" : "ANALYSE SUPERVISÉE"}
        titre={a.titre}
        texte={`Créée le ${date(a.cree_le)} · ${a.duree_s ? Math.round(a.duree_s) + " s de calcul" : "En attente de résultat"}`}
      >
        <Badge statut={a.statut} />
        <button className="btn" onClick={() => exportFichier("json")}>
          <ArrowDownToLine size={16} /> JSON
        </button>
        <button
          className="icon-button"
          onClick={() => setDecision("supprimer")}
          disabled={actifs.has(a.statut)}
          aria-label="Supprimer l’analyse"
        >
          <Trash2 size={17} />
        </button>
      </Titre>
      {attente && (
        <div className="approval-banner">
          <ShieldCheck size={25} />
          <div>
            <strong>Cette proposition attend votre regard.</strong>
            <p>
              Les actions sont un aperçu soumis à validation. Vérifiez leur
              pertinence et leurs préconditions.
            </p>
          </div>
          <button className="btn" onClick={() => setDecision("non")}>
            Refuser
          </button>
          <button
            className="btn primary"
            onClick={() => {
              setAccord(false);
              setDecision("oui");
            }}
          >
            <Check size={17} /> Examiner & approuver
          </button>
        </div>
      )}
      {actifs.has(a.statut) && (
        <div className="running-banner">
          <LoaderCircle className="spin" />
          <div>
            <strong>
              {a.statut === "en_file"
                ? "Votre analyse est dans la file."
                : a.statut === "decision"
                  ? "Votre décision est en cours de traitement."
                  : "Le moteur travaille sur votre analyse."}
            </strong>
            <p>Les étapes ci-dessous reflètent l’exécution réelle.</p>
          </div>
          <button
            className="btn"
            disabled={action.isPending}
            onClick={() => action.mutate("annuler")}
          >
            Annuler l’exécution
          </button>
        </div>
      )}
      <div className="detail-grid">
        <div>
          {d ? (
            <section className="panel diagnostic-panel">
              <div className="panel-heading">
                <h2>{livre ? "Diagnostic livré" : "Proposition à examiner"}</h2>
                <span className="tag">CONFIANCE DÉCLARÉE : {d.confiance}</span>
              </div>
              <div className="diagnostic-content">
                <h3>Cause probable</h3>
                <p className="diagnostic-cause">{d.cause_probable}</p>
                <div className="source-card">
                  <BookOpen size={19} />
                  <div>
                    <small>SOURCE DU DIAGNOSTIC</small>
                    {d.runbook_source ? (
                      <Link
                        to={"/runbooks/" + encodeURIComponent(d.runbook_source)}
                      >
                        {d.runbook_source} <ExternalLink size={13} />
                      </Link>
                    ) : (
                      <strong>Aucune source vérifiée</strong>
                    )}
                  </div>
                </div>
                <h3>
                  {!livre
                    ? "Actions soumises à validation"
                    : "Actions proposées à l’opérateur"}
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
                  <p className="muted">Aucune action proposée.</p>
                )}
                {!!d.elements_manquants?.length && (
                  <div className="notice">
                    <strong>Réserves & éléments à confirmer</strong>
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
                  <FileText size={15} /> Exporter en Markdown
                </button>
              </div>
            </section>
          ) : (
            !actifs.has(a.statut) && (
              <section className="panel">
                <Vide
                  titre={
                    a.statut === "rejete_par_humain"
                      ? "Proposition refusée."
                      : a.statut === "complet"
                        ? "Opération terminée."
                        : "Aucun diagnostic livré."
                  }
                  texte={
                    r?.message ||
                    "Cette exécution ne contient pas de diagnostic approuvé."
                  }
                />
              </section>
            )
          )}
          {r?.injections_signalees?.length ? (
            <section className="panel warning-panel">
              <h2>Instructions suspectes signalées</h2>
              <p>
                Confirmez l’origine de l’alerte. Ces instructions ne sont pas
                des commandes à suivre.
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
                Actions écartées faute de source{" "}
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
              <h2>Fil d’exécution</h2>
              <Radio size={17} />
            </div>
            <div className="timeline">
              <div>
                <span className="timeline-dot" />
                <strong>Analyse créée</strong>
                <small>{date(a.cree_le)}</small>
              </div>
              {a.evenements?.map((e, i) => (
                <div key={e.id}>
                  <span className="timeline-dot" />
                  <strong>
                    {{
                      demarrage: "Moteur démarré",
                      modele: "Appel au modèle local",
                      outil: "Consultation d’un outil",
                      termine: "Exécution terminée",
                    }[e.stade] || e.stade}
                  </strong>
                  <small>
                    {new Date(e.date).toLocaleTimeString("fr-FR")}
                    {e.stade === "modele"
                      ? ` · appel ${a.evenements!.slice(0, i + 1).filter((s) => s.stade === "modele").length}`
                      : ""}
                  </small>
                </div>
              ))}
            </div>
          </section>
          <section className="panel metadata">
            <h2>Cadre d’exécution</h2>
            <dl>
              <dt>Routage</dt>
              <dd>
                <LockKeyhole size={13} /> Local confidentiel
              </dd>
              <dt>Remédiation automatique</dt>
              <dd>Désactivée</dd>
              <dt>Outils appelés</dt>
              <dd>{r?.outils_appeles?.length ?? "—"}</dd>
              <dt>Appels au modèle</dt>
              <dd>{r?.budget?.appels_llm ?? "—"}</dd>
              <dt>Coût API déclaré</dt>
              <dd>
                {r?.budget?.cout_usd !== undefined
                  ? r.budget.cout_usd.toFixed(4) + " $"
                  : "—"}
              </dd>
            </dl>
            {r?.classification && (
              <div className="notice">
                <strong>Urgence déclarée : {r.classification.urgence}/5</strong>
                <p>{r.classification.justification}</p>
                <small>Classification du modèle, à confronter aux faits.</small>
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
              ? "Approuver la proposition"
              : decision === "non"
                ? "Refuser la proposition"
                : "Supprimer cette analyse"
          }
          fermer={() => setDecision(null)}
        >
          <p>
            {decision === "oui"
              ? "L’approbation autorise la livraison du diagnostic. Aucune commande de remédiation ne sera exécutée."
              : decision === "non"
                ? "Le diagnostic sera refusé et aucune action ne sera livrée."
                : "Le rapport et ses checkpoints seront supprimés du stockage actif. Les sauvegardes suivent leur propre rétention."}
          </p>
          {decision === "oui" && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={accord}
                onChange={(e) => setAccord(e.target.checked)}
              />{" "}
              J’ai vérifié la source, la pertinence des actions et leurs
              préconditions.
            </label>
          )}
          <div className="form-actions">
            <button className="btn" onClick={() => setDecision(null)}>
              Retour
            </button>
            <button
              className={"btn " + (decision === "oui" ? "primary" : "danger")}
              disabled={action.isPending || (decision === "oui" && !accord)}
              onClick={() => action.mutate(decision)}
            >
              {action.isPending
                ? "Traitement…"
                : decision === "oui"
                  ? "Confirmer l’approbation"
                  : decision === "non"
                    ? "Confirmer le refus"
                    : "Supprimer"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
