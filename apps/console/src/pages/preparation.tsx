import { t, useI18n, systemText, number, countLabel } from "../i18n";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  CircleHelp,
  Copy,
  RefreshCw,
  ShieldCheck,
  Terminal,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { api, date } from "../api";
import { Chargement, Erreur, Titre, useToast } from "../ui";
export type Readiness = {
  schema_version: number;
  checked_at: string;
  duration_ms: number;
  scope: "local-private";
  ready: boolean;
  summary: Record<"pass" | "warn" | "fail" | "unknown", number>;
  checks: {
    id: string;
    group: string;
    status: "pass" | "warn" | "fail" | "unknown";
    required: boolean;
    label: string;
    message: string;
    evidence: Record<string, unknown>;
    action: { label: string; command: string } | null;
  }[];
  capabilities: Record<string, boolean>;
  limits: string[];
};
const groups: Record<string, string> = {
  runtime: "Runtime",
  get configuration() {
    return t("Private configuration");
  },
  get services() {
    return t("Connected services");
  },
  get routing() {
    return t("Model routing");
  },
  get knowledge() {
    return t("Knowledge");
  },
  get voice() {
    return t("Voice");
  },
  get mcp() {
    return t("MCP tools");
  },
};
const states = {
  pass: {
    icon: CheckCircle2,
    get label() {
      return t("Passed");
    },
  },
  warn: {
    icon: TriangleAlert,
    get label() {
      return t("Review");
    },
  },
  fail: {
    icon: XCircle,
    get label() {
      return t("Failed");
    },
  },
  unknown: {
    icon: CircleHelp,
    get label() {
      return t("Unknown");
    },
  },
};
export function Preparation() {
  useI18n();
  const [filter, setFilter] = useState("all");
  const notifier = useToast();
  const q = useQuery({
    queryKey: ["preparation"],
    queryFn: () => api<Readiness>("/preparation"),
    staleTime: 30000,
  });
  const copy = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      notifier(t("Command copied. Review it before running in your terminal."));
    } catch {
      notifier(
        t("Clipboard unavailable. Select and copy the command manually."),
        true,
      );
    }
  };
  return (
    <>
      <Titre
        surligne={t("WORKSPACE READINESS")}
        titre={t("Know what’s ready.")}
        texte={t(
          "A live operational check of your local environment, with a clear next step for each missing capability.",
        )}
      >
        <button
          className="btn"
          onClick={() => void q.refetch()}
          disabled={q.isFetching}
        >
          <RefreshCw size={16} className={q.isFetching ? "spin" : ""} />{" "}
          {t("Refresh checks")}
        </button>
      </Titre>
      {q.isPending ? (
        <Chargement />
      ) : q.error ? (
        <Erreur erreur={q.error} recommencer={() => q.refetch()} />
      ) : (
        q.data && (
          <>
            <section className="readiness-hero panel">
              <div
                className={`readiness-seal ${q.data.ready ? "check-pass" : "check-warn"}`}
              >
                <ShieldCheck size={40} />
              </div>
              <div>
                <span className="eyebrow">{t("LOCAL / PRIVATE")}</span>
                <h2>
                  {q.data.ready
                    ? t("Core operations are ready.")
                    : t("Your workspace needs attention.")}
                </h2>
                <p>
                  {t("Checked {date} · {seconds} s · cached for up to 30 s", {
                    date: date(q.data.checked_at),
                    seconds: number(q.data.duration_ms / 1000, {
                      minimumFractionDigits: 1,
                      maximumFractionDigits: 1,
                    }),
                  })}
                </p>
                <p>
                  {t(
                    "Operational checks do not replace security review or production qualification.",
                  )}
                </p>
              </div>
              <Link to="/missions" className="btn primary">
                {t("Open missions")} <ArrowRight size={16} />
              </Link>
            </section>
            <div className="readiness-summary">
              {(Object.keys(states) as (keyof typeof states)[]).map(
                (status) => {
                  const StateIcon = states[status].icon;
                  return (
                    <button
                      key={status}
                      className={`panel check-${status} ${filter === status ? "selected" : ""}`}
                      aria-pressed={filter === status}
                      onClick={() =>
                        setFilter(filter === status ? "all" : status)
                      }
                    >
                      <StateIcon size={20} />
                      <strong>{number(q.data!.summary[status])}</strong>
                      <span>{states[status].label}</span>
                    </button>
                  );
                },
              )}
            </div>
            <div className="section-heading">
              <h2>{t("Environment checks")}</h2>
              <button className="text-button" onClick={() => setFilter("all")}>
                {t("Show all checks")}
              </button>
            </div>
            <div className="readiness-groups">
              {Object.entries(groups).map(([group, label]) => {
                const checks = q.data!.checks.filter(
                  (check) =>
                    check.group === group &&
                    (filter === "all" || check.status === filter),
                );
                return (
                  checks.length > 0 && (
                    <section className="panel readiness-group" key={group}>
                      <h3>
                        {label}
                        <span>{countLabel(checks.length, "check")}</span>
                      </h3>
                      {checks.map((check) => {
                        const StateIcon = states[check.status].icon;
                        return (
                          <details
                            key={check.id}
                            className={`readiness-check check-${check.status}`}
                          >
                            <summary>
                              <StateIcon size={18} />
                              <div>
                                <strong>{systemText(check.label)}</strong>
                                <span>{systemText(check.message)}</span>
                              </div>
                              <small>{states[check.status].label}</small>
                            </summary>
                            <div className="check-detail">
                              <p>
                                {check.required
                                  ? t("Required for core operations")
                                  : t("Optional capability")}
                              </p>
                              {Object.keys(check.evidence).length > 0 && (
                                <pre>
                                  {JSON.stringify(check.evidence, null, 2)}
                                </pre>
                              )}
                              {check.action && (
                                <div className="copy-command">
                                  <div>
                                    <strong>
                                      {systemText(check.action.label)}
                                    </strong>
                                    <code>{check.action.command}</code>
                                  </div>
                                  <button
                                    className="icon-button"
                                    aria-label={t("Copy command for {name}", {
                                      name: systemText(check.label),
                                    })}
                                    onClick={() =>
                                      void copy(check.action!.command)
                                    }
                                  >
                                    <Copy size={16} />
                                  </button>
                                </div>
                              )}
                            </div>
                          </details>
                        );
                      })}
                    </section>
                  )
                );
              })}
            </div>
            <section className="panel readiness-limits">
              <h2>{t("Deployment boundaries")}</h2>
              <ul>
                {q.data.limits.map((limit) => (
                  <li key={limit}>{systemText(limit)}</li>
                ))}
              </ul>
            </section>
          </>
        )
      )}
      <section className="panel client-start">
        <div>
          <span className="eyebrow">{t("A REPEATABLE CLIENT WORKFLOW")}</span>
          <h2>{t("Set the boundaries. Then launch.")}</h2>
          <p>
            {t(
              "Use a dedicated VM per client. Keep client files outside this repository, configure their backup roots explicitly, and verify encrypted off-host recovery.",
            )}
          </p>
        </div>
        <ol className="numbered-steps">
          <li>
            <strong>{t("Qualify the environment")}</strong>
            <p>
              {t(
                "Run readiness, inspect service health, and review open security findings.",
              )}
            </p>
          </li>
          <li>
            <strong>{t("Curate the knowledge")}</strong>
            <p>
              {t(
                "Import reviewed runbooks into the isolated client installation, then reindex.",
              )}
            </p>
          </li>
          <li>
            <strong>{t("Run a synthetic mission")}</strong>
            <p>
              {t(
                "Check cited passages, approval, export and recovery before using client data.",
              )}
            </p>
          </li>
        </ol>
        <div className="client-start-footer">
          <Terminal size={17} />
          <code>./plateforme preparation</code>
          <span>
            <Check size={15} /> {t("Same checks from CLI")}
          </span>
        </div>
        <p className="hint">
          {t("Full operator guide in the repository:")}{" "}
          <code>docs/CLIENT-WORKFLOW.md</code>
        </p>
      </section>
    </>
  );
}
