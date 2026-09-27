import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Radio } from "lucide-react";
import { api, date } from "./api";
import { t, useI18n } from "./i18n";

export type TechDigest = {
  enabled: boolean;
  refreshing: boolean;
  stale: boolean;
  generated_at?: number;
  next_refresh_at?: number;
  interval_hours: number;
  articles?: {
    title: string;
    source: string;
    published: string;
    url: string;
  }[];
  unavailable_sources?: string[];
  briefings?: Partial<
    Record<"en" | "fr", { text: string; duration_s: number }>
  >;
};
export function useTechWatch() {
  return useQuery({
    queryKey: ["public-tech-watch"],
    queryFn: ({ signal }) =>
      api<TechDigest>("/veille", "GET", undefined, signal),
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: false,
  });
}
export function TechWatch() {
  useI18n();
  const watch = useTechWatch();
  const data = watch.data;
  return (
    <section className="tech-watch panel" aria-label={t("Technology watch")}>
      <div className="section-heading">
        <div>
          <span className="eyebrow">
            <Radio size={15} /> {t("TECHNOLOGY WATCH")}
          </span>
          <h2>{t("Signals for your next mission.")}</h2>
        </div>
        <span className="tag">{t("Every 3 days")}</span>
      </div>
      <p>
        {t(
          "Official announcements for DevOps, SRE, DevSecOps and platform engineering. AURA prepares a local AI summary; verify the linked sources before acting.",
        )}
      </p>
      {watch.error || !data?.articles?.length ? (
        <p role="status">
          {t(
            "The technology briefing is not ready yet. Your workspace remains available.",
          )}
        </p>
      ) : (
        <>
          <p className="hint">
            {t("Updated {date}", {
              date: date(new Date(data.generated_at! * 1000).toISOString()),
            })}
            {data.stale && (
              <> · {t("Refresh pending — this digest may be outdated.")}</>
            )}
          </p>
          {!!data.unavailable_sources?.length && (
            <p role="status">
              {t("Some sources were unavailable: {sources}", {
                sources: data.unavailable_sources.join(", "),
              })}
            </p>
          )}
          <div className="tech-watch-grid">
            {data.articles.map((item) => (
              <article key={item.url}>
                <span className="eyebrow">{item.source}</span>
                <h3>
                  <a href={item.url} target="_blank" rel="noopener noreferrer">
                    {item.title}
                    <ExternalLink size={14} />
                  </a>
                </h3>
                <time dateTime={item.published}>{date(item.published)}</time>
              </article>
            ))}
          </div>
        </>
      )}
      <p className="hint">
        {t(
          "Original article titles are preserved. Only public feeds are fetched; your conversations and attachments are never sent to news sources.",
        )}
      </p>
    </section>
  );
}
