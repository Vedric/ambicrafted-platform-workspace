import {
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  Layers3,
  Radio,
  Timer,
  Hourglass,
  BookOpen,
  ChartColumn,
} from "lucide-react";
import { type Vue, type Liste, type Runbook, serviceName } from "./api";
import { t, useI18n, number, getLocale } from "./i18n";
import {
  activityWindow,
  serviceSnapshot,
  stateGroups,
  processingSummary,
  workloadGroups,
  pendingReviewAge,
  corpusVolume,
  INSIGHT_RUN_LIMIT,
} from "./insight-model";
import {
  MotionPreference,
  useReducedMotionPreference,
} from "./motion-preferences";
import "./insights.css";

type DetailSource<T> = {
  data?: T;
  loading: boolean;
  failed: boolean;
  retry: () => void;
  updatedAt: number;
};

function useChartMotion() {
  const ref = useRef<HTMLElement>(null);
  const preference = useContext(MotionPreference);
  const reduced = useReducedMotionPreference();
  const [visible, setVisible] = useState(false);
  const [foreground, setForeground] = useState(
    () => typeof document !== "undefined" && !document.hidden,
  );
  useEffect(() => {
    const change = () => setForeground(!document.hidden);
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);
  useEffect(() => {
    if (!ref.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry?.isIntersecting ?? false),
      { threshold: 0.05 },
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return { ref, enabled: preference && !reduced && foreground && visible };
}

function InsightCard({
  title,
  subtitle,
  icon,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  icon: ReactNode;
  children: ReactNode;
  footer: ReactNode;
}) {
  const id = useId();
  const motion = useChartMotion();
  return (
    <section
      ref={motion.ref}
      className="panel insight-metric-panel"
      aria-labelledby={id}
      data-chart-motion={motion.enabled ? "on" : "off"}
    >
      <div className="insight-card-heading">
        <div>
          {icon}
          <h3 id={id}>{title}</h3>
        </div>
      </div>
      <p className="insight-subtitle">{subtitle}</p>
      <div className="insight-metric-body">{children}</div>
      <div className="insight-metric-footer">{footer}</div>
    </section>
  );
}

type MetricRow = {
  id: string;
  label: string;
  value: number;
  formatted: string;
  color: string;
  href?: string;
  detail?: string;
};
function MetricBars({
  rows,
  maximum,
  caption,
  valueLabel,
}: {
  rows: MetricRow[];
  maximum: number;
  caption: string;
  valueLabel: string;
}) {
  return (
    <>
      <ul className="metric-bars" aria-label={caption}>
        {rows.map((row) => (
          <li key={row.id} className={"color-" + row.color}>
            <div className="metric-row-label">
              <span className="legend-dot" aria-hidden="true" />
              {row.href ? (
                <Link to={row.href}>{row.label}</Link>
              ) : (
                <span>{row.label}</span>
              )}
              <strong>{row.formatted}</strong>
            </div>
            <svg
              viewBox="0 0 320 12"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <rect className="metric-track" width="320" height="12" rx="4" />
              <rect
                className="metric-fill"
                width={
                  maximum > 0
                    ? Math.min(320, Math.max(0, (row.value / maximum) * 320))
                    : 0
                }
                height="12"
                rx="4"
              />
            </svg>
            {row.detail && <small>{row.detail}</small>}
          </li>
        ))}
      </ul>
      <details className="chart-data">
        <summary>{t("Inspect numeric values")}</summary>
        <table>
          <caption>{caption}</caption>
          <thead>
            <tr>
              <th scope="col">{t("Record name")}</th>
              <th scope="col">{valueLabel}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <th scope="row">{row.label}</th>
                <td>{row.formatted}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </>
  );
}

function DetailUnavailable({
  loading,
  reload,
}: {
  loading?: boolean;
  reload?: () => void;
}) {
  return (
    <div className="metric-unavailable">
      <p>
        {loading
          ? t("Loading chart details…")
          : t("Chart details are unavailable. No values are inferred.")}
      </p>
      {!loading && reload && (
        <button className="btn small" onClick={reload}>
          {t("Reload chart details")}
        </button>
      )}
    </div>
  );
}

const seconds = (value: number) =>
  number(value, { maximumFractionDigits: 1 }) + " s";
const bytes = (value: number) =>
  number(value / 1000, {
    style: "unit",
    unit: "kilobyte",
    maximumFractionDigits: 1,
  });

function RunInsights({
  source,
  runbooks,
  now,
}: {
  source?: DetailSource<Liste>;
  runbooks?: DetailSource<Runbook[]>;
  now: number;
}) {
  const available = !!source?.data && !source.failed;
  const runs = available
    ? source.data!.elements.slice(0, INSIGHT_RUN_LIMIT)
    : [];
  const processing = processingSummary(runs);
  const groups = workloadGroups(runs);
  const review = pendingReviewAge(runs, now);
  const mixRows = groups.map((group) => ({
    ...group,
    value: group.count,
    formatted: number(group.count),
    label: t(group.label),
  }));
  const reviewRows = review.groups.map((group) => ({
    ...group,
    value: group.count,
    formatted: number(group.count),
    label: t(group.label),
  }));
  const unavailable = (
    <DetailUnavailable loading={source?.loading} reload={source?.retry} />
  );
  const visibleDurations = processing.eligible.slice(0, 6);
  const durationRows = visibleDurations.map((run) => ({
    id: run.id,
    label:
      run.mode === "operation"
        ? t(
            groups.find((group) => group.id === run.options.operation)?.label ??
              "Other run types",
          )
        : run.titre,
    value: run.duree_s,
    formatted: seconds(run.duree_s),
    color: run.mode === "operation" ? "violet" : "cyan",
    href: "/analyses/" + encodeURIComponent(run.id),
  }));
  return (
    <>
      <div className="insight-sample-note">
        <span className="eyebrow">{t("Run intelligence")}</span>
        <h3>{t("Patterns that help you decide.")}</h3>
        <p>
          {available
            ? t(
                "Latest {shown} of {total} saved runs, ordered by creation. Limited to {limit}; these charts do not describe the entire history when more records exist.",
                {
                  shown: number(runs.length),
                  total: number(source.data!.total),
                  limit: number(INSIGHT_RUN_LIMIT),
                },
              )
            : t(
                "Detailed charts use a separate, bounded snapshot of saved runs.",
              )}
        </p>
      </div>
      <div className="insight-detail-grid">
        <InsightCard
          title={t("Recorded processing time")}
          subtitle={t("Completed and rejected runs with saved timings")}
          icon={<Timer size={18} />}
          footer={
            <p className="chart-note">
              {t(
                "Worker process time, including resumed passes. Queue and human waiting time are excluded. Failed, stopped, pending and missing timings are omitted.",
              )}
            </p>
          }
        >
          {!available ? (
            unavailable
          ) : !processing.eligible.length ? (
            <p className="chart-empty">
              {t(
                "No completed or rejected runs with a recorded duration in this sample.",
              )}
            </p>
          ) : (
            <>
              <div className="metric-summary">
                <div>
                  <strong>{seconds(processing.median!)}</strong>
                  <span>{t("Median recorded time")}</span>
                </div>
                <div>
                  <strong>{number(processing.eligible.length)}</strong>
                  <span>{t("timed runs in the sample")}</span>
                </div>
              </div>
              <MetricBars
                rows={durationRows}
                maximum={Math.max(
                  ...visibleDurations.map((run) => run.duree_s),
                )}
                caption={t("Recorded processing time")}
                valueLabel={t("Process time")}
              />
              <p className="chart-note">
                {t(
                  "Bars show the latest {count} eligible creations. The median uses every eligible run in this sample.",
                  { count: number(durationRows.length) },
                )}
              </p>
            </>
          )}
        </InsightCard>
        <InsightCard
          title={t("Recent workload mix")}
          subtitle={t("Actual run types, not inferred mission topics")}
          icon={<ChartColumn size={18} />}
          footer={
            <p className="chart-note">
              {t(
                "Analyses and maintenance operations share the same queue. Topic labels are not stored, so no incident categories are inferred from titles.",
              )}
            </p>
          }
        >
          {!available ? (
            unavailable
          ) : !runs.length ? (
            <p className="chart-empty">{t("No saved runs to compare yet.")}</p>
          ) : (
            <>
              <div className="metric-summary">
                <div>
                  <strong>{number(runs.length)}</strong>
                  <span>{t("runs in the sample")}</span>
                </div>
                <div>
                  <strong>
                    {number(groups.filter((group) => group.count > 0).length)}
                  </strong>
                  <span>{t("observed run types")}</span>
                </div>
              </div>
              <MetricBars
                rows={mixRows}
                maximum={Math.max(...groups.map((group) => group.count))}
                caption={t("Recent workload mix")}
                valueLabel={t("Count")}
              />
            </>
          )}
        </InsightCard>
        <InsightCard
          title={t("Pending review age")}
          subtitle={t("Time since the latest saved update")}
          icon={<Hourglass size={18} />}
          footer={
            <>
              <p className="chart-note">
                {t(
                  "Only runs currently awaiting human review in this sample. Age is measured at refresh, not an approval deadline or a recorded queue duration.",
                )}
              </p>
              <Link className="text-button" to="/approbations">
                {t("Open approvals")} <ArrowUpRight size={15} />
              </Link>
            </>
          }
        >
          {!available ? (
            unavailable
          ) : !review.total ? (
            <p className="chart-empty">
              {t("No human review is pending in this sample.")}
            </p>
          ) : (
            <>
              <div className="metric-summary">
                <div>
                  <strong>{number(review.total)}</strong>
                  <span>{t("awaiting human review")}</span>
                </div>
                <div>
                  <strong>
                    {review.oldest === null
                      ? "—"
                      : number(review.oldest / 3600, {
                          maximumFractionDigits: 1,
                        }) + " h"}
                  </strong>
                  <span>{t("oldest known update")}</span>
                </div>
              </div>
              <MetricBars
                rows={reviewRows}
                maximum={Math.max(...review.groups.map((group) => group.count))}
                caption={t("Pending review age")}
                valueLabel={t("Count")}
              />
              {review.unavailable > 0 && (
                <p className="chart-note">
                  {t(
                    "{count} records have unavailable or future timestamps and are excluded from the age bars.",
                    { count: number(review.unavailable) },
                  )}
                </p>
              )}
            </>
          )}
        </InsightCard>
        <CorpusInsight source={runbooks} />
      </div>
    </>
  );
}

function CorpusInsight({ source }: { source?: DetailSource<Runbook[]> }) {
  const available = !!source?.data && !source.failed;
  const corpus = corpusVolume(available ? source.data! : []);
  const rows: MetricRow[] = corpus.largest.map((runbook) => ({
    id: runbook.nom,
    label: runbook.titre || runbook.nom,
    value: runbook.octets,
    formatted: bytes(runbook.octets),
    color: "green",
    href: "/runbooks/" + encodeURIComponent(runbook.nom),
    detail: runbook.nom,
  }));
  if (corpus.remainingCount)
    rows.push({
      id: "__other",
      label: t("Other runbooks ({count})", {
        count: number(corpus.remainingCount),
      }),
      value: corpus.remainingBytes,
      formatted: bytes(corpus.remainingBytes),
      color: "slate",
    });
  return (
    <InsightCard
      title={t("Knowledge footprint")}
      subtitle={t("Source document sizes · decimal kilobytes")}
      icon={<BookOpen size={18} />}
      footer={
        <p className="chart-note">
          {t(
            "Source files only. Size does not measure quality, freshness, index coverage or model knowledge. No document dates are supplied by the API.",
          )}
        </p>
      }
    >
      {!available ? (
        <DetailUnavailable loading={source?.loading} reload={source?.retry} />
      ) : !corpus.count ? (
        <p className="chart-empty">{t("No runbook sources available yet.")}</p>
      ) : (
        <>
          <div className="metric-summary">
            <div>
              <strong>{bytes(corpus.total)}</strong>
              <span>{t("total source size")}</span>
            </div>
            <div>
              <strong>{number(corpus.count)}</strong>
              <span>{t("source documents")}</span>
            </div>
          </div>
          <MetricBars
            rows={rows}
            maximum={Math.max(0, ...rows.map((row) => row.value))}
            caption={t("Knowledge footprint")}
            valueLabel={t("Source size")}
          />
          {corpus.unavailable > 0 && (
            <p className="chart-note">
              {t(
                "{count} document sizes are unavailable and excluded from totals.",
                { count: number(corpus.unavailable) },
              )}
            </p>
          )}
        </>
      )}
    </InsightCard>
  );
}

export function Insights({
  data,
  updatedAt,
  runs,
  runbooks,
}: {
  data: Vue;
  updatedAt: number;
  runs?: DetailSource<Liste>;
  runbooks?: DetailSource<Runbook[]>;
}) {
  useI18n();
  const [activityDays, setActivityDays] = useState<7 | 14>(14);
  const [cursor, setCursor] = useState<number | null>(null);
  const id = useId().replaceAll(":", "");
  const motion = useChartMotion();
  const days = activityWindow(data.activite, activityDays);
  const max = Math.max(
    2,
    Math.ceil(Math.max(0, ...days.map((day) => day.total)) / 2) * 2,
  );
  const total = days.reduce((sum, day) => sum + day.total, 0);
  const selected = Math.max(
    0,
    Math.min(cursor ?? days.length - 1, days.length - 1),
  );
  const selectedDay = days[selected];
  const dateLabel = (value: string) =>
    new Intl.DateTimeFormat(getLocale(), {
      dateStyle: "medium",
      timeZone: "UTC",
    }).format(new Date(value + "T00:00:00Z"));
  const point = (index: number, value: number) => ({
    x: 36 + (index / Math.max(1, days.length - 1)) * 562,
    y: 180 - (value / max) * 142,
  });
  const points = days.map((day, index) => point(index, day.total));
  const line = points
    .map((p, index) => (index ? "L" : "M") + p.x + "," + p.y)
    .join(" ");
  const area = points.length
    ? line + " L" + points.at(-1)!.x + ",180 L36,180 Z"
    : "";
  const groups = stateGroups(data.statuts);
  const stateTotal = groups.reduce((sum, group) => sum + group.count, 0);
  const snapshot = serviceSnapshot(data.sante.services);
  let offset = 0;
  const arcs = groups
    .filter((group) => group.count > 0)
    .map((group) => {
      const length = (group.count / stateTotal) * 100;
      const arc = { ...group, offset, length };
      offset += length;
      return arc;
    });
  return (
    <section
      ref={motion.ref}
      className="insights"
      aria-labelledby={id + "-title"}
      data-chart-motion={motion.enabled ? "on" : "off"}
    >
      <div className="insight-heading">
        <div>
          <span className="eyebrow">{t("Operational pulse")}</span>
          <h2 id={id + "-title"}>
            {t("See the work. Understand the system.")}
          </h2>
          <p>
            {t("Charts use saved runs and the latest local service probes.")}
          </p>
        </div>
        <Link className="btn small" to="/architecture">
          {t("Explore the architecture")} <ArrowUpRight size={16} />
        </Link>
      </div>
      <div className="insight-grid">
        <section
          className="panel insight-activity"
          aria-labelledby={id + "-activity"}
        >
          <div className="insight-card-heading">
            <div>
              <Activity size={18} />
              <h3 id={id + "-activity"}>{t("Created runs")}</h3>
            </div>
            <div
              className="chart-period"
              role="group"
              aria-label={t("Activity window")}
            >
              {([7, 14] as const).map((value) => (
                <button
                  key={value}
                  aria-pressed={activityDays === value}
                  onClick={() => {
                    setActivityDays(value);
                    setCursor(null);
                  }}
                >
                  {value === 7 ? t("7 days") : t("14 days")}
                </button>
              ))}
            </div>
          </div>
          <div className="chart-summary">
            <strong>{number(total)}</strong>
            <span>{t("runs in this window")}</span>
            <small>{t("Recorded activity · UTC")}</small>
          </div>
          <div className="chart-canvas">
            <svg
              viewBox="0 0 640 220"
              role="img"
              aria-label={
                days
                  .map((day) => dateLabel(day.date) + ": " + number(day.total))
                  .join("; ") || t("No activity recorded yet.")
              }
              onPointerMove={(event) => {
                if (!days.length || event.pointerType === "touch") return;
                const rect = event.currentTarget.getBoundingClientRect();
                setCursor(
                  Math.round(
                    ((((event.clientX - rect.left) / rect.width) * 640 - 36) /
                      562) *
                      (days.length - 1),
                  ),
                );
              }}
            >
              <defs>
                <linearGradient id={id + "-area"} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--mint)" stopOpacity=".24" />
                  <stop
                    offset="100%"
                    stopColor="var(--mint)"
                    stopOpacity=".01"
                  />
                </linearGradient>
              </defs>
              {[0, 0.5, 1].map((part) => (
                <g key={part} className="chart-gridline">
                  <line
                    x1="36"
                    x2="606"
                    y1={180 - part * 142}
                    y2={180 - part * 142}
                  />
                  <text x="24" y={184 - part * 142} textAnchor="end">
                    {number(max * part, { maximumFractionDigits: 1 })}
                  </text>
                </g>
              ))}
              {area && <path d={area} fill={"url(#" + id + "-area)"} />}
              {line && <path className="chart-line" d={line} pathLength="1" />}
              {points.map((p, index) => (
                <circle
                  key={days[index].date}
                  className="chart-dot"
                  cx={p.x}
                  cy={p.y}
                  r={selected === index ? 5 : 3}
                />
              ))}
              {points[selected] && (
                <line
                  className="chart-cursor"
                  x1={points[selected].x}
                  x2={points[selected].x}
                  y1="26"
                  y2="184"
                />
              )}
              {days.length > 0 &&
                [0, Math.floor((days.length - 1) / 2), days.length - 1]
                  .filter((value, index, all) => all.indexOf(value) === index)
                  .map((index) => (
                    <text
                      className="chart-axis-label"
                      key={index}
                      x={points[index].x}
                      y="210"
                      textAnchor={
                        index === 0
                          ? "start"
                          : index === days.length - 1
                            ? "end"
                            : "middle"
                      }
                    >
                      {new Intl.DateTimeFormat(getLocale(), {
                        month: "short",
                        day: "numeric",
                        timeZone: "UTC",
                      }).format(new Date(days[index].date + "T00:00:00Z"))}
                    </text>
                  ))}
            </svg>
          </div>
          {selectedDay ? (
            <div className="chart-inspector">
              <label htmlFor={id + "-day"}>{t("Inspect a day")}</label>
              <input
                id={id + "-day"}
                type="range"
                min={0}
                max={Math.max(0, days.length - 1)}
                value={selected}
                onChange={(event) => setCursor(Number(event.target.value))}
                aria-valuetext={
                  dateLabel(selectedDay.date) + ": " + number(selectedDay.total)
                }
              />
              <output htmlFor={id + "-day"}>
                <span>{dateLabel(selectedDay.date)}</span>
                <strong>{number(selectedDay.total)}</strong>
              </output>
            </div>
          ) : (
            <p className="chart-empty">{t("No activity recorded yet.")}</p>
          )}
          <details className="chart-data">
            <summary>{t("View chart data")}</summary>
            <table>
              <caption>{t("Created runs")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("Day")}</th>
                  <th scope="col">{t("Count")}</th>
                </tr>
              </thead>
              <tbody>
                {days.map((day) => (
                  <tr key={day.date}>
                    <th scope="row">{dateLabel(day.date)}</th>
                    <td>{number(day.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>
        <section
          className="panel insight-states"
          aria-labelledby={id + "-states"}
        >
          <div className="insight-card-heading">
            <div>
              <Layers3 size={18} />
              <h3 id={id + "-states"}>{t("Run states")}</h3>
            </div>
          </div>
          <p className="insight-subtitle">{t("Current saved records")}</p>
          <div className="state-ring">
            <svg viewBox="0 0 200 200" aria-hidden="true">
              <circle className="ring-track" cx="100" cy="100" r="77" />
              {arcs.map((arc) => (
                <circle
                  key={arc.id}
                  className={"ring-arc color-" + arc.color}
                  cx="100"
                  cy="100"
                  r="77"
                  pathLength="100"
                  strokeDasharray={arc.length + " " + (100 - arc.length)}
                  strokeDashoffset={-arc.offset}
                  transform="rotate(-90 100 100)"
                />
              ))}
            </svg>
            <div>
              <strong>{number(stateTotal)}</strong>
              <span>
                {stateTotal ? t("Saved runs") : t("No saved states yet")}
              </span>
            </div>
          </div>
          <ul className="state-legend">
            {groups.map((group) => (
              <li key={group.id}>
                <span className={"legend-dot color-" + group.color} />
                <span>{t(group.label)}</span>
                <strong>{number(group.count)}</strong>
              </li>
            ))}
          </ul>
        </section>
        <section
          className="panel insight-services"
          aria-labelledby={id + "-services"}
        >
          <div className="insight-card-heading">
            <div>
              <Radio size={18} />
              <h3 id={id + "-services"}>{t("Service response")}</h3>
            </div>
            <span className="probe-summary">
              {t("{ready} of {total} service checks passed", {
                ready: number(snapshot.responding),
                total: number(snapshot.total),
              })}
            </span>
          </div>
          <p className="insight-subtitle">
            {t("Latest health checks · milliseconds")}
          </p>
          {data.sante.services.length ? (
            <ul className="probe-chart">
              {data.sante.services.map((service) => (
                <li key={service.id}>
                  <span className="probe-name">
                    <i
                      className={
                        "health-dot " + (service.ok ? "healthy" : "unhealthy")
                      }
                    />
                    {serviceName(service.id)}
                  </span>
                  <span className="probe-track" aria-hidden="true">
                    <i
                      style={{
                        width:
                          service.ok && Number.isFinite(service.latence_ms)
                            ? Math.max(
                                0,
                                Math.min(
                                  100,
                                  (service.latence_ms / snapshot.maxLatency) *
                                    100,
                                ),
                              ) + "%"
                            : "0%",
                      }}
                    />
                  </span>
                  <strong>
                    {service.ok && Number.isFinite(service.latence_ms)
                      ? number(service.latence_ms) + " ms"
                      : t("Probe failed")}
                  </strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="chart-empty">{t("No service probes available.")}</p>
          )}
          <p className="chart-note">
            {t(
              "Snapshot, refreshed every 15 seconds. Probe time is not inference latency or an availability SLO.",
            )}
          </p>
        </section>
      </div>
      <RunInsights
        source={runs}
        runbooks={runbooks}
        now={runs?.updatedAt || updatedAt}
      />
      <div className="insight-foot">
        <span>
          {t(
            "Saved runs include analyses and maintenance operations. Deleting a run removes it from these charts.",
          )}
        </span>
        <span>
          {updatedAt
            ? t("Latest refresh: {time}", {
                time: new Intl.DateTimeFormat(getLocale(), {
                  timeStyle: "short",
                }).format(updatedAt),
              })
            : t("No current data")}
        </span>
      </div>
    </section>
  );
}
