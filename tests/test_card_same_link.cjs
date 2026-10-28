// 24 October 2026: the same link counts as the same evidence. A row whose link the record already
// holds takes that evidence's name, shows "existing" and says so under the row.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const NOTE = 'This evidence is already in the database.';
const candidates = {issues: {flooding: {name: 'Flooding', parent_key: null}}, solutions: {},
  evidence: {'old report': 'Old report', 'other report': 'Other report'},
  evidence_links: {'example.org/report': 'old report', 'example.org/other': 'other report'}};

async function cardWith(evidence) {
  const p = await setup(candidates); await p.flush();
  await p.type('Flooding is getting worse'); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Flooding'}], solutions: [], evidence}, source: 'model', extraction_raw: '{}', model: 'reader', latency_ms: 5});
  await p.flush();
  const row = p.get('evidence-rows').children[0];
  const name = row.children[1], badge = row.children[2], link = row.children[4];
  const note = row.children.find(child => child.className === 'link-note');
  return {p, row, name, badge, link, note};
}

test('a link the record holds gives the row the existing name, the badge and the note', async () => {
  const {name, badge, note} = await cardWith([{name: 'Flood study 2024', url: 'https://www.example.org/report/', stance: 'supports', about: 'Flooding'}]);
  assert.equal(name.value, 'Old report');
  assert.equal(badge.textContent, 'existing');
  assert.equal(note.textContent, NOTE);
  assert.equal(note.hidden, false);
});

test('a link not in the record is new and says nothing', async () => {
  const {name, badge, note} = await cardWith([{name: 'Flood study 2024', url: 'https://example.org/report?page=2', stance: 'supports', about: 'Flooding'}]);
  assert.equal(name.value, 'Flood study 2024');
  assert.equal(badge.textContent, 'new');
  assert.equal(note.hidden, true);
});

test('typing a link that the record holds renames the row once; the writer may still change the name', async () => {
  const {row, name, badge, link, note} = await cardWith([{name: 'Flood study 2024', url: '', stance: 'supports', about: 'Flooding'}]);
  assert.equal(badge.textContent, 'new');
  link.value = 'http://example.org/report#top'; await row.emit('input');
  assert.equal(name.value, 'Old report');
  assert.equal(note.hidden, false);
  // Renaming to another piece the record holds: the name rule decides, and the note goes.
  name.value = 'Other report'; await row.emit('input');
  assert.equal(name.value, 'Other report');
  assert.equal(badge.textContent, 'existing');
  assert.equal(note.hidden, true);
  // Renaming to new words: the link still joins the existing evidence, so the note stays.
  name.value = 'My own words'; await row.emit('input');
  assert.equal(name.value, 'My own words');
  assert.equal(badge.textContent, 'existing');
  assert.equal(note.hidden, false);
});

test('an existing name is not overwritten by a link that belongs to another piece', async () => {
  const {name, badge, note} = await cardWith([{name: 'Other report', url: 'https://example.org/report', stance: 'supports', about: 'Flooding'}]);
  assert.equal(name.value, 'Other report');
  assert.equal(badge.textContent, 'existing');
  assert.equal(note.hidden, true);
});
