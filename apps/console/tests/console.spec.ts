import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const erreursNavigateurs = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const erreurs: string[] = [];
  erreursNavigateurs.set(page, erreurs);
  page.on('pageerror', erreur => erreurs.push(erreur.message));
});
test.afterEach(async ({ page }) => {
  expect(erreursNavigateurs.get(page), 'No uncaught browser exception is permitted').toEqual([]);
});

async function connexion(page: Page) {
  const reponse = await page.request.post('/api/auth/ticket', {
    headers: { Authorization: 'Bearer ' + process.env.PLATFORM_E2E_KEY }, data: {},
  });
  expect(reponse.ok()).toBe(true);
  const { ticket } = await reponse.json();
  await page.goto('/#session=' + ticket);
  await expect(page.getByRole('heading', { name: 'Une vision claire. Une action juste.' })).toBeVisible();
  await expect(page).toHaveURL('http://127.0.0.1:8789/');
  const cookie = (await page.context().cookies()).find(c => c.name === 'ambicrafted_session');
  expect(cookie).toMatchObject({ httpOnly: true, sameSite: 'Strict', path: '/' });
}

async function aller(page: Page, nom: string) {
  const menu = page.getByRole('button', { name: 'Ouvrir le menu' });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole('navigation', { name: 'Navigation principale' }).filter({ visible: true }).getByRole('link', { name: nom, exact: true }).click();
}

async function creerAnalyse(page: Page, titre: string, alerte = 'Connexions PostgreSQL saturées. Exercice synthétique.') {
  await page.goto('/analyses/nouvelle');
  await page.getByLabel(/Intitulé de l’analyse/).fill(titre);
  await page.getByLabel(/Alerte & contexte/).fill(alerte);
  await page.getByRole('button', { name: 'Lancer l’analyse' }).click();
  await expect(page.getByRole('heading', { name: titre, exact: true })).toBeVisible();
  return page.url().split('/').at(-1)!;
}

async function sansDefautsA11y(page: Page) {
  // Inspect the settled UI, not an intermediate opacity/color in its entrance transition.
  await page.evaluate(async () => {
    await document.fonts.ready;
    const finies = document.getAnimations().filter(animation =>
      Number.isFinite(animation.effect?.getComputedTiming().endTime),
    );
    await Promise.allSettled(finies.map(animation => animation.finished));
  });
  const contenu = page.locator('#contenu > div');
  if (await contenu.count()) {
    await expect.poll(() => contenu.evaluate(element => getComputedStyle(element).opacity)).toBe('1');
  }
  const resultats = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(resultats.violations.map(v => ({
    id: v.id, impact: v.impact,
    nodes: v.nodes.map(n => ({ target: n.target, summary: n.failureSummary })),
  }))).toEqual([]);
}

test('private landing, refused login, keyboard entry and accessible layout', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Votre astreinte/ })).toBeVisible();
  await sansDefautsA11y(page);
  await page.getByLabel('Retrouver votre espace').fill('Mot de passe synthétique invalide');
  await page.getByRole('button', { name: 'Entrer', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Connexion refusée.');
  await page.getByLabel('Retrouver votre espace').fill(process.env.PLATFORM_E2E_PASSWORD!);
  await page.getByLabel('Retrouver votre espace').press('Enter');
  await expect(page.getByRole('heading', { name: 'Une vision claire. Une action juste.' })).toBeVisible();
  await sansDefautsA11y(page);
  for (const largeur of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width: largeur, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `No horizontal overflow at ${largeur}px`).toBe(true);
  }
});

