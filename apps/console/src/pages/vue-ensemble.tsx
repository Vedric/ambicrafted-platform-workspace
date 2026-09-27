import { t, useI18n, number, countLabel } from "../i18n";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  CheckCheck,
  Compass,
  ChevronRight,
  GitBranch,
  Plus,
  Radio,
  ShieldCheck,
  Sparkles,
  Workflow,
  Wrench,
} from "lucide-react";
import { api, serviceName, type Liste, type Vue } from "../api";
import { Erreur, Chargement, Vide, Titre, Orbit } from "../ui";
import { ListeAnalyses } from "./analyses";
import { Insights } from "../Insights";

export function VueEnsemble() {
  useI18n();
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
  return (
    <>
      <Titre
        surligne={t("MISSION CONTROL")}
        titre={t("Your intelligence, in motion.")}
        texte={t(
          "One command center. Your knowledge, your agents, your decisions.",
        )}
      >
        <Link className="btn primary" to="/missions">
          <Compass size={18} /> {t("Launch a mission")}
        </Link>
      </Titre>
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="tag">
            <span className="live-dot" />{" "}
            {t("MISSION CONTROL / LOCAL INTELLIGENCE")}
          </span>
          <h2>
            {t("Signals become clarity.")}
            <br />
            <span>{t("You stay in command.")}</span>
          </h2>
          <p>
            {t("Your agents connect the signals and the knowledge.")}
            <br />
            {t("You decide what comes next, with the evidence in hand.")}
          </p>
          <div className="hero-actions">
            <Link to="/assistant" className="btn primary">
              <AudioLines size={18} /> {t("Talk to AURA")}{" "}
              <ArrowRight size={17} />
            </Link>
            <Link to="/agents" className="text-button">
              {t("Explore the agents")} <ChevronRight size={16} />
            </Link>
          </div>
          <div className="hero-foot">
            <ShieldCheck size={15} /> {t("Private by design")} <span>·</span>
            <GitBranch size={15} /> {t("Human decisions")}
          </div>
        </div>
        <Orbit petit />
      </section>
      <div className="workspace-telemetry" aria-label={t("Workspace status")}>
        <span>
          <i
            className={"health-dot " + (d.sante.ok ? "healthy" : "unhealthy")}
          />
          {d.sante.ok
            ? t("Services responding")
            : t("Service attention needed")}
        </span>
        <span>
          <Radio size={13} />{" "}
          {t("{count} active / queued", { count: number(enCours) })}
        </span>
        <span>
          <BookOpen size={13} /> {countLabel(d.runbooks, "source")}
        </span>
        <Link to="/preparation">
          {t("Workspace readiness")} <ArrowRight size={13} />
        </Link>
      </div>
      <div className="stats-grid">
        {[
          {
            label: t("Saved runs"),
            valeur: d.total,
            icon: Workflow,
            note: t("Saved on this device"),
          },
          {
            label: t("Active & queued"),
            valeur: enCours,
            icon: Radio,
            note: t("Controlled execution"),
          },
          {
            label: t("Awaiting your review"),
            valeur: d.statuts.en_attente_humain || 0,
            icon: ShieldCheck,
            note: t("Decisions to approve"),
          },
          {
            label: t("Available runbooks"),
            valeur: d.runbooks,
            icon: BookOpen,
            note:
              d.sante.index.points === undefined
                ? "—"
                : countLabel(d.sante.index.points, "passage"),
          },
        ].map((s, index) => (
          <div
            className="stat-card"
            key={s.label}
            style={{ animationDelay: `${index * 65}ms` }}
          >
            <div>
              <span>{s.label}</span>
              <s.icon size={18} />
            </div>
            <strong>{number(s.valeur, { minimumIntegerDigits: 2 })}</strong>
            <small>{s.note}</small>
          </div>
        ))}
      </div>
      <div className="mission-ribbon">
        <div>
          <span className="eyebrow">{t("WHAT WILL YOU INVESTIGATE?")}</span>
          <strong>{t("Start with a purpose. Follow the evidence.")}</strong>
        </div>
        <Link to="/analyses/nouvelle?mission=incident">
          {t("Incident triage")} <ArrowRight size={15} />
        </Link>
        <Link to="/analyses/nouvelle?mission=latency">
          {t("Performance")} <ArrowRight size={15} />
        </Link>
        <Link to="/missions">
          {t("All missions")} <Compass size={15} />
        </Link>
      </div>
      <Insights data={d} updatedAt={q.dataUpdatedAt} />
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>{t("Recent analyses")}</h2>
            <Link to="/analyses">
              {t("View all")} <ArrowRight size={15} />
            </Link>
          </div>
          {recent.error ? (
            <Erreur erreur={recent.error} />
          ) : !recent.data?.elements.length ? (
            <Vide
              titre={t("A fresh perspective starts here.")}
              texte={t(
                "Bring an alert. Your agents consult the runbooks before proposing a diagnosis.",
              )}
            >
              <Link className="btn" to="/analyses/nouvelle">
                <Plus size={16} /> {t("Run analysis")}
              </Link>
            </Vide>
          ) : (
            <ListeAnalyses elements={recent.data.elements} />
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>{t("System health")}</h2>
            <Link to="/sante" aria-label={t("View system health")}>
              <ArrowRight size={17} />
            </Link>
          </div>
          <div className="service-list">
            {d.sante.services.map((s) => (
              <div key={s.id}>
                <span
                  className={"health-dot " + (s.ok ? "healthy" : "unhealthy")}
                />
                <span>{serviceName(s.id)}</span>
                <small>{s.ok ? t("Online") : t("Needs attention")}</small>
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
                ? t("All services responding")
                : t("Some services need attention")}
            </span>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>{t("Ready for your next move")}</h2>
            <Sparkles size={17} />
          </div>
          <div className="quick-links">
            <Link to="/runbooks">
              <BookOpen />
              <div>
                <strong>{t("Your knowledge base")}</strong>
                <span>{t("Explore and enrich your runbooks")}</span>
              </div>
              <ChevronRight />
            </Link>
            <Link to="/approbations">
              <CheckCheck />
              <div>
                <strong>{t("Stay in control")}</strong>
                <span>{t("Review your agents’ proposals")}</span>
              </div>
              <ChevronRight />
            </Link>
            <Link to="/operations">
              <Wrench />
              <div>
                <strong>{t("Keep things running")}</strong>
                <span>{t("Verify, back up, reindex")}</span>
              </div>
              <ChevronRight />
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}
