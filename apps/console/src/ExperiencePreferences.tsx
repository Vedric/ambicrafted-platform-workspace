import { AmbientAudioControl } from "./AmbientAudio";
import { createContext, useContext, useState } from "react";
import { Moon, Sun, Columns3, BookOpen } from "lucide-react";
import { Link } from "react-router-dom";
import { LanguageSelector, t, useI18n } from "./i18n";

export const ExperiencePreferences = createContext({
  theme: "dark",
  density: "comfortable",
  setTheme: (_value: string) => {},
  setDensity: (_value: string) => {},
});

export function WorkspacePreferences() {
  useI18n();
  const preferences = useContext(ExperiencePreferences);
  const [welcome, setWelcome] = useState(() => {
    try {
      return localStorage.getItem("ambicrafted-welcome-audio") !== "off";
    } catch {
      return true;
    }
  });
  return (
    <>
      <nav
        className="settings-navigation"
        aria-label={t("Workspace preferences")}
      >
        <a href="#appearance">{t("Appearance")}</a>
        <a href="#audio-settings">{t("Voice preferences")}</a>
        <a href="#access-settings">{t("Access & privacy")}</a>
        <a href="#cli-settings">{t("CLI reference")}</a>
        <Link to="/guide">
          <BookOpen size={16} />
          {t("User guide")}
        </Link>
      </nav>
      <div className="settings-experience-grid">
        <section className="panel settings-preferences" id="appearance">
          <span className="eyebrow">{t("YOUR WORKSPACE")}</span>
          <h2>{t("Make yourself at home.")}</h2>
          <p>
            {t(
              "Appearance and language follow you through this browser. Animations respect your device’s reduced-motion setting. Operational limits are managed separately.",
            )}
          </p>
          <fieldset className="preference-group">
            <legend>{t("Appearance")}</legend>
            <div className="theme-options">
              <button
                type="button"
                className={
                  "theme-option theme-option-day " +
                  (preferences.theme === "light" ? "selected" : "")
                }
                aria-pressed={preferences.theme === "light"}
                onClick={() => preferences.setTheme("light")}
              >
                <span className="theme-miniature" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span>
                  <Sun size={17} />
                  {t("Daylight")}
                </span>
              </button>
              <button
                type="button"
                className={
                  "theme-option theme-option-night " +
                  (preferences.theme === "dark" ? "selected" : "")
                }
                aria-pressed={preferences.theme === "dark"}
                onClick={() => preferences.setTheme("dark")}
              >
                <span className="theme-miniature" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span>
                  <Moon size={17} />
                  {t("Midnight")}
                </span>
              </button>
            </div>
          </fieldset>
          <div className="preference-row">
            <div>
              <strong>
                <Columns3 size={17} />
                {t("Layout density")}
              </strong>
              <p>{t("Keep readable text while adjusting card spacing.")}</p>
            </div>
            <select
              aria-label={t("Layout density")}
              value={preferences.density}
              onChange={(event) => preferences.setDensity(event.target.value)}
            >
              <option value="comfortable">{t("Comfortable")}</option>
              <option value="compact">{t("Compact")}</option>
            </select>
          </div>
          <div className="preference-row">
            <strong>{t("Interface language")}</strong>
            <LanguageSelector />
          </div>
        </section>
        <section className="panel settings-preferences" id="audio-settings">
          <span className="eyebrow">AURA · AUDIO</span>
          <h2>{t("Your voice, your space.")}</h2>
          <p>{t("AURA uses your system’s default microphone and speakers.")}</p>
          <div className="preference-row">
            <div>
              <strong>{t("Welcome me on arrival")}</strong>
              <p>
                {t(
                  "A personal welcome on the Welcome page, with a visible play button if the browser blocks autoplay.",
                )}
              </p>
            </div>
            <label className="preference-switch">
              <input
                type="checkbox"
                checked={welcome}
                aria-label={t("Welcome me on arrival")}
                onChange={(event) => {
                  setWelcome(event.target.checked);
                  try {
                    localStorage.setItem(
                      "ambicrafted-welcome-audio",
                      event.target.checked ? "on" : "off",
                    );
                  } catch {
                    /* Current control remains usable. */
                  }
                }}
              />
              <span aria-hidden="true" />
            </label>
          </div>
          <AmbientAudioControl expanded />
          <div className="settings-help-links">
            <Link className="btn" to="/assistant">
              {t("Talk with AURA")}
            </Link>
            <Link className="text-button" to="/guide">
              {t("Open the user guide")}
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}
