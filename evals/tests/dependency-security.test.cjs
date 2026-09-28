const test = require('node:test');
const assert = require('node:assert/strict');
const uri = require('fast-uri');
const { Address6 } = require('ip-address');

test('La sérialisation refuse une injection d’autorité dans le port', () => {
  const base = { scheme: 'https', host: 'example.test', path: '/app' };
  for (const port of ['@127.0.0.1:8124', '80/path', '443?other']) {
    assert.throws(() => uri.serialize({ ...base, port }), TypeError);
  }
  assert.equal(uri.serialize({ ...base, port: '8443' }), 'https://example.test:8443/app');
});

test('Les adresses link-local et NAT64 locales ne sont pas classées publiques', () => {
  for (const host of ['fe80::1', 'fe81::1', 'febf::1']) {
    assert.equal(new Address6(host).isLinkLocal(), true);
  }
  for (const host of ['64:ff9b:1::7f00:1', '64:ff9b:1:a9fe:a9:fe00::']) {
    assert.equal(new Address6(host).isPrivate(), true);
  }
  const globalAddress = new Address6('2001:4860:4860::8888');
  assert.equal(globalAddress.isLinkLocal(), false);
  assert.equal(globalAddress.isPrivate(), false);
});
