import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  CheckCheck,
  ChevronRight,
  GitBranch,
  Plus,
  Radio,
  ShieldCheck,
  Sparkles,
  Workflow,
  Wrench,
} from "lucide-react";
import { api, type Liste, type Vue } from "../api";
import { Erreur, Chargement, Vide, Titre, Orbit } from "../ui";
import { ListeAnalyses } from "./analyses";

export function VueEnsemble() {
  const q = useQuery({
    queryKey: ["vue"],
    queryFn: () => api<Vue>("/vue-ensemble"),
    refetchInterval: 15000,
  });
  const recent = useQuery({
    queryKey: ["recentes"],
    queryFn: () => api<Liste>("/analyses?taille=4"),
    refetchInterval: 10000,
  });
  if (q.isPending) return <Chargement />;
  if (q.error)
    return <Erreur erreur={q.error} recommencer={() => q.refetch()} />;
  const d = q.data!,
    enCours =
      (d.statuts.en_cours || 0) +
      (d.statuts.en_file || 0) +
      (d.statuts.decision || 0);
  const max = Math.max(1, ...d.activite.map((a) => a.total));
  return (
    <>
      <Titre
        surligne="MISSION CONTROL"
        titre="Une vision claire. Une action juste."
        texte="Votre espace pour comprendre, orchestrer et décider."
      >
        <Link className="btn primary" to="/analyses/nouvelle">
          <Plus size={18} /> Nouvelle analyse
        </Link>
      </Titre>
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="tag">
            <span className="live-dot" /> VOTRE INTELLIGENCE LOCALE
          </span>
          <h2>
            La complexité s’arrête ici.
            <br />
            <span>Votre expertise prend le relais.</span>
          </h2>
          <p>
            Vos agents explorent les signaux et les runbooks.
            <br />
            Vous validez les décisions, preuves à l’appui.
          </p>
          <div className="hero-actions">
            <Link to="/assistant" className="btn primary">
              <AudioLines size={18} /> Parler à l’assistante{" "}
              <ArrowRight size={17} />
            </Link>
            <Link to="/agents" className="text-button">
              Explorer les agents <ChevronRight size={16} />
            </Link>
          </div>
          <div className="hero-foot">
            <ShieldCheck size={15} /> Confidentiel par conception <span>·</span>
            <GitBranch size={15} /> Validation humaine
          </div>
        </div>
        <Orbit petit />
      </section>
      <div className="stats-grid">
        {[
          {
            label: "Analyses enregistrées",
            valeur: d.total,
            icon: Workflow,
            note: "Sur ce poste",
          },
          {
            label: "En cours & en file",
            valeur: enCours,
            icon: Radio,
            note: "Exécution maîtrisée",
          },
          {
            label: "À votre attention",
            valeur: d.statuts.en_attente_humain || 0,
            icon: ShieldCheck,
            note: "Décisions à valider",
          },
          {
            label: "Runbooks disponibles",
            valeur: d.runbooks,
            icon: BookOpen,
            note: `${d.sante.index.points ?? "—"} fragments indexés`,
          },
        ].map((s) => (
          <div className="stat-card" key={s.label}>
            <div>
              <span>{s.label}</span>
              <s.icon size={18} />
            </div>
            <strong>{s.valeur.toString().padStart(2, "0")}</strong>
            <small>{s.note}</small>
          </div>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>Dernières analyses</h2>
            <Link to="/analyses">
              Tout voir <ArrowRight size={15} />
            </Link>
          </div>
          {recent.error ? (
            <Erreur erreur={recent.error} />
          ) : !recent.data?.elements.length ? (
            <Vide
              titre="Votre prochaine décision commence ici."
              texte="Soumettez une alerte. Le moteur consulte vos procédures avant de proposer un diagnostic."
            >
              <Link className="btn" to="/analyses/nouvelle">
                <Plus size={16} /> Lancer une analyse
              </Link>
            </Vide>
          ) : (
            <ListeAnalyses elements={recent.data.elements} />
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>Santé de l’écosystème</h2>
            <Link to="/sante" aria-label="Voir la santé détaillée">
              <ArrowRight size={17} />
            </Link>
          </div>
          <div className="service-list">
            {d.sante.services.map((s) => (
              <div key={s.id}>
                <span
                  className={"health-dot " + (s.ok ? "healthy" : "unhealthy")}
                />
                <span>{s.nom}</span>
                <small>{s.ok ? "Disponible" : "À vérifier"}</small>
              </div>
            ))}
          </div>
          <div className="panel-bottom">
            <span
              className={
                "badge " + (d.sante.ok ? "status-complet" : "status-erreur")
              }
            >
              <i />
              {d.sante.ok
                ? "Tous les services répondent"
                : "Une vérification est nécessaire"}
            </span>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>Votre activité</h2>
            <span className="muted tiny">14 derniers jours · UTC</span>
          </div>
          <div
            className="activity-chart"
            role="img"
            aria-label={d.activite
              .map((a) => `${a.date} : ${a.total} analyses`)
              .join(", ")}
          >
            {d.activite.map((a) => (
              <div key={a.date} title={`${a.date} · ${a.total} analyses`}>
                <span
                  style={{
                    height: `${Math.max(3, (a.total / max) * 100)}%`,
                    opacity: a.total ? 1 : 0.2,
                  }}
                />
                <small>{a.date.slice(8)}</small>
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>À portée de main</h2>
            <Sparkles size={17} />
          </div>
          <div className="quick-links">
            <Link to="/runbooks">
              <BookOpen />
              <div>
                <strong>Votre mémoire opérationnelle</strong>
                <span>Lire et enrichir les procédures</span>
              </div>
              <ChevronRight />
            </Link>
            <Link to="/approbations">
              <CheckCheck />
              <div>
                <strong>Garder la main</strong>
                <span>Examiner les propositions des agents</span>
              </div>
              <ChevronRight />
            </Link>
            <Link to="/operations">
              <Wrench />
              <div>
                <strong>Prendre soin de la plateforme</strong>
                <span>Vérifier, sauvegarder, réindexer</span>
              </div>
              <ChevronRight />
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}
