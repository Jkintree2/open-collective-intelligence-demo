// John, 22 Oct 2026: a link on an evidence row is evidence even when the row has no words beside it.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

test('an evidence row with a link and no name is still sent', async () => {
  const p = await setup(); await p.flush();
  await p.type('Ending sanctions on Russian oil hurts Ukraine'); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Sanctions on Russian oil'}], solutions: [],
    evidence: [{name: 'Reuters report', url: 'https://www.reuters.com/world/', stance: 'supports', about: 'Sanctions on Russian oil'}]},
    source: 'model', extraction_raw: '{}', model: 'reader', latency_ms: 5});
  await p.flush();
  const row = p.get('evidence-rows').children[0];
  const name = row.children[1];
  name.value = ''; await row.emit('input');
  await p.runTimer(200);
  const body = JSON.parse(p.requests.at(-1).options.body);
  assert.deepEqual(body.evidence.map(e => [e.name, e.url]), [['', 'https://www.reuters.com/world/']]);
});
