import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const erreursNavigateurs = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const erreurs: string[] = [];
  erreursNavigateurs.set(page, erreurs);
  page.on("pageerror", (erreur) => erreurs.push(erreur.message));
});
test.afterEach(async ({ page }) => {
  expect(
    erreursNavigateurs.get(page),
    "No uncaught browser exception is permitted",
  ).toEqual([]);
});

async function connexion(page: Page) {
  const reponse = await page.request.post("/api/auth/ticket", {
    headers: { Authorization: "Bearer " + process.env.PLATFORM_E2E_KEY },
    data: {},
  });
  expect(reponse.ok()).toBe(true);
  const { ticket } = await reponse.json();
  await page.goto("/#session=" + ticket);
  await expect(
    page.getByRole("heading", {
      name: "Your intelligence, in motion.",
      level: 1,
      exact: true,
    }),
  ).toBeVisible();
  await expect(page).toHaveURL("http://127.0.0.1:8789/");
  const cookie = (await page.context().cookies()).find(
    (c) => c.name === "ambicrafted_session",
  );
  expect(cookie).toMatchObject({
    httpOnly: true,
    sameSite: "Strict",
    path: "/",
  });
}

async function aller(page: Page, nom: string) {
  const menu = page.getByRole("button", { name: "Open navigation" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .filter({ visible: true })
    .getByRole("link", { name: nom, exact: true })
    .click();
}

async function creerAnalyse(
  page: Page,
  titre: string,
  alerte = "PostgreSQL connections exhausted. Synthetic exercise.",
) {
  await page.goto("/analyses/nouvelle");
  await page.getByLabel(/Analysis title/).fill(titre);
  await page.getByLabel(/Alert & context/).fill(alerte);
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(
    page.getByRole("heading", { name: titre, exact: true }),
  ).toBeVisible();
  return page.url().split("/").at(-1)!;
}

async function sansDefautsA11y(page: Page) {
  // Inspect the settled UI, not an intermediate opacity/color in its entrance transition.
  await page.evaluate(async () => {
    await document.fonts.ready;
    const finies = document
      .getAnimations()
      .filter((animation) =>
        Number.isFinite(animation.effect?.getComputedTiming().endTime),
      );
    await Promise.allSettled(finies.map((animation) => animation.finished));
  });
  const contenu = page.locator("#contenu > div");
  if (await contenu.count()) {
    await expect
      .poll(() =>
        contenu.evaluate((element) => getComputedStyle(element).opacity),
      )
      .toBe("1");
  }
  const resultats = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    resultats.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.map((n) => ({
        target: n.target,
        summary: n.failureSummary,
      })),
    })),
  ).toEqual([]);
}

