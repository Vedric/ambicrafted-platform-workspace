import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, basename } from 'node:path';
import { test } from 'node:test';
import watcher from '@parcel/watcher';
import { expect } from 'expect';

test('native watcher keeps notifications and brace-glob exclusion', { timeout: 10000 }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'qdrant-watch-'));
  const events = [];
  let subscription;
  let resolveChange;
  let rejectChange;
  const changed = new Promise((resolve, reject) => {
    resolveChange = resolve;
    rejectChange = reject;
  });
  const deadline = setTimeout(() => rejectChange(new Error('watcher did not deliver a change')), 5000);
  try {
    await mkdir(join(root, 'nested'));
    subscription = await watcher.subscribe(root, (error, batch) => {
      if (error) return rejectChange(error);
      events.push(...batch);
      if (batch.some(event => basename(event.path) === 'visible.css')) resolveChange();
    }, { ignore: ['**/*.{tmp,log}'] });
    await writeFile(join(root, 'nested', 'hidden.tmp'), 'ignored');
    await writeFile(join(root, 'nested', 'hidden.log'), 'ignored');
    await writeFile(join(root, 'nested', 'visible.css'), '.fixture { color: red; }');
    await changed;
    assert(events.some(event => event.path.endsWith('/nested/visible.css') && event.type === 'create'));
    assert(!events.some(event => /\.(tmp|log)$/.test(event.path)), 'ignored glob emitted a file event');
  } finally {
    clearTimeout(deadline);
    if (subscription) await subscription.unsubscribe();
    await rm(root, { recursive: true, force: true });
  }
});

test('native snapshot detects additions while preserving glob ignores', async () => {
  const root = await mkdtemp(join(tmpdir(), 'qdrant-snapshot-'));
  const watched = join(root, 'watched');
  try {
    await mkdir(watched);
    const options = { ignore: ['**/*.{tmp,log}'] };
    const snapshot = join(root, 'snapshot');
    await watcher.writeSnapshot(watched, snapshot, options);
    await writeFile(join(watched, 'visible.css'), 'synthetic');
    await writeFile(join(watched, 'hidden.tmp'), 'synthetic');
    const events = await watcher.getEventsSince(watched, snapshot, options);
    assert.deepEqual(events.map(event => [basename(event.path), event.type]), [['visible.css', 'create']]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('upgraded Jest matcher support accepts matches and rejects mismatches with useful diffs', () => {
  expect({ collection: 'synthetic', points: [1, 2] }).toEqual({ collection: 'synthetic', points: [1, 2] });
  expect(() => { throw new Error('synthetic failure'); }).toThrow('synthetic failure');
  assert.throws(() => expect({ count: 1 }).toEqual({ count: 2 }), error => {
    assert.match(error.message, /Expected|expected/);
    assert.match(error.message, /Received|received/);
    assert.match(error.message, /count/);
    return true;
  });
});
