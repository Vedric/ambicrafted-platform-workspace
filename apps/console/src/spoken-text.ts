/** Prepare displayed prose for speech without reading markup or cutting words. */
export function texteOral(texte: string, langue: "en" | "fr" = "en"): string {
  const code =
    langue === "fr"
      ? "Un exemple de code est disponible à l’écran."
      : "A code example is available on screen.";
  const continuation =
    langue === "fr"
      ? "La suite est disponible à l’écran."
      : "The rest is available on screen.";
  const cleaned = texte
    .replace(/```[\s\S]*?```/g, `\n${code}\n`)
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/<[^>]*>/g, " ")
    .replace(/^\s{0,3}(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+\.\s+)/gm, "")
    .replace(/[`*_~|]/g, "")
    .split(/\n+/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .map((line) => (/[.!?:;…][”’"')\]]*$/.test(line) ? line : line + "."))
    .join("\n\n");
  if (cleaned.length <= 2000) return cleaned;
  const limit = 2000 - continuation.length - 2;
  const prefix = cleaned.slice(0, limit);
  // Prefer a complete sentence. For an exceptionally long sentence, stop at a word.
  const sentence = [...prefix.matchAll(/[.!?…](?=\s)/g)].at(-1)?.index;
  const end =
    sentence !== undefined && sentence > limit / 2
      ? sentence + 1
      : prefix.lastIndexOf(" ");
  if (end < 1) return continuation;
  return (
    prefix
      .slice(0, end)
      .trimEnd()
      .replace(/[,:;]$/, "") +
    (sentence === end - 1 ? " " : "… ") +
    continuation
  );
}
