import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { date } from "./api";
import {
  getLanguage,
  getLocale,
  LANGUAGE_STORAGE_KEY,
  LanguageSelector,
  number,
  setLanguage,
  t,
  useI18n,
} from "./i18n";

function Sample() {
  const { t, locale } = useI18n();
  return (
    <>
      <LanguageSelector />
      <p data-testid="locale">{locale}</p>
      <p data-testid="label">{t("Overview")}</p>
      <label>
        Operator evidence
        <input defaultValue="Do not translate this customer title" />
      </label>
    </>
  );
}
beforeEach(() => {
  localStorage.clear();
  setLanguage("en");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  setLanguage("en");
});

describe("English and French interface preferences", () => {
  it("defaults to English and rejects corrupt persisted preferences", () => {
    for (const invalid of ["", "de", "null", '{"language":"fr"}', "FR"]) {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, invalid);
      expect(getLanguage()).toBe("en");
      expect(getLocale()).toBe("en-US");
    }
    render(<Sample />);
    expect(screen.getByLabelText("Interface language")).toHaveValue("en");
    expect(document.documentElement.lang).toBe("en");
  });
  it("updates labels, document language and storage without rewriting operator text", () => {
    render(<Sample />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "fr" } });
    expect(screen.getByTestId("locale")).toHaveTextContent("fr-FR");
    expect(screen.getByTestId("label")).not.toHaveTextContent(/^Overview$/);
    expect(screen.getByLabelText("Operator evidence")).toHaveValue(
      "Do not translate this customer title",
    );
    expect(document.documentElement.lang).toBe("fr");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("fr");
    cleanup();
    render(<Sample />);
    expect(screen.getByRole("combobox")).toHaveValue("fr");
  });
  it("updates an open view when another tab changes the saved language", () => {
    render(<Sample />);
    act(() => {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, "fr");
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: LANGUAGE_STORAGE_KEY,
          newValue: "fr",
        }),
      );
    });
    expect(screen.getByRole("combobox")).toHaveValue("fr");
    expect(document.documentElement.lang).toBe("fr");
  });
  it("keeps in-memory selection usable when both storage operations are blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError");
    });
    render(<Sample />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "fr" } });
    expect(screen.getByRole("combobox")).toHaveValue("fr");
    expect(document.documentElement.lang).toBe("fr");
  });
  it("keeps in-memory selection when storage is readable but writes exceed quota", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Full", "QuotaExceededError");
    });
    render(<Sample />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "fr" } });
    expect(screen.getByRole("combobox")).toHaveValue("fr");
    expect(document.documentElement.lang).toBe("fr");
  });
  it("formats dates and numbers using the selected locale", () => {
    const instant = "2026-09-27T10:15:00Z";
    setLanguage("en");
    const english = date(instant);
    setLanguage("fr");
    expect(date(instant)).toBe(
      new Intl.DateTimeFormat("fr-FR", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(instant)),
    );
    expect(date(instant)).not.toBe(english);
    expect(number(1234.5)).toBe(new Intl.NumberFormat("fr-FR").format(1234.5));
    expect(date("invalid")).toBe("—");
  });
  it("keeps singular and plural result labels distinct in French", () => {
    setLanguage("fr");
    expect(t("result")).toBe("résultat");
    expect(t("results")).toBe("résultats");
    expect(t("document")).toBe("document");
    expect(t("documents")).toBe("documents");
  });
});
