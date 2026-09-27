import { useEffect, useSyncExternalStore } from "react";
import { frenchMessages } from "./messages.fr";
import { assistantFr } from "./messages.assistant";
import { insightsFr } from "./messages.insights";
import { architectureFr } from "./messages.architecture";

export type Language = "en" | "fr";
const messages = {
  ...frenchMessages,
  ...assistantFr,
  ...insightsFr,
  ...architectureFr,
} as const;
export type MessageKey = keyof typeof messages;
const sourceMessages = new Map<string, MessageKey>(
  Object.entries(messages).map(([key, translation]) => [
    translation,
    key as MessageKey,
  ]),
);
export const LANGUAGE_STORAGE_KEY = "ambicrafted-language";
const listeners = new Set<() => void>();
let preference: Language = "en";
let volatilePreference: Language | null = null;

export function getLanguage(): Language {
  if (volatilePreference) return volatilePreference;
  try {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (stored === "fr" || stored === "en") return stored;
    return "en";
  } catch {
    return preference;
  }
}

export function getLocale(): "en-US" | "fr-FR" {
  return getLanguage() === "fr" ? "fr-FR" : "en-US";
}

function notify() {
  document.documentElement.lang = getLanguage();
  listeners.forEach((listener) => listener());
}

export function setLanguage(language: Language) {
  if (language !== "en" && language !== "fr") return;
  preference = language;
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    volatilePreference = null;
  } catch {
    volatilePreference = language;
  }
  notify();
}

function storageChanged(event: StorageEvent) {
  if (!event.key || event.key === LANGUAGE_STORAGE_KEY) notify();
}

function subscribe(listener: () => void) {
  if (!listeners.size) window.addEventListener("storage", storageChanged);
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (!listeners.size) window.removeEventListener("storage", storageChanged);
  };
}

export function t(
  key: MessageKey,
  values: Record<string, string | number> = {},
): string {
  const text = getLanguage() === "fr" ? messages[key] : key;
  return text.replace(
    /\{([a-zA-Z][a-zA-Z0-9_]*)\}/g,
    (placeholder, name: string) =>
      Object.hasOwn(values, name) ? String(values[name]) : placeholder,
  );
}

/** Only for known system messages; never apply to runbooks, alerts or model output. */
export function systemText(value: string): string {
  if (Object.hasOwn(messages, value)) return t(value as MessageKey);
  const source = sourceMessages.get(value);
  return source ? t(source) : value;
}

export function number(
  value: number,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(getLocale(), options).format(value);
}

const countMessages = {
  result: ["{count} result", "{count} results"],
  analysis: ["{count} analysis", "{count} analyses"],
  check: ["{count} check", "{count} checks"],
  task: ["{count} task", "{count} tasks"],
  hour: ["{count} hour", "{count} hours"],
  day: ["{count} day", "{count} days"],
  document: ["{count} document", "{count} documents"],
  target: ["{count} target", "{count} targets"],
  source: ["{count} source runbook", "{count} source runbooks"],
  passage: ["{count} indexed passage", "{count} indexed passages"],
} as const satisfies Record<string, readonly [MessageKey, MessageKey]>;

export function countLabel(
  count: number,
  unit: keyof typeof countMessages,
): string {
  const singular = new Intl.PluralRules(getLocale()).select(count) === "one";
  return t(countMessages[unit][singular ? 0 : 1], { count: number(count) });
}

export function useI18n() {
  const language = useSyncExternalStore(
    subscribe,
    getLanguage,
    () => "en" as Language,
  );
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);
  return {
    language,
    locale: language === "fr" ? "fr-FR" : "en-US",
    setLanguage,
    t,
  } as const;
}

export function LanguageSelector() {
  const { t, language, setLanguage } = useI18n();
  return (
    <select
      className="language-selector"
      aria-label={t("Interface language")}
      value={language}
      onChange={(event) => setLanguage(event.target.value as Language)}
    >
      <option value="en">English (EN)</option>
      <option value="fr">Français (FR)</option>
    </select>
  );
}
