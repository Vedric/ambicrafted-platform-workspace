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
import { api, serviceName, type Liste, type Vue } from "../api";
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
        titre="A clearer view. A smarter move."
        texte="Your signals, your agents, your next decision."
      >
        <Link className="btn primary" to="/analyses/nouvelle">
          <Plus size={18} /> New analysis
        </Link>
      </Titre>
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="tag">
            <span className="live-dot" /> YOUR PRIVATE INTELLIGENCE
          </span>
          <h2>
            Less noise.
            <br />
            <span>More perspective.</span>
          </h2>
          <p>
            Your agents connect the signals and the knowledge.
            <br />
            You decide what comes next, with the evidence in hand.
          </p>
          <div className="hero-actions">
            <Link to="/assistant" className="btn primary">
              <AudioLines size={18} /> Meet your assistant{" "}
              <ArrowRight size={17} />
            </Link>
            <Link to="/agents" className="text-button">
              Explore the agents <ChevronRight size={16} />
            </Link>
          </div>
          <div className="hero-foot">
            <ShieldCheck size={15} /> Private by design <span>·</span>
            <GitBranch size={15} /> Human decisions
          </div>
        </div>
        <Orbit petit />
      </section>
      <div className="stats-grid">
        {[
          {
            label: "Total analyses",
            valeur: d.total,
            icon: Workflow,
            note: "Saved on this device",
          },
          {
            label: "Active & queued",
            valeur: enCours,
            icon: Radio,
            note: "Controlled execution",
          },
          {
            label: "Awaiting your review",
            valeur: d.statuts.en_attente_humain || 0,
            icon: ShieldCheck,
            note: "Decisions to approve",
          },
          {
            label: "Available runbooks",
            valeur: d.runbooks,
            icon: BookOpen,
            note: `${d.sante.index.points ?? "—"} indexed passages`,
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
            <strong>{s.valeur.toString().padStart(2, "0")}</strong>
            <small>{s.note}</small>
          </div>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>Recent analyses</h2>
            <Link to="/analyses">
              View all <ArrowRight size={15} />
            </Link>
          </div>
          {recent.error ? (
            <Erreur erreur={recent.error} />
          ) : !recent.data?.elements.length ? (
            <Vide
              titre="A fresh perspective starts here."
              texte="Bring an alert. Your agents consult the runbooks before proposing a diagnosis."
            >
              <Link className="btn" to="/analyses/nouvelle">
                <Plus size={16} /> Run analysis
              </Link>
            </Vide>
          ) : (
            <ListeAnalyses elements={recent.data.elements} />
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>System health</h2>
            <Link to="/sante" aria-label="View system health">
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
                <small>{s.ok ? "Online" : "Needs attention"}</small>
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
                ? "All services responding"
                : "Some services need attention"}
            </span>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>Your activity</h2>
            <span className="muted tiny">Last 14 days · UTC</span>
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
            <h2>Ready for your next move</h2>
            <Sparkles size={17} />
          </div>
          <div className="quick-links">
            <Link to="/runbooks">
              <BookOpen />
              <div>
                <strong>Your knowledge base</strong>
                <span>Explore and enrich your runbooks</span>
              </div>
              <ChevronRight />
            </Link>
            <Link to="/approbations">
              <CheckCheck />
              <div>
                <strong>Stay in control</strong>
                <span>Review your agents’ proposals</span>
              </div>
              <ChevronRight />
            </Link>
            <Link to="/operations">
              <Wrench />
              <div>
                <strong>Keep things running</strong>
                <span>Verify, back up, reindex</span>
              </div>
              <ChevronRight />
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}
