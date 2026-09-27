import { Link } from "react-router-dom";
import { ArrowRight, AudioLines, BookOpen, Gauge, Network } from "lucide-react";
import { t, useI18n } from "./i18n";
import { TechWatch } from "./TechWatch";

const updates = [
  {
    title: "Understand your activity",
    text: "Seven views connect retained runs, processing time, approvals, services and knowledge. Every chart explains its scope.",
    icon: Gauge,
    label: "INSIGHTS",
  },
  {
    title: "A voice that feels personal",
    text: "Speak with AURA in French or English using your system’s default microphone and speakers.",
    icon: AudioLines,
    label: "AURA",
  },
  {
    title: "One gateway for your tools",
    text: "Discover the local MCP gateway and follow the path from your request to sourced evidence and a human decision.",
    icon: Network,
    label: "NEXUS",
  },
] as const;

export function WelcomeUpdates() {
  useI18n();
  return (
    <>
      <TechWatch />
      <section
        className="landing-updates"
        aria-label={t("Latest workspace improvements")}
      >
        <div className="landing-updates-title">
          <span className="eyebrow">{t("Release notes")} · 0.4</span>
          <h2>{t("Latest workspace improvements")}</h2>
          <p>{t("Product updates, not live internet news.")}</p>
        </div>
        {updates.map((item) => (
          <article key={item.label}>
            <span className="landing-update-icon">
              <item.icon size={24} />
            </span>
            <span className="eyebrow">{item.label}</span>
            <h3>{t(item.title)}</h3>
            <p>{t(item.text)}</p>
          </article>
        ))}
      </section>
      <Link to="/guide" className="landing-guide-link">
        <BookOpen size={22} />
        <div>
          <strong>{t("Open the user guide")}</strong>
          <span>{t("Your first mission, step by step.")}</span>
        </div>
        <ArrowRight size={21} />
      </Link>
    </>
  );
}
