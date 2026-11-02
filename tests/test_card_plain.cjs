// 2 November 2026: posting the text as it is keeps what the reading found, so the back room's "Readings changed by
// their writers" lists a reading its writer set aside.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const CANDIDATES = {issues: {climate: {name: 'Climate', parent_key: null}}, solutions: {}, evidence: {}};

test('posting the text as it is keeps the reading the writer set aside', async () => {
  const p = await setup('SpeechRecognition', CANDIDATES);
  await p.type('Majority votes would work better');
  await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Climate'}], solutions: [], evidence: []}, message: '', source: 'model', extraction_raw: 'RAW',
    model: 'reader', latency_ms: 5});
  await p.flush();
  await p.get('plain').emit('click'); await p.flush();
  await p.runTimer(200);
  p.requests.at(-1).resolve({sentences: ['x'], valid: true, dropped: [], corrected: []}); await p.flush();
  p.get('post').emit('click'); await p.flush();
  const sent = p.requests.at(-1);
  assert.equal(sent.url, '/api/posts');
  sent.resolve({id: 'p1', message: 'Added to the database'}); await p.flush();
  const body = JSON.parse(sent.options.body);
  assert.equal(body.plain, true);
  assert.equal(body.source, 'manual');
  assert.equal(body.extraction_raw, 'RAW');
  assert.equal(body.model, 'reader');
});
