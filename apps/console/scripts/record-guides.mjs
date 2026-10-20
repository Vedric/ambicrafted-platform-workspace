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
const clips = JSON.parse(
  await readFile(new URL("./guide-script.json", import.meta.url), "utf8"),
);
const narration = JSON.parse(
  await readFile(join(evidence, "narration.json"), "utf8"),
);

const stamp = (seconds) =>
  new Date(Math.round(seconds * 1000)).toISOString().slice(11, 23);
try {
  for (const language of ["en", "fr"])
    for (const lesson of Object.keys(clips)) {
      if (only && only !== language && only !== `${lesson}-${language}`)
        continue;
      const context = await browser.newContext({
        viewport: { width: 1920, height: 1080 },
        recordVideo: { dir: temporary, size: { width: 1920, height: 1080 } },
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
      let posterCaptured = false;
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
      const captions = (text, start, end) => {
        // Short, optional WebVTT cues; narration is never burned into pixels.
        const words = text.split(/\s+/),
          parts = [];
        let lines = [""];
        for (const word of words) {
          const index = lines.length - 1;
          if ((lines[index] + " " + word).trim().length <= 44)
            lines[index] = (lines[index] + " " + word).trim();
          else if (lines.length === 1) lines.push(word);
          else {
            parts.push(lines.join("\n"));
            lines = [word];
          }
        }
        if (lines[0]) parts.push(lines.join("\n"));
        const length = parts.reduce((sum, part) => sum + part.length, 0);
        let position = start;
        return parts
          .map((part) => {
            const next = position + ((end - start) * part.length) / length;
            const result = `${stamp(position)} --> ${stamp(next)}\n${part}\n`;
            position = next;
            return result;
          })
          .join("\n");
      };
      const click = (en, fr) =>
        page
          .getByRole("button", {
            name: language === "fr" ? fr : en,
            exact: true,
          })
          .click();
      const draft = () =>
        page.getByLabel(language === "fr" ? "Votre message" : "Your message");
      const pause = () => {
        const index = cues.length - 1;
        const target = narration[`${lesson}-${language}`][index].duration + 0.8;
        const elapsed =
          (performance.now() - started) / 1000 - cues[index].start;
        return page.waitForTimeout(Math.max(1800, (target - elapsed) * 1000));
      };
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
        cue(3);
        await go("/runbooks");
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
        cue(0);
        await go("/assistant");
        await page
          .getByText(
            language === "fr"
              ? "Vérifier le microphone et le son"
              : "Check microphone & sound",
            { exact: true },
          )
          .click();
        await page.locator(".microphone-check").scrollIntoViewIfNeeded();
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
        cue(3);
        await click("Conversation history", "Historique des conversations");
        await pause();
      } else if (lesson === "documents") {
        cue(0);
        await go("/assistant");
        await draft().fill(
          language === "fr"
            ? "Crée un diagramme pour ce guide fictif : un navigateur envoie des requêtes HTTPS à une API, puis l’API interroge PostgreSQL avec SQL. Trois composants seulement."
            : "Create a diagram for this synthetic guide: a browser sends HTTPS requests to an API, then the API queries PostgreSQL using SQL. Three components only.",
        );
        await click("Send", "Envoyer");
        await page.locator(".artifact-card").waitFor();
        await pause();
        cue(1);
        await click("Open document", "Ouvrir le document");
        await page.locator(".artifact-expanded svg.document-diagram").waitFor();
        await page
          .getByRole("dialog")
          .getByRole("button", {
            name: language === "fr" ? "Afficher l’ensemble" : "Fit diagram",
            exact: true,
          })
          .click();
        await page.screenshot({
          path: join(output, `${lesson}-${language}.jpg`),
          type: "jpeg",
          quality: 86,
        });
        posterCaptured = true;
        await pause();
        await page.keyboard.press("Escape");
        cue(2);
        await draft().fill(
          language === "fr"
            ? "Rédige un rapport pour ce guide fictif : une API consulte PostgreSQL. La disponibilité cible et les tests de restauration ne sont pas renseignés. Sépare faits fournis, inconnues et vérifications proposées."
            : "Write a report for this synthetic guide: an API queries PostgreSQL. The availability target and restore tests are unknown. Separate supplied facts, unknowns and proposed checks.",
        );
        await click("Send", "Envoyer");
        await page.locator(".document-report").waitFor();
        await page.locator(".artifact-card").last().scrollIntoViewIfNeeded();
        await pause();
        cue(3);
        await page
          .locator(".artifact-card")
          .last()
          .getByRole("button", {
            name:
              language === "fr"
                ? "Préparer une note de mémoire"
                : "Prepare a memory note",
            exact: true,
          })
          .click();
        await page.getByRole("dialog").waitFor();
        await pause();
        await page.keyboard.press("Escape");
      } else if (lesson === "recovery") {
        cue(0);
        await go("/operations");
        await pause();
        cue(1);
        await click("Back up now", "Sauvegarder maintenant");
        await page.getByRole("dialog").waitFor();
        await pause();
        await page.keyboard.press("Escape");
        cue(2);
        await click("Test backup", "Tester la sauvegarde");
        await page.getByRole("dialog").waitFor();
        await pause();
        await page.keyboard.press("Escape");
        cue(3);
        await go("/preparation");
        await page
          .locator("main")
          .evaluate((element) =>
            element.scrollTo({ top: element.scrollHeight, behavior: "smooth" }),
          );
        await pause();
      } else if (lesson === "observability") {
        cue(0);
        await go("/observabilite");
        await pause();
        cue(1);
        await go("/sante");
        await pause();
        cue(2);
        await go("/observabilite");
        await page
          .locator("main")
          .evaluate((element) =>
            element.scrollTo({ top: element.scrollHeight, behavior: "smooth" }),
          );
        await pause();
        cue(3);
        await go("/architecture");
        await page.mouse.wheel(0, 500);
        await pause();
      } else if (lesson === "investigation") {
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
        cue(3);
        await go("/analyses");
        await pause();
      } else throw Error("Unknown guide lesson");
      if (cues.length !== 4)
        throw Error("Every guide needs four recorded chapters");
      if (!posterCaptured)
        await page.screenshot({
          path: join(output, `${lesson}-${language}.jpg`),
          type: "jpeg",
          quality: 86,
        });
      const duration = (performance.now() - started) / 1000;
      const video = page.video();
      await context.close();
      await video.saveAs(join(evidence, `${lesson}-${language}.webm`));
      await writeFile(
        join(output, `${lesson}-${language}.vtt`),
        "WEBVTT\n\n" +
          cues
            .map((cue, index) =>
              captions(
                cue.text,
                cue.start,
                cue.start + narration[`${lesson}-${language}`][index].duration,
              ),
            )
            .join("\n"),
      );
      if (errors.length)
        throw Error(
          "Browser exception during " + lesson + ": " + errors.join("; "),
        );
      const bytes = await readFile(
        join(evidence, `${lesson}-${language}.webm`),
      );
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
        viewport: { width: 1920, height: 1080 },
        captions_burned_in: false,
        cues,
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
