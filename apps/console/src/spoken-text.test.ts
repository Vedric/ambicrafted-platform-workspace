import { describe, expect, it } from "vitest";
import { texteOral } from "./spoken-text";

describe("spoken prose", () => {
  it("keeps paragraph boundaries and makes unpunctuated headings/list items speakable", () => {
    expect(
      texteOral(
        "# Next steps\n- Inspect the pool\n- Check latency.\n\nThen, compare the results.",
      ),
    ).toBe(
      "Next steps.\n\nInspect the pool.\n\nCheck latency.\n\nThen, compare the results.",
    );
  });
  it("does not corrupt decimals, French accents or punctuation", () => {
    expect(
      texteOral(
        "Védric, la latence est de 1.25 ms.\n\nQue souhaitez-vous vérifier ?",
        "fr",
      ),
    ).toBe(
      "Védric, la latence est de 1.25 ms.\n\nQue souhaitez-vous vérifier ?",
    );
  });
  it("announces a bounded continuation without slicing a word or a surrogate", () => {
    const result = texteOral("Voici les résultats. ".repeat(150) + "😀", "fr");
    expect(result.length).toBeLessThanOrEqual(2000);
    expect(result).toMatch(/résultats\. La suite est disponible à l’écran\.$/);
    expect(result).not.toContain("\uD83D");
  });
  it("does not fabricate speakable content from an empty markup-only response", () => {
    expect(texteOral("<span></span> ** **")).toBe("");
  });
});
