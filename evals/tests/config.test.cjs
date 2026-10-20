const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const yaml = require('yaml');

test('Les évaluations locales ne déclarent aucun fournisseur externe ni juge distant', () => {
  const config = yaml.parse(fs.readFileSync('archive/promptfooconfig.local.yaml', 'utf8'));
  assert.ok(config.providers.length > 0);
  for (const provider of config.providers) {
    assert.equal(provider.id, 'openai:chat:local');
    assert.equal(provider.config.apiBaseUrl, '{{env.LITELLM_BASE_URL}}');
    assert.equal(provider.config.apiKeyEnvar, 'CONFIDENTIAL_KEY');
    assert.equal(provider.config.apiKey, undefined);
  }
  assert.ok(config.tests.length >= 4);
  for (const example of config.tests) {
    assert.ok(example.assert.length > 0);
    assert.ok(example.assert.every(a => ['is-json', 'contains', 'not-contains', 'javascript'].includes(a.type)));
  }
});

test('Les assertions locales sont des expressions exécutables et refusent une source inventée', () => {
  const config = yaml.parse(fs.readFileSync('archive/promptfooconfig.local.yaml', 'utf8'));
  for (const example of config.tests) {
    for (const assertion of example.assert.filter(a => a.type === 'javascript')) {
      const evaluate = new Function('output', `return (${assertion.value});`);
      const known = example.vars.document !== 'Aucun';
      assert.equal(evaluate(JSON.stringify({
        runbook_source: known ? 'test-pool.md' : null,
        actions_proposees: known ? ['Vérifier le nombre de connexions actives.'] : [],
      })), true);
      assert.equal(evaluate(JSON.stringify({
        runbook_source: 'invented.md', actions_proposees: ['Action sans preuve.'],
      })), false);
    }
  }
});
