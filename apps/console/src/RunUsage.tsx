import { Gauge } from "lucide-react";
import { number, t, useI18n } from "./i18n";
import type { RunBudget } from "./api";

function measured(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

export function RunUsage({ budget }: { budget?: RunBudget }) {
  useI18n();
  const attempted = budget?.appels_llm_tentes ?? budget?.appels_llm;
  const tokens = budget?.tokens_total;
  const limit = budget?.max_tokens_total;
  const full = budget?.usage_complet === true;
  return (
    <section className="panel run-usage">
      <h2>
        <Gauge size={18} />
        {t("Token usage & limits")}
      </h2>
      <div className="run-usage-total">
        <strong>{measured(tokens) ? number(tokens) : "—"}</strong>
        <span>{full ? t("Reported tokens") : t("Observed minimum")}</span>
      </div>
      {measured(tokens) && measured(limit) && limit > 0 && (
        <>
          <meter
            min={0}
            max={limit}
            value={Math.min(tokens, limit)}
            aria-label={t("Observed token usage against the run limit")}
          />
          <p>
            {t("{used} of {limit} tokens observed", {
              used: number(tokens),
              limit: number(limit),
            })}
          </p>
        </>
      )}
      <dl>
        <dt>{t("Input tokens")}</dt>
        <dd>
          {measured(budget?.tokens_entree)
            ? number(budget.tokens_entree)
            : t("Not reported")}
        </dd>
        <dt>{t("Output tokens")}</dt>
        <dd>
          {measured(budget?.tokens_sortie)
            ? number(budget.tokens_sortie)
            : t("Not reported")}
        </dd>
        <dt>{t("Model requests attempted")}</dt>
        <dd>{measured(attempted) ? number(attempted) : "—"}</dd>
        <dt>{t("Requests with both token counts")}</dt>
        <dd>
          {measured(budget?.appels_mesures_tokens)
            ? number(budget.appels_mesures_tokens)
            : "—"}
        </dd>
        <dt>{t("Reported API cost")}</dt>
        <dd>
          {measured(budget?.cout_usd)
            ? number(budget.cout_usd, {
                style: "currency",
                currency: "USD",
                minimumFractionDigits: 4,
              })
            : t("Not reported")}
        </dd>
      </dl>
      <p className="hint">
        {t(
          "Missing usage is unknown, not zero. Partial counts are lower bounds; local compute costs are not included.",
        )}
      </p>
      <p className="hint">
        {t(
          "The observed budget stops subsequent model calls. The last response can exceed it; input tokens are not predicted.",
        )}
      </p>
      {budget?.usage_cout_complet === false && (
        <p className="hint">{t("Some requests did not report an API cost.")}</p>
      )}
    </section>
  );
}
