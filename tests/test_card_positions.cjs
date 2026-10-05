// GitHub issue 8: a position chosen in the panel above the box survives "Read my statement".
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const radios = row => row.children.find(c => c.tag === 'fieldset').children
  .filter(c => c.tag === 'label').map(label => label.children[0]);
const chosen = row => radios(row).find(r => r.checked).value;
const reading = (solutions = []) => ({payload: {found: true, language_ok: true,
  issues: [{name: 'Security Council veto'}], solutions, evidence: []},
  source: 'model', extraction_raw: '{"found": true}', model: 'reader', latency_ms: 5});

async function readWith(p, result) {
  await p.type('The veto should go'); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve(result); await p.flush();
}

// A tap on one of the panel's radios (about_issue.js, loaded into the page as index.html loads it).
async function panel(p, stance, solution = 'Abolish the veto') {
  const about = p.get('about-issue');
  if (!p.panelLoaded) { about.dataset = {issue: 'Security Council veto'}; p.load('about_issue.js'); p.panelLoaded = true; }
  await about.emit('change', {target: {type: 'radio', dataset: {solution}, value: stance, name: 'about-0-abolish'}});
}

test('a panel position survives read my statement', async () => {
  const p = await setup(); await p.flush();
  await panel(p, 'approve');
  await readWith(p, reading());
  const rows = p.get('solution-rows').children;
  assert.equal(rows.length, 1);
  assert.equal(rows[0].children[1].value, 'Abolish the veto');
  assert.equal(chosen(rows[0]), 'approve');
  await p.runTimer(200);
  const body = JSON.parse(p.requests.at(-1).options.body);
  assert.deepEqual(body.solutions.map(s => [s.name, s.stance]), [['Abolish the veto', 'approve']]);
});

test('the panel choice wins over a row the reading found for the same solution', async () => {
  const p = await setup(); await p.flush();
  await panel(p, 'oppose');
  await readWith(p, reading([{name: 'abolish the veto', for_issue: 'Security Council veto', stance: 'none'}]));
  const rows = p.get('solution-rows').children;
  assert.equal(rows.length, 1);
  assert.equal(chosen(rows[0]), 'oppose');
});

test('a position taken back in the panel is not brought back by a reading', async () => {
  const p = await setup(); await p.flush();
  await panel(p, 'approve');
  await panel(p, 'none');
  await readWith(p, reading());
  assert.equal(p.get('solution-rows').children.length, 0);
});

test('a position removed from the card stays removed', async () => {
  const p = await setup(); await p.flush();
  await panel(p, 'approve');
  const row = p.get('solution-rows').children[0];
  await row.children.find(c => c.textContent === 'remove from this form').emit('click');
  await readWith(p, reading());
  assert.equal(p.get('solution-rows').children.length, 0);
});

test('a plain statement carries no panel position', async () => {
  const p = await setup(); await p.flush();
  await panel(p, 'approve');
  await p.type('The veto should go');
  await p.get('plain').emit('click');
  assert.equal(p.get('solution-rows').children.length, 0);
});

test('dictating after a reading keeps what the reading returned', async () => {
  const p = await setup(); await p.flush();
  await readWith(p, reading());
  await p.get('dictate').emit('click');
  p.recognizers.at(-1).result('and the assembly should decide');
  await p.runTimer(200);
  const body = JSON.parse(p.requests.at(-1).options.body);
  assert.equal(body.source, 'manual');
  assert.equal(body.extraction_raw, '{"found": true}');
  assert.equal(body.model, 'reader');
  assert.equal(body.latency_ms, 5);
});
