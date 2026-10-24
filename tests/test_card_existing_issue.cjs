// 24 October 2026 (John's email of that day): an issue the record already holds says so under its row,
// not only in the small badge.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const NOTE = 'This issue is already in the record.';
const candidates = {issues: {flooding: {name: 'Flooding', parent_key: null}}, solutions: {}, evidence: {}};

async function cardWith(issues) {
  const p = await setup(candidates); await p.flush();
  await p.type('Flooding is getting worse'); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues, solutions: [], evidence: []}, source: 'model', extraction_raw: '{}', model: 'reader', latency_ms: 5});
  await p.flush();
  const row = p.get('issue-rows').children[0];
  const name = row.children[1], badge = row.children[2];
  const note = row.children.find(child => child.className === 'issue-note');
  return {row, name, badge, note};
}

test('an issue the record holds shows the badge and the note under the row', async () => {
  const {badge, note} = await cardWith([{name: 'Flooding'}]);
  assert.equal(badge.textContent, 'existing');
  assert.equal(note.textContent, NOTE);
  assert.equal(note.hidden, false);
});

test('a new issue says nothing, and the note follows the name as it is edited', async () => {
  const {row, name, badge, note} = await cardWith([{name: 'Erosion'}]);
  assert.equal(badge.textContent, 'new');
  assert.equal(note.hidden, true);
  name.value = 'Flooding'; await row.emit('input');
  assert.equal(badge.textContent, 'existing');
  assert.equal(note.hidden, false);
});
