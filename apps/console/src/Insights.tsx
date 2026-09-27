import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowUpRight, Layers3, Radio } from "lucide-react";
import { type Vue, serviceName } from "./api";
import { t, useI18n, number, getLocale } from "./i18n";
import { activityWindow, serviceSnapshot, stateGroups } from "./insight-model";
import "./insights.css";

export function Insights({
  data,
  updatedAt,
}: {
  data: Vue;
  updatedAt: number;
}) {
  useI18n();
  const [window, setWindow] = useState<7 | 14>(14);
  const [cursor, setCursor] = useState<number | null>(null);
  const id = useId().replaceAll(":", "");
  const days = activityWindow(data.activite, window);
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
    <section className="insights" aria-labelledby={id + "-title"}>
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
                  aria-pressed={window === value}
                  onClick={() => {
                    setWindow(value);
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
