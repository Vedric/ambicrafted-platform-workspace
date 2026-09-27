import { t, useI18n } from "../i18n";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  Check,
  Compass,
  Search,
  ShieldCheck,
  SquareTerminal,
} from "lucide-react";
import { missions } from "../missions";
import { Titre } from "../ui";

export function Missions() {
  useI18n();
  const [query, setQuery] = useState("");
  const filtered = missions.filter((mission) =>
    `${mission.title} ${mission.category} ${mission.description}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <>
      <Titre
        surligne={t("MISSION LAUNCHPAD")}
        titre={t("Give your next move a direction.")}
        texte={t(
          "Choose a starting point. Add your evidence. Keep every decision in your hands.",
        )}
      />
      <section className="mission-intro panel">
        <div className="mission-intro-copy">
          <span className="tag">
            <Compass size={14} /> {t("SUPERVISED INVESTIGATION")}
          </span>
          <h2>
            {t("From a signal.")}
            <br />
            <span>{t("To a grounded decision.")}</span>
          </h2>
          <p>
            {t(
              "These templates prepare an editable analysis brief for the same local SRE workflow. Launch only after you have added the facts.",
            )}
          </p>
          <Link className="text-button" to="/preparation">
            {t("Check workspace readiness")} <ArrowRight size={16} />
          </Link>
        </div>
        <ol className="mission-sequence">
          <li>
            <span>01</span>
            <div>
              <strong>{t("Frame the question")}</strong>
              <small>{t("Symptoms, scope and constraints")}</small>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>{t("Gather the evidence")}</strong>
              <small>{t("Local runbooks and source passages")}</small>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>{t("Review the proposal")}</strong>
              <small>{t("Your approval; manual remediation")}</small>
            </div>
            <Check size={18} />
          </li>
        </ol>
      </section>
      <div className="section-heading">
        <h2>{t("Choose your mission")}</h2>
        <div className="search-input">
          <Search size={16} />
          <input
            aria-label={t("Find a mission")}
            placeholder={t("Find a starting point…")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>
      <div className="mission-grid">
        {filtered.map((mission) => (
          <Link
            key={mission.id}
            to={`/analyses/nouvelle?mission=${mission.id}`}
            className="mission-card panel"
          >
            <div className="mission-top">
              <span>{mission.category}</span>
              <b>{mission.code}</b>
            </div>
            <Compass size={26} className="mission-symbol" />
            <h3>{mission.title}</h3>
            <p>{mission.description}</p>
            <div className="mission-bottom">
              <span>{t("Prepare brief")}</span>
              <ArrowRight size={18} />
            </div>
          </Link>
        ))}
      </div>
      {!filtered.length && (
        <p role="status">
          {t("No matching mission. Try incident, capacity or performance.")}
        </p>
      )}
      <div className="mission-links">
        <Link to="/runbooks">
          <BookOpen size={20} />
          <div>
            <strong>{t("Build the knowledge")}</strong>
            <span>{t("Curate the procedures agents can cite.")}</span>
          </div>
          <ArrowRight size={17} />
        </Link>
        <Link to="/assistant">
          <AudioLines size={20} />
          <div>
            <strong>{t("Think it through with AURA")}</strong>
            <span>{t("A local conversation before you launch.")}</span>
          </div>
          <ArrowRight size={17} />
        </Link>
        <Link to="/parametres">
          <SquareTerminal size={20} />
          <div>
            <strong>{t("Work from your terminal")}</strong>
            <span>{t("The same platform, with CLI control.")}</span>
          </div>
          <ArrowRight size={17} />
        </Link>
      </div>
      <p className="hint">
        <ShieldCheck size={15} />{" "}
        {t(
          "Keep each client in a dedicated environment. Templates provide structure; they do not establish isolation or certify a proposed action.",
        )}
      </p>
    </>
  );
}
