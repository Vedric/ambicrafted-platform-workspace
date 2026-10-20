import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import redirects from 'follow-redirects';

// Exercise the real Node HTTP adapter in an offline network namespace. The
// browser runtime does not use it, but the complete build inventory retains it.
async function fixture(run) {
  const received = { origin: [], destination: [] };
  const destination = createServer((request, response) => {
    received.destination.push(request.headers);
    request.resume();
    response.end('synthetic');
  });
  let destinationPort;
  const origin = createServer((request, response) => {
    received.origin.push(request.headers);
    request.resume();
    if (request.url === '/same') {
      response.writeHead(302, { Location: '/final' });
    } else if (request.url !== '/final') {
      response.writeHead(302, { Location: `http://127.0.0.1:${destinationPort}/final` });
    }
    response.end('synthetic');
  });
  try {
    destination.listen(0, '127.0.0.1');
    await once(destination, 'listening');
    destinationPort = destination.address().port;
    origin.listen(0, '127.0.0.1');
    await once(origin, 'listening');
    await run(received, origin.address().port);
  } finally {
    await Promise.all([origin, destination].map(server => new Promise(resolve => {
      server.closeAllConnections();
      server.close(resolve);
    })));
  }
}

function request(port, headers, path = '/') {
  return new Promise((resolve, reject) => {
    const req = redirects.http.get({
      hostname: '127.0.0.1', port, path, headers,
      sensitiveHeaders: ['X-Api^Key', 'X-Token|Secret'],
    }, response => {
      response.resume();
      if (response.statusCode !== 200) {
        reject(new Error(`Synthetic redirect returned HTTP ${response.statusCode}`));
        return;
      }
      response.once('end', resolve);
      response.once('error', reject);
    });
    req.once('error', reject);
    req.setTimeout(2000, () => req.destroy(new Error('Synthetic redirect timed out')));
  });
}

const sensitive = {
  Authorization: 'synthetic', Cookie: 'synthetic',
  'Proxy-Authorization': 'synthetic', 'X-Api^Key': 'synthetic', 'X-Token|Secret': 'synthetic',
};

test('cross-origin redirects strip metacharacter-named sensitive headers', { timeout: 5000 }, async () => {
  await fixture(async (received, port) => {
    await request(port, { ...sensitive, 'X-Public': 'retained' });
    assert.equal(received.origin.length, 1);
    assert.equal(received.destination.length, 1);
    for (const name of Object.keys(sensitive)) {
      assert.equal(received.origin[0][name.toLowerCase()], 'synthetic');
      assert.equal(received.destination[0][name.toLowerCase()], undefined, `${name} crossed origin`);
    }
    assert.equal(received.destination[0]['x-public'], 'retained');
  });
});

test('array-form headers are normalized and stripped across origins', { timeout: 5000 }, async () => {
  await fixture(async (received, port) => {
    // Native Node HTTP does not add Host for the raw array form. Include it so
    // the vulnerable control reaches both servers rather than stopping at 400.
    await request(port, Object.entries({
      Host: `127.0.0.1:${port}`, ...sensitive, 'X-Public': 'retained',
    }).flat());
    assert.equal(received.origin.length, 1);
    assert.equal(received.destination.length, 1);
    for (const name of Object.keys(sensitive)) {
      assert.equal(received.origin[0][name.toLowerCase()], 'synthetic');
      assert.equal(received.destination[0][name.toLowerCase()], undefined, `${name} crossed origin`);
    }
    assert.equal(received.destination[0]['x-public'], 'retained');
  });
});

test('same-origin redirects preserve required credentials', { timeout: 5000 }, async () => {
  await fixture(async (received, port) => {
    await request(port, sensitive, '/same');
    assert.equal(received.origin.length, 2);
    assert.equal(received.destination.length, 0);
    for (const name of Object.keys(sensitive)) {
      assert.equal(received.origin[1][name.toLowerCase()], 'synthetic');
    }
  });
});
