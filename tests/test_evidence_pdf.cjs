// Revision round, PDFs: a scanned PDF's row says so in John's words, keeps no check and leaves the
// writer's supports or refutes alone.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const PDF = 'https://council.example.org/minutes-2019.pdf';
const reading = evidence => ({payload: {found: true, language_ok: true, issues: [{name: 'Coastal flooding'}], solutions: [],
  evidence}, source: 'model', extraction_raw: '{}', model: 'reader', latency_ms: 5});
const fields = row => ({stance: row.children[6], about: row.children[8]});
const lines = row => fields(row).about.afterNodes[0].children.filter(c => c.tag === 'p').map(c => c.textContent);
const checks = p => p.requests.filter(r => r.url === '/api/check-evidence');

test('a PDF with no text says exactly that and keeps no check', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  await p.type('The council minutes show flooding was discussed. ' + PDF); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve(reading([{name: 'Council minutes', url: PDF, stance: 'refutes',
    about: 'Coastal flooding'}]));
  await p.flush();
  const [row] = p.get('evidence-rows').children;
  checks(p)[0].resolve({verdict: 'notext', quote: null, reason: null, line: null, suggested: {}}); await p.flush();
  assert.equal(lines(row)[0], 'This PDF has no text that can be read.');
  assert.deepEqual(lines(row).filter(Boolean), ['This PDF has no text that can be read.']);
  assert.equal(fields(row).stance.value, 'refutes');               // not a side: the writer's choice stands
  await p.runTimer(200);
  const preview = JSON.parse(p.requests.at(-1).options.body);
  assert.equal(preview.evidence[0].check, undefined);              // not one of the verdicts a post may carry
});
