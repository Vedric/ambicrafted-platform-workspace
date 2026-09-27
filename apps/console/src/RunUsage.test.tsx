import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it } from "vitest";
import { setLanguage } from "./i18n";
import { RunUsage } from "./RunUsage";

beforeEach(() => setLanguage("en"));
afterEach(cleanup);
it("keeps unknown usage and absent costs distinct from a measured zero", () => {
  const view = render(<RunUsage budget={{ appels_llm: 2, cout_usd: null }} />);
  expect(screen.queryByRole("meter")).toBeNull();
  expect(screen.getAllByText("Not reported")).toHaveLength(3);
  expect(screen.getByText("2")).toBeVisible();
  view.rerender(
    <RunUsage
      budget={{
        tokens_total: 0,
        tokens_entree: 0,
        tokens_sortie: 0,
        cout_usd: 0,
        usage_complet: true,
        max_tokens_total: 60000,
      }}
    />,
  );
  expect(screen.getByRole("meter")).toHaveAttribute("value", "0");
  expect(screen.getByText("$0.0000")).toBeVisible();
  expect(screen.queryByText("Not reported")).toBeNull();
});
it("shows partial counts as a lower bound and preserves a last-response overshoot", () => {
  render(
    <RunUsage
      budget={{
        tokens_total: 60250,
        tokens_entree: 60000,
        tokens_sortie: 250,
        max_tokens_total: 60000,
        usage_complet: false,
        appels_llm_tentes: 3,
        appels_mesures_tokens: 2,
        usage_cout_complet: false,
      }}
    />,
  );
  expect(screen.getByText("Observed minimum")).toBeVisible();
  expect(screen.getByText("60,250 of 60,000 tokens observed")).toBeVisible();
  expect(screen.getByRole("meter")).toHaveAttribute("value", "60000");
  expect(screen.getByText("3")).toBeVisible();
  expect(
    screen.getByText("Some requests did not report an API cost."),
  ).toBeVisible();
});
it("does not render invalid legacy counters as legitimate measurements", () => {
  render(
    <RunUsage
      budget={{ tokens_total: -1, cout_usd: NaN, tokens_entree: Infinity }}
    />,
  );
  expect(screen.queryByRole("meter")).toBeNull();
  expect(screen.getAllByText("Not reported")).toHaveLength(3);
});
