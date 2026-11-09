// John, 9 November 2026: a solution row the member already approves or opposes says so, since "no position" on the
// form never withdraws a stance (card.js, `held` from /api/candidates, Q58).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const CANDIDATES = {issues: {'security council veto': {name: 'Security Council veto', parent_key: null}},
  solutions: {'abolish the veto': 'Abolish the veto', 'expand the council': 'Expand the council'}, evidence: {},
  held: {'abolish the veto': 'approve', 'expand the council': 'oppose'}};
const note = row => row.children.find(child => child.className === 'held-note');
const shown = row => (note(row).hidden ? '' : note(row).textContent);

async function readWith(p, solutions) {
  await p.type('The veto should go'); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Security Council veto'}], solutions, evidence: []},
    source: 'model', extraction_raw: '{"found": true}', model: 'reader', latency_ms: 5});
  await p.flush();
}

test('a solution the member approves or opposes says so, whatever the radios say', async () => {
  const p = await setup(undefined, CANDIDATES, {member: 'John Kintree'}); await p.flush();
  await readWith(p, [{name: 'Abolish the veto', for_issue: 'Security Council veto', stance: 'none'},
    {name: 'expand the Council', for_issue: 'Security Council veto', stance: 'approve'},
    {name: 'Rotate the seats', for_issue: 'Security Council veto', stance: 'approve'}]);
  const rows = p.get('solution-rows').children;
  assert.deepEqual(rows.map(shown), ['You approve this already.', 'You oppose this already.', '']);
});

test('a row typed by hand says so once its name is a solution the member holds a stance on', async () => {
  const p = await setup(undefined, CANDIDATES, {member: 'John Kintree'}); await p.flush();
  await readWith(p, []);
  await p.get('add-solution').emit('click');
  const row = p.get('solution-rows').children.at(-1);
  assert.equal(shown(row), '');
  row.children[1].value = 'Abolish the veto'; await row.emit('input');
  assert.equal(shown(row), 'You approve this already.');
  row.children[1].value = 'Abolish the veto now'; await row.emit('input');
  assert.equal(shown(row), '');
});

test('without stances, as on the passphrase site, no row says anything', async () => {
  const {held, ...without} = CANDIDATES;
  const p = await setup(undefined, without); await p.flush();
  await readWith(p, [{name: 'Abolish the veto', for_issue: 'Security Council veto', stance: 'none'}]);
  assert.equal(shown(p.get('solution-rows').children[0]), '');
});

test('the edit page says nothing: the post\'s own rows hold its stance', async () => {
  const p = await setup(undefined, CANDIDATES, {member: 'John Kintree'});
  p.get('edit-post').textContent = JSON.stringify({id: 'post-1', text: 'The veto should go', anonymous: false,
    card: {issues: [{name: 'Security Council veto', parent: null}],
      solutions: [{name: 'Abolish the veto', for_issue: 'Security Council veto', stance: 'approve'}], evidence: []}});
  p.load('edit_post.js'); await p.flush();
  assert.equal(shown(p.get('solution-rows').children[0]), '');
});
