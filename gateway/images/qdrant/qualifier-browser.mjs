// Invoked only while qualifier.py owns the disposable synthetic collection.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';

const input = JSON.parse(readFileSync(0, 'utf8'));
const require = createRequire(join(input.root, 'apps/console/package.json'));
const { chromium } = require('playwright');
const origin = new URL(input.base).origin;
const browser = await chromium.launch({ headless: true });
const errors = [];
const external = [];
const checks = [];
try {
  const context = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  await context.route('**/*', async route => {
    if (new URL(route.request().url()).origin !== origin) {
      external.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  for (const path of ['/dashboard/', '/dashboard#/collections', '/dashboard#/collections/synthetic']) {
    const response = await page.goto(origin + path, { waitUntil: 'networkidle' });
    // Hash-router navigation reuses the document and returns no HTTP response.
    assert(response === null || response.ok(), path);
    await page.getByText('synthetic', { exact: true }).first().waitFor({ state: 'visible', timeout: 30000 });
    if (path.endsWith('/synthetic')) {
      const loaded = page.waitForResponse(response => new URL(response.url()).pathname === '/collections/synthetic' && response.ok());
      await page.getByRole('tab', { name: 'Info', exact: true }).click();
      assert.equal((await (await loaded).json()).result.points_count, 3);
      await page.getByText('Collection Info', { exact: true }).waitFor({ state: 'visible' });
      await page.getByText('synthetic-current', { exact: true }).waitFor({ state: 'visible' });
    }
    await page.screenshot({ path: join(input.output, `dashboard-${checks.length}.png`), fullPage: true });
    checks.push({ path, syntheticCollectionVisible: true });
  }
  assert.equal(errors.length, 0, JSON.stringify(errors));
  assert.equal(external.length, 0, 'private dashboard attempted an external request');
  await context.close();
} catch (error) {
  writeFileSync(join(input.output, 'browser-failure.json'), JSON.stringify({ errors, external, checks, message: error.message }, null, 2));
  throw error;
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify({ engine: 'chromium', checks, externalRequests: external.length, pageErrors: errors.length }));