test("private landing, refused login, keyboard entry and accessible layout", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Intelligence/ }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", /^en(?:-|$)/);
  await sansDefautsA11y(page);
  await testInfo.attach("landing", {
    body: await page.screenshot({ fullPage: true, animations: "disabled" }),
    contentType: "image/png",
  });
  const viewport = page.viewportSize()!;
  for (const width of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      `No landing overflow at ${width}px`,
    ).toBe(true);
  }
  await page.setViewportSize(viewport);
  const scene = page.locator(".neural-core").first();
  const runningOrbitAnimations = () => scene.evaluate((element) => element.getAnimations({ subtree: true }).filter((animation) => animation.playState === "running" && animation.effect?.getComputedTiming().endTime === Infinity).length);
  await scene.scrollIntoViewIfNeeded();
  await expect.poll(runningOrbitAnimations).toBeGreaterThan(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(scene).toHaveAttribute("data-resting", "true");
  await expect.poll(runningOrbitAnimations).toBe(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(scene).toHaveAttribute("data-resting", "false");
  await expect.poll(runningOrbitAnimations).toBeGreaterThan(0);
  await page.mouse.move(0, 0);
  await page.getByRole("button", { name: "Pause animations" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "paused");
  await expect(
    page.getByRole("button", { name: "Enable animations" }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "paused");
  await expect(
    page.getByRole("button", { name: "Enable animations" }),
  ).toBeVisible();
  await expect(scene).toBeVisible();
  await expect.poll(runningOrbitAnimations).toBe(0);
  await page.getByLabel("Welcome back").fill("Invalid synthetic password");
  await page
    .getByRole("button", { name: "Enter workspace", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Sign-in failed. Check your password and try again.",
  );
  await page
    .getByLabel("Welcome back")
    .fill(process.env.PLATFORM_E2E_PASSWORD!);
  await page.getByLabel("Welcome back").press("Enter");
  await expect(
    page.getByRole("heading", {
      name: "Your intelligence, in motion.",
      level: 1,
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Enable animations" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Enable animations" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "enabled");
  await expect(
    page.getByRole("button", { name: "Pause animations" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Your intelligence, in motion.",
      exact: true,
    }),
  ).toBeInViewport();
  await scene.scrollIntoViewIfNeeded();
  await expect.poll(runningOrbitAnimations).toBeGreaterThan(0);
  await sansDefautsA11y(page);
  await testInfo.attach("overview", {
    body: await page.screenshot({ fullPage: true, animations: "disabled" }),
    contentType: "image/png",
  });
  for (const largeur of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width: largeur, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      `No horizontal overflow at ${largeur}px`,
    ).toBe(true);
  }
});

test("navigation, command palette, focus confinement and theme", async ({
  page,
}) => {
  await connexion(page);
  await page.keyboard.press("Control+k");
  const dialogue = page.getByRole("dialog", { name: "Go anywhere" });
  await expect(dialogue).toBeVisible();
  await expect(page.getByLabel("Search pages")).toBeFocused();
  await page.getByLabel("Search pages").fill("Runbooks");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Runbooks", level: 1, exact: true }),
  ).toBeVisible();
  await expect(dialogue).not.toBeVisible();
  await aller(page, "System health");
  await expect(
    page.getByRole("heading", { name: "System health", level: 1, exact: true }),
  ).toBeVisible();
  await expect(page.getByText("AI gateway", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await sansDefautsA11y(page);
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await page.getByRole("button", { name: "Open command menu" }).click();
  for (let i = 0; i < 20; i++) await page.keyboard.press("Tab");
  expect(
    await dialogue.evaluate((d) => d.contains(document.activeElement)),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialogue).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Open command menu" }),
  ).toBeFocused();
  await aller(page, "Agents & tools");
  await expect(
    page.getByRole("heading", {
      name: "Specialists working toward one outcome.",
      level: 1,
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Approved tools & connectors" }),
  ).toBeVisible();
  await aller(page, "Approvals");
  await expect(
    page.getByRole("heading", { name: "Approvals", level: 1, exact: true }),
  ).toBeVisible();
  const menu = page.getByRole("button", { name: "Open navigation" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("link", { name: "Settings & help", exact: true })
    .filter({ visible: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Settings & help",
      level: 1,
      exact: true,
    }),
  ).toBeVisible();
  await sansDefautsA11y(page);
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("button", { name: "Sign out" })
    .filter({ visible: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Intelligence/ }),
  ).toBeVisible();
});

test("analysis lifecycle requires explicit checked human approval, then exports and deletes", async ({
  page,
}) => {
  await connexion(page);
  const id = await creerAnalyse(page, "Browser qualification: approval");
  await expect(page.getByText("Ready for your review")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Proposal for review" }),
  ).toBeVisible();
  await sansDefautsA11y(page);
  await page.getByRole("button", { name: "Approve proposal" }).click();
  const dialogue = page.getByRole("dialog", {
    name: "Approve proposal",
  });
  const confirmer = dialogue.getByRole("button", {
    name: "Approve proposal",
  });
  await expect(confirmer).toBeDisabled();
  await dialogue.getByRole("checkbox").check();
  await confirmer.click();
  await expect(
    page.getByRole("heading", { name: "Completed diagnosis" }),
  ).toBeVisible();
  const telechargement = page.waitForEvent("download");
  await page.getByRole("button", { name: "JSON", exact: true }).click();
  const fichier = await telechargement;
  expect(fichier.suggestedFilename()).toBe(`analyse-${id}.json`);
  const flux = await fichier.createReadStream();
  const morceaux: Buffer[] = [];
  for await (const morceau of flux!) morceaux.push(morceau);
  const rapport = JSON.parse(Buffer.concat(morceaux).toString());
  expect(rapport.statut).toBe("complet");
  expect(rapport.rapport.diagnostic.runbook_source).toBe("postgres.md");
  await page.getByRole("button", { name: "Delete analysis" }).click();
  await page
    .getByRole("dialog", { name: "Delete analysis" })
    .getByRole("button", { name: "Delete analysis", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Analyses", level: 1, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search analyses" })
    .fill("Browser qualification: approval");
  await expect(page.getByText("No analyses yet")).toBeVisible();
});

test("refusal withholds actions and cancellation ends a running job", async ({
  page,
}) => {
  await connexion(page);
  await creerAnalyse(page, "Browser qualification: rejection");
  await page
    .getByRole("button", { name: "Reject proposal", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Reject proposal" })
    .getByRole("button", { name: "Reject proposal" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Proposal rejected" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Completed diagnosis" }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Recommended actions" }),
  ).not.toBeVisible();
  await creerAnalyse(
    page,
    "Browser qualification: cancellation",
    "SLOW — cancellable synthetic exercise.",
  );
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve proposal" }),
  ).not.toBeVisible();
});

test("runbook creation, inert Markdown, optimistic conflict and search", async ({
  page,
}, testInfo) => {
  await connexion(page);
  await aller(page, "Runbooks");
  await page.getByRole("link", { name: "New runbook" }).click();
  const nom = `navigateur-${testInfo.project.name}.md`;
  await page.getByLabel("File name").fill(nom);
  await page
    .getByLabel("Markdown content")
    .fill(
      "# Browser procedure\n\nCheck the service.\n\n![Remote image blocked](https://outside.invalid/pixel.png)\n\n<script>window.testAttack=true</script>",
    );
  const reseau = [] as string[];
  page.on("request", (requete) => {
    if (requete.url().includes("outside.invalid")) reseau.push(requete.url());
  });
  await page.getByRole("button", { name: "Save runbook", exact: true }).click();
  await expect(
    page
      .getByRole("heading", { name: "Browser procedure", exact: true })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByText("Remote image blocked", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as unknown as { testAttack?: boolean }).testAttack,
    ),
  ).toBeUndefined();
  expect(reseau).toEqual([]);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page
    .getByLabel("Markdown content")
    .fill("# Draft to preserve\n\nCheck the service.");
  await page.evaluate(async (nom) => {
    const session = await (await fetch("/api/auth")).json();
    const actuel = await (await fetch("/api/runbooks/" + nom)).json();
    const reponse = await fetch("/api/runbooks/" + nom, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": session.csrf,
      },
      body: JSON.stringify({
        contenu: "# Concurrent edit\n\nAnother version.",
        empreinte: actuel.empreinte,
      }),
    });
    if (!reponse.ok) throw new Error("Failed to prepare the concurrent edit");
  }, nom);
  await page.getByRole("button", { name: "Save runbook", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "This runbook has changed. Reload the latest version before saving.",
  );
  await expect(page.getByLabel("Markdown content")).toHaveValue(
    "# Draft to preserve\n\nCheck the service.",
  );
  await aller(page, "Search");
  await page.getByLabel("Search query").fill("PostgreSQL");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(
    page.getByRole("link", { name: /PostgreSQL: connections/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Local semantic search" }).click();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("SIMILARITY 0.710")).toBeVisible();
});

test("operations require confirmation and follow the same execution view", async ({
  page,
}) => {
  await connexion(page);
  await aller(page, "Operations");
  await sansDefautsA11y(page);
  await page.getByRole("button", { name: "Run verification" }).click();
  await expect(
    page.getByRole("dialog", { name: "Verify platform" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirm operation" }).click();
  await expect(
    page.getByRole("heading", { name: "Operation completed" }),
  ).toBeVisible();
  await aller(page, "Observability");
  await expect(page.getByText("test-local", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Activity log" }),
  ).toBeVisible();
});

test("reduced motion, keyboard skip link and session expiration", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await connexion(page);
  await page.keyboard.press("Tab");
  // A reload resets focus so the skip link is the first keyboard destination.
  await page.reload();
  await expect(
    page.getByRole("heading", {
      name: "Your intelligence, in motion.",
      level: 1,
      exact: true,
    }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#contenu")).toBeFocused();
  const animees = await page
    .locator(".core-track")
    .evaluateAll((elements) =>
      elements.map((e) => parseFloat(getComputedStyle(e).animationDuration)),
    );
  expect(animees.length).toBeGreaterThan(0);
  expect(animees.every((duree) => duree <= 0.001)).toBe(true);
  await page.context().clearCookies();
  await aller(page, "Runbooks");
  await expect(
    page.getByRole("heading", { name: /Intelligence/ }),
  ).toBeVisible();
});

test("offline session discovery is recoverable without a blank screen", async ({
  page,
}) => {
  await page.route("**/api/auth", (route) => route.abort("failed"));
  await page.goto("/");
  await expect(page.getByRole("alert")).toBeVisible();
  await page.unroute("**/api/auth");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(
    page.getByRole("heading", { name: /Intelligence/ }),
  ).toBeVisible();
});

test("a failed analysis submission preserves input and can be retried", async ({
  page,
}) => {
  await connexion(page);
  await page.goto("/analyses/nouvelle");
  await page.getByLabel(/Analysis title/).fill("Retry after downtime");
  await page
    .getByLabel(/Alert & context/)
    .fill("Synthetic signal to preserve.");
  await page.route("**/api/analyses", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          detail:
            "This service is unavailable. Check system health and try again.",
        }),
      });
    } else await route.continue();
  });
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "This service is unavailable. Check system health and try again.",
  );
  await expect(page.getByLabel(/Analysis title/)).toHaveValue(
    "Retry after downtime",
  );
  await expect(page.getByLabel(/Alert & context/)).toHaveValue(
    "Synthetic signal to preserve.",
  );
  await page.unroute("**/api/analyses");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByText("Ready for your review")).toBeVisible();
});

test("assistant remains accessible in both themes when voice is unavailable", async ({
  page,
}) => {
  await connexion(page);
  await aller(page, "AURA · Voice assistant VOICE");
  await expect(
    page.getByRole("heading", {
      name: "Voice assistant",
      level: 1,
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Record" })).toBeDisabled();
  await expect(
    page.getByText("Unavailable", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByLabel("Your message")).toBeEditable();
  await sansDefautsA11y(page);
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await sansDefautsA11y(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const message = "How should I investigate this synthetic incident?";
  await page.getByLabel("Your message").fill(message);
  const requete = page.waitForRequest(
    (r) => /\/api\/conversations\/[^/]+\/messages$/.test(r.url()) && r.method() === "POST",
  );
  await page.getByLabel("Your message").press("Control+Enter");
  expect((await requete).postDataJSON()).toMatchObject({
    langue: "en",
    message,
    pieces: [],
  });
  await expect(
    page.getByText(
      "Synthetic reply: open Analyses to investigate an incident with its sources.",
    ),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Listen" })).toBeDisabled();
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(
    message,
  );
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(page.getByText(message, { exact: true })).not.toBeVisible();
});
