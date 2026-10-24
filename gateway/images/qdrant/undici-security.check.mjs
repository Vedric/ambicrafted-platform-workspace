import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer } from 'node:http';
import { setTimeout } from 'node:timers/promises';
import { gzipSync } from 'node:zlib';
import { test } from 'node:test';
import { fetch } from 'undici';

// GHSA-xjj6-f33q-929c: catching fetch's rejection must also prevent a later,
// unhandled error from an orphan response stream from killing the process.
test('excessive encodings and a truncated body do not crash the client', { timeout: 5000 }, async () => {
  const server = createServer((request, response) => {
    if (request.url === '/truncated') {
      response.writeHead(200, {
        'content-encoding': 'gzip, gzip, gzip, gzip, gzip, gzip',
        'content-length': '100',
        connection: 'close',
      });
      response.end();
    } else {
      response.writeHead(200, { 'content-encoding': 'gzip' });
      response.end(gzipSync('synthetic response'));
    }
  });
  try {
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const base = `http://127.0.0.1:${server.address().port}`;
    await assert.rejects(fetch(`${base}/truncated`), TypeError);
    await setTimeout(100);
    const response = await fetch(`${base}/valid`);
    assert.equal(await response.text(), 'synthetic response');
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
