/** Real browser recordings of the deterministic, disposable E2E application.
 * Run with the test server on 8789; the session file is private and never copied.
 * Voice readiness/STT below are explicitly synthetic; no model quality claim.
 */
import { chromium } from "playwright";
import { readFile, writeFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { createHash } from "node:crypto";

const sessionFile = process.argv[2];
const evidence = process.argv[3];
if (!sessionFile || !evidence)
  throw Error(
    "Usage: node scripts/record-guides.mjs PRIVATE_SESSION_JSON PRIVATE_EVIDENCE_DIR",
  );
const { key } = JSON.parse(await readFile(sessionFile, "utf8"));
if (typeof key !== "string" || key.length < 32)
  throw Error("Missing disposable credentials");
const base = "http://127.0.0.1:8789";
const output = resolve("public/guides");
await mkdir(output, { recursive: true });
await mkdir(evidence, { recursive: true, mode: 0o700 });
const temporary = await mkdtemp(join(tmpdir(), "ambicrafted-guide-"));
const browser = await chromium.launch({
  args: [
    "--use-fake-device-for-media-stream",
    "--use-fake-ui-for-media-stream",
  ],
});
const bootstrap = await browser.newContext();
const auth = await bootstrap.request.post(base + "/api/auth/ticket", {
  headers: { Authorization: "Bearer " + key },
  data: {},
});
if (!auth.ok()) throw Error("Disposable authentication failed");
const login = await bootstrap.newPage();
await login.addInitScript(() =>
  localStorage.setItem("ambicrafted-welcome-audio", "off"),
);
await login.goto(base + "/#session=" + (await auth.json()).ticket);
await login.locator(".insights").waitFor();
const cookies = await bootstrap.cookies();
await bootstrap.close();
const only = process.argv[4];
const results = only
  ? JSON.parse(await readFile(join(evidence, "recordings.json"), "utf8"))
  : [];
const clips = {
  "first-steps": {
    en: [
      "Welcome to your private workspace. Choose your language and theme.",
      "Check Readiness before starting a mission.",
      "Choose a mission and describe observed facts.",
    ],
    fr: [
      "Bienvenue dans votre espace privé. Choisissez la langue et le thème.",
      "Vérifiez la préparation avant une mission.",
      "Choisissez une mission et décrivez les faits observés.",
    ],
  },
  voice: {
    en: [
      "AURA follows your system’s default microphone and speakers.",
      "Record a draft, then review its transcription. This transcript is synthetic.",
      "Send reviewed text to AURA. Conversation cannot approve an operation.",
    ],
    fr: [
      "AURA utilise le microphone et la sortie audio par défaut du système.",
      "Enregistrez puis relisez la transcription. Ici, elle est simulée.",
      "Envoyez le texte relu à AURA. La conversation ne valide aucune opération.",
    ],
  },
  investigation: {
    en: [
      "Describe a synthetic incident and submit a supervised analysis.",
      "Read the proposal and inspect its sources before deciding.",
      "Your decision is recorded. Approval does not execute remediation.",
    ],
    fr: [
      "Décrivez un incident fictif et lancez une analyse supervisée.",
      "Lisez la proposition et ses sources avant de décider.",
      "Votre décision est enregistrée. Elle ne lance aucune remédiation.",
    ],
  },
};
const stamp = (seconds) =>
  new Date(Math.round(seconds * 1000)).toISOString().slice(11, 23);
try {
  for (const language of ["en", "fr"])
    for (const lesson of Object.keys(clips)) {
      if (only && only !== language && only !== `${lesson}-${language}`)
        continue;
      const context = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        recordVideo: { dir: temporary, size: { width: 1280, height: 800 } },
        reducedMotion: "no-preference",
        locale: language === "fr" ? "fr-FR" : "en-US",
        permissions: ["microphone"],
        storageState: { cookies, origins: [] },
      });
      await context.addInitScript((language) => {
        localStorage.setItem("ambicrafted-language", language);
        localStorage.setItem(
          "ambicrafted-theme",
          language === "fr" ? "light" : "dark",
        );
        localStorage.setItem("ambicrafted-welcome-audio", "off");
      }, language);
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const started = performance.now();
      const cues = [];
      const cue = (index) =>
        cues.push({
          start: (performance.now() - started) / 1000,
          text: clips[lesson][language][index],
        });
      const go = async (route) => {
        await page.goto(base + route);
        await page.locator("h1").waitFor();
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(1100);
      };
      const pause = () => page.waitForTimeout(2400); // Reading time in an exported tutorial, not a test retry.
      if (lesson === "first-steps") {
        cue(0);
        await go("/welcome");
        await pause();
        cue(1);
        await go("/preparation");
        await pause();
        cue(2);
        await go("/missions");
        await pause();
      } else if (lesson === "voice") {
        // Deterministic guide fixture; native browser capture still uses Chromium's fake microphone.
        await page.route("**/api/voix/statut?*", (route) =>
          route.fulfill({
            json: {
              pret: true,
              local: true,
              voix: "voix-feminine-" + language,
              langue: language === "fr" ? "fr-FR" : "en-US",
            },
          }),
        );
        const question =
          language === "fr"
            ? "Comment lancer une analyse supervisée ?"
            : "How do I start a supervised analysis?";
        await page.route("**/api/voix/transcrire", (route) =>
          route.fulfill({ json: { texte: question, local: true } }),
        );
        if (language === "fr")
          await page.route("**/api/conversations/*/messages", (route) =>
            route.fulfill({
              contentType: "application/x-ndjson",
              body:
                JSON.stringify({
                  type: "done",
                  texte:
                    "Réponse simulée : ouvrez Analyses pour examiner un incident avec ses sources.",
                  local: true,
                  actions_executees: false,
                }) + "\n",
            }),
          );
        cue(0);
        await go("/assistant");
        await pause();
        cue(1);
        await page
          .getByRole("button", {
            name: language === "fr" ? "Enregistrer" : "Record",
            exact: true,
          })
          .click();
        await page.waitForTimeout(1800);
        await page
          .getByRole("button", {
            name:
              language === "fr"
                ? "Terminer l’enregistrement"
                : "Finish recording",
            exact: true,
          })
          .click();
        await page
          .getByLabel(language === "fr" ? "Votre message" : "Your message")
          .waitFor();
        await pause();
        cue(2);
        await page
          .getByRole("button", {
            name: language === "fr" ? "Envoyer" : "Send",
            exact: true,
          })
          .click();
        await pause();
      } else {
        cue(0);
        await go("/analyses/nouvelle");
        await page
          .getByLabel(
            language === "fr" ? /Titre de l’analyse/ : /Analysis title/,
          )
          .fill(
            language === "fr"
              ? "Exercice · connexions PostgreSQL"
              : "Training · PostgreSQL connections",
          );
        await page
          .getByLabel(
            language === "fr" ? /Alerte et contexte/ : /Alert & context/,
          )
          .fill(
            language === "fr"
              ? "Exercice fictif : connexions PostgreSQL saturées. Vérifiez les sources ; aucune modification autorisée."
              : "Synthetic exercise: PostgreSQL connections exhausted. Inspect the sources; no changes authorised.",
          );
        await pause();
        await page
          .getByRole("button", {
            name: language === "fr" ? "Lancer l’analyse" : "Run analysis",
            exact: true,
          })
          .click();
        cue(1);
        await page
          .getByRole("button", {
            name:
              language === "fr"
                ? "Approuver la proposition"
                : "Approve proposal",
            exact: true,
          })
          .waitFor();
        await pause();
        cue(2);
        const reject =
          language === "fr" ? "Rejeter la proposition" : "Reject proposal";
        await page.getByRole("button", { name: reject, exact: true }).click();
        await pause();
        await page
          .getByRole("dialog", { name: reject })
          .getByRole("button", { name: reject, exact: true })
          .click();
        await pause();
      }
      await page.screenshot({
        path: join(output, `${lesson}-${language}.jpg`),
        type: "jpeg",
        quality: 86,
      });
      const duration = (performance.now() - started) / 1000;
      const video = page.video();
      await context.close();
      await video.saveAs(join(output, `${lesson}-${language}.webm`));
      await writeFile(
        join(output, `${lesson}-${language}.vtt`),
        "WEBVTT\n\n" +
          cues
            .map(
              (cue, index) =>
                `${index + 1}\n${stamp(cue.start)} --> ${stamp(cues[index + 1]?.start ?? duration)}\n${cue.text}\n`,
            )
            .join("\n"),
      );
      if (errors.length)
        throw Error(
          "Browser exception during " + lesson + ": " + errors.join("; "),
        );
      const bytes = await readFile(join(output, `${lesson}-${language}.webm`));
      const previous = results.findIndex(
        (item) => item.lesson === lesson && item.language === language,
      );
      if (previous >= 0) results.splice(previous, 1);
      results.push({
        lesson,
        language,
        duration_seconds: Number(duration.toFixed(2)),
        bytes: bytes.length,
        sha256: createHash("sha256").update(bytes).digest("hex"),
        page_errors: errors,
      });
      await writeFile(
        join(evidence, "recordings.json"),
        JSON.stringify(results, null, 2),
      );
      console.log(`${lesson}-${language}: recorded`);
    }
} finally {
  await browser.close();
  await rm(temporary, { recursive: true, force: true });
}
await writeFile(
  join(output, "provenance.json"),
  JSON.stringify(
    {
      source:
        "Playwright capture of the local application served by tests/server.py",
      data: "Synthetic disposable data; model inference and voice recognition are deterministic fixtures. No customer data.",
      browser: "Chromium",
      clips: results,
    },
    null,
    2,
  ),
);