test('navigation, command palette, focus confinement and theme', async ({ page }) => {
  await connexion(page);
  await page.keyboard.press('Control+k');
  const dialogue = page.getByRole('dialog', { name: 'Aller à…' });
  await expect(dialogue).toBeVisible();
  await expect(page.getByLabel('Chercher une page')).toBeFocused();
  await page.getByLabel('Chercher une page').fill('Bibliothèque');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Le savoir qui guide vos agents.' })).toBeVisible();
  await expect(dialogue).not.toBeVisible();
  await aller(page, 'Santé & modèles');
  await expect(page.getByRole('heading', { name: 'Chaque composant, à sa place.' })).toBeVisible();
  await expect(page.getByText('Passerelle locale', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Activer le thème clair' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await sansDefautsA11y(page);
  await page.getByRole('button', { name: 'Activer le thème sombre' }).click();
  await page.keyboard.press('Control+k');
  for (let i = 0; i < 20; i++) await page.keyboard.press('Tab');
  expect(await dialogue.evaluate(d => d.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialogue).not.toBeVisible();
});

test('analysis lifecycle requires explicit checked human approval, then exports and deletes', async ({ page }) => {
  await connexion(page);
  const id = await creerAnalyse(page, 'Qualification navigateur : approbation');
  await expect(page.getByText('Cette proposition attend votre regard.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Proposition à examiner' })).toBeVisible();
  await sansDefautsA11y(page);
  await page.getByRole('button', { name: 'Examiner & approuver' }).click();
  const dialogue = page.getByRole('dialog', { name: 'Approuver la proposition' });
  const confirmer = dialogue.getByRole('button', { name: 'Confirmer l’approbation' });
  await expect(confirmer).toBeDisabled();
  await dialogue.getByRole('checkbox').check();
  await confirmer.click();
  await expect(page.getByRole('heading', { name: 'Diagnostic livré' })).toBeVisible();
  const telechargement = page.waitForEvent('download');
  await page.getByRole('button', { name: 'JSON', exact: true }).click();
  const fichier = await telechargement;
  expect(fichier.suggestedFilename()).toBe(`analyse-${id}.json`);
  const flux = await fichier.createReadStream();
  const morceaux: Buffer[] = [];
  for await (const morceau of flux!) morceaux.push(morceau);
  const rapport = JSON.parse(Buffer.concat(morceaux).toString());
  expect(rapport.statut).toBe('complet');
  expect(rapport.rapport.diagnostic.runbook_source).toBe('postgres.md');
  await page.getByRole('button', { name: 'Supprimer l’analyse' }).click();
  await page.getByRole('dialog', { name: 'Supprimer cette analyse' }).getByRole('button', { name: 'Supprimer', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Vos analyses, de bout en bout.' })).toBeVisible();
  await page.getByRole('textbox', { name: 'Rechercher une analyse' }).fill('Qualification navigateur : approbation');
  await expect(page.getByText('Aucune analyse ici pour le moment.')).toBeVisible();
});

test('refusal withholds actions and cancellation ends a running job', async ({ page }) => {
  await connexion(page);
  await creerAnalyse(page, 'Qualification navigateur : refus');
  await page.getByRole('button', { name: 'Refuser', exact: true }).click();
  await page.getByRole('dialog', { name: 'Refuser la proposition' }).getByRole('button', { name: 'Confirmer le refus' }).click();
  await expect(page.getByRole('heading', { name: 'Proposition refusée.' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Diagnostic livré' })).not.toBeVisible();
  await expect(page.getByRole('heading', { name: 'Actions proposées à l’opérateur' })).not.toBeVisible();
  await creerAnalyse(page, 'Qualification navigateur : annulation', 'LENT — exercice synthétique annulable.');
  await page.getByRole('button', { name: 'Annuler l’exécution' }).click();
  await expect(page.getByText('Annulé', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Examiner & approuver' })).not.toBeVisible();
});

test('runbook creation, inert Markdown, optimistic conflict and search', async ({ page }, testInfo) => {
  await connexion(page);
  await aller(page, 'Bibliothèque');
  await page.getByRole('link', { name: 'Nouveau runbook' }).click();
  const nom = `navigateur-${testInfo.project.name}.md`;
  await page.getByLabel('Nom du fichier').fill(nom);
  await page.getByLabel('Contenu Markdown').fill('# Procédure navigateur\n\nVérifier le service.\n\n![Image distante bloquée](https://outside.invalid/pixel.png)\n\n<script>window.testAttack=true</script>');
  const reseau = [] as string[];
  page.on('request', requete => { if (requete.url().includes('outside.invalid')) reseau.push(requete.url()); });
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Procédure navigateur', exact: true }).first()).toBeVisible();
  await expect(page.getByText('Image distante bloquée', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { testAttack?: boolean }).testAttack)).toBeUndefined();
  expect(reseau).toEqual([]);
  await page.getByRole('button', { name: 'Modifier', exact: true }).click();
  await page.getByLabel('Contenu Markdown').fill('# Brouillon à conserver\n\nVérifier le service.');
  await page.evaluate(async nom => {
    const session = await (await fetch('/api/auth')).json();
    const actuel = await (await fetch('/api/runbooks/' + nom)).json();
    const reponse = await fetch('/api/runbooks/' + nom, {
      method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf },
      body: JSON.stringify({ contenu: '# Modification concurrente\n\nAutre version.', empreinte: actuel.empreinte }),
    });
    if (!reponse.ok) throw new Error('Failed to prepare the concurrent edit');
  }, nom);
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Ce runbook a changé.');
  await expect(page.getByLabel('Contenu Markdown')).toHaveValue('# Brouillon à conserver\n\nVérifier le service.');
  await aller(page, 'Recherche');
  await page.getByLabel('Votre recherche').fill('PostgreSQL');
  await page.getByRole('button', { name: 'Rechercher', exact: true }).click();
  await expect(page.getByRole('link', { name: /PostgreSQL : connexions/ })).toBeVisible();
  await page.getByRole('button', { name: 'Sémantique locale' }).click();
  await page.getByRole('button', { name: 'Rechercher', exact: true }).click();
  await expect(page.getByText('SIMILARITÉ 0.710')).toBeVisible();
});

test('operations require confirmation and follow the same execution view', async ({ page }) => {
  await connexion(page);
  await aller(page, 'Opérations');
  await sansDefautsA11y(page);
  await page.getByRole('button', { name: 'Lancer la vérification' }).click();
  await expect(page.getByRole('dialog', { name: 'Vérifier la plateforme' })).toBeVisible();
  await page.getByRole('button', { name: 'Confirmer le lancement' }).click();
  await expect(page.getByRole('heading', { name: 'Opération terminée.' })).toBeVisible();
  await aller(page, 'Observabilité');
  await expect(page.getByText('test-local', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Journal d’activité' })).toBeVisible();
});

test('reduced motion, keyboard skip link and session expiration', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await connexion(page);
  await page.keyboard.press('Tab');
  // A reload resets focus so the skip link is the first keyboard destination.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Une vision claire. Une action juste.' })).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Aller au contenu' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#contenu')).toBeFocused();
  const animees = await page.locator('.orbit-ring').evaluateAll(elements => elements.map(e => parseFloat(getComputedStyle(e).animationDuration)));
  expect(animees.every(duree => duree <= 0.001)).toBe(true);
  await page.context().clearCookies();
  await aller(page, 'Bibliothèque');
  await expect(page.getByRole('heading', { name: /Votre astreinte/ })).toBeVisible();
});

test('offline session discovery is recoverable without a blank screen', async ({ page }) => {
  await page.route('**/api/auth', route => route.abort('failed'));
  await page.goto('/');
  await expect(page.getByRole('alert')).toBeVisible();
  await page.unroute('**/api/auth');
  await page.getByRole('button', { name: 'Réessayer' }).click();
  await expect(page.getByRole('heading', { name: /Votre astreinte/ })).toBeVisible();
});

test('a failed analysis submission preserves input and can be retried', async ({ page }) => {
  await connexion(page);
  await page.goto('/analyses/nouvelle');
  await page.getByLabel(/Intitulé de l’analyse/).fill('Reprise après indisponibilité');
  await page.getByLabel(/Alerte & contexte/).fill('Signal synthétique à conserver.');
  await page.route('**/api/analyses', async route => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Moteur temporairement indisponible.' }) });
    } else await route.continue();
  });
  await page.getByRole('button', { name: 'Lancer l’analyse' }).click();
  await expect(page.getByRole('alert')).toContainText('Moteur temporairement indisponible.');
  await expect(page.getByLabel(/Intitulé de l’analyse/)).toHaveValue('Reprise après indisponibilité');
  await expect(page.getByLabel(/Alerte & contexte/)).toHaveValue('Signal synthétique à conserver.');
  await page.unroute('**/api/analyses');
  await page.getByRole('button', { name: 'Lancer l’analyse' }).click();
  await expect(page.getByText('Cette proposition attend votre regard.')).toBeVisible();
});

test('assistant remains accessible in both themes when voice is unavailable', async ({ page }) => {
  await connexion(page);
  await aller(page, 'Assistant vocal VOIX');
  await expect(page.getByRole('heading', { name: 'Une voix à vos côtés.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Dicter un message' })).toBeDisabled();
  await expect(page.getByText('Indisponible', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Votre message')).toBeEditable();
  await sansDefautsA11y(page);
  await page.getByRole('button', { name: 'Activer le thème clair' }).click();
  await sansDefautsA11y(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const message = 'Comment analyser cet incident synthétique ?';
  await page.getByLabel('Votre message').fill(message);
  const requete = page.waitForRequest(r => r.url().endsWith('/api/assistant/dialogue') && r.method() === 'POST');
  await page.getByLabel('Votre message').press('Control+Enter');
  expect((await requete).postDataJSON()).toEqual({ messages: [{ role: 'user', content: message }] });
  await expect(page.getByText('Réponse synthétique : ouvrez Analyses pour examiner un incident avec ses sources.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Écouter la réponse' })).toBeDisabled();
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(message);
  await page.getByRole('button', { name: 'Effacer le dialogue' }).click();
  await expect(page.getByText(message, { exact: true })).not.toBeVisible();
});
