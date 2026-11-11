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

// Review of 11 November 2026: a Post tap waiting on a preview was handed on to the plain card, so a writer who
// pressed Post and then the plain link within a second posted a statement with no issue, believing they had pressed
// Post on the card they saw.
test('Post then plain posts nothing until Post is pressed again', async () => {
  const p = await setup(undefined, CANDIDATES, {member: 'Ada Tester'});
  await p.type('Majority votes would work better');
  await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Climate'}], solutions: [], evidence: []}, message: '', source: 'model', extraction_raw: 'RAW',
    model: 'reader', latency_ms: 5});
  await p.flush(); await p.runTimer(200);
  p.requests.at(-1).resolve({sentences: ['Ada Tester claims about existing issue Climate'], valid: true, dropped: [], corrected: []});
  await p.flush();
  p.get('anonymous').checked = true; await p.get('anonymous').emit('change'); await p.flush();
  p.get('post').emit('click'); await p.flush();  // waits on the preview the tick started
  await p.get('plain').emit('click'); await p.flush();
  assert.deepEqual(p.get('sentences').children, []);  // the lines of the card as it was are gone at once
  await p.runTimer(200);
  for (const r of p.requests.filter(r => r.url === '/api/preview')) r.resolve({sentences: [], valid: true, dropped: [], corrected: []});
  await p.flush(); await p.flush();
  assert.equal(p.requests.filter(r => r.url === '/api/posts').length, 0);
  p.get('post').emit('click'); await p.flush();  // pressed again, on the plain card: now it posts
  const sent = p.requests.filter(r => r.url === '/api/posts');
  assert.equal(sent.length, 1);
  assert.equal(JSON.parse(sent[0].options.body).plain, true);
});
