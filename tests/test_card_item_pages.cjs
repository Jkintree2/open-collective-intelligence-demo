// GitHub issue 55: the write page opened from a solution's or a piece of evidence's page. The reading is told
// which, and the card starts from the issue the summary above the form names (data-issue-key).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const ISSUES = {issues: {
  'world': {name: 'World', parent_key: null},
  'climate': {name: 'Climate', parent_key: 'world'}}, solutions: {'carbon tax': 'Carbon tax'}, evidence: {}};

test('reading from a solution page sends the solution, and from an evidence page the evidence', async () => {
  for (const [search, sent] of [['?solution=carbon%20tax', {solution: 'carbon tax'}],
                                ['?evidence=who%20pays', {evidence: 'who pays'}]]) {
    const {get, type, requests, location} = await setup();
    location.search = search;
    await type('Statement'); await get('compose').emit('submit');
    const body = JSON.parse(requests[0].options.body);
    assert.equal(body.issue, null);
    for (const [name, value] of Object.entries(sent)) assert.equal(body[name], value);
  }
});

test('an issue in the address is sent alone, as before', async () => {
  const {get, type, requests, location} = await setup();
  location.search = '?issue=veto&solution=carbon%20tax';
  await type('Statement'); await get('compose').emit('submit');
  const body = JSON.parse(requests[0].options.body);
  assert.equal(body.issue, 'veto');
  assert.equal('solution' in body, false);
});

test('the card starts from the issue the summary names, with that issue\'s family', async () => {
  const {get, flush, location} = await setup(ISSUES);
  location.search = '?solution=carbon%20tax';
  get('about-issue').dataset = {issue: 'Climate', issueKey: 'climate'};
  await get('stop').emit('click'); await flush();
  const rows = get('issue-rows').children;
  assert.equal(rows[0].children[1].value, 'Climate');
  const parent = rows[0].children.find(c => c.tag === 'select');
  assert.equal(parent.value, 'World');
  await get('add-issue').emit('click');
  const labels = rows[1].children.find(c => c.tag === 'select').children.map(c => c.label || c.value);
  assert.ok(labels.includes('About World'));
});

test('a summary that names no issue starts the card empty', async () => {
  const {get, flush} = await setup(ISSUES);
  get('about-issue').dataset = {issue: '', issueKey: ''};
  await get('stop').emit('click'); await flush();
  assert.equal(get('issue-rows').children[0].children[1].value, '');
});

// John, 31 October 2026, after trying the live pages: the form on a solution's or a piece of evidence's write page
// holds what that page is about, and posting goes back to the page.
const TWO = {issues: {
  'need for world government': {name: 'Need for world government', parent_key: null},
  'methods of collective decision making': {name: 'Methods of collective decision making', parent_key: null}},
  solutions: {'decisions by consensus': 'Decisions by consensus'}, evidence: {'who pays': 'Who pays'}};
const CONSENSUS = {issue: 'Need for world government', issueKey: 'need for world government',
  issueKeys: '["need for world government","methods of collective decision making"]', solution: 'Decisions by consensus'};
const issueNames = p => p.get('issue-rows').children.map(row => row.children[1].value);
const evidenceRow = p => { const [stance, about] = p.get('evidence-rows').children.at(-1).children.filter(c => c.tag === 'select'); return {stance: stance.value, about: about.value}; };

test('a solution proposed for two issues starts the card with both', async () => {
  const p = await setup(TWO);
  p.location.search = '?solution=decisions%20by%20consensus';
  p.get('about-issue').dataset = {...CONSENSUS};
  await p.get('stop').emit('click'); await p.flush();
  assert.deepEqual(issueNames(p), ['Need for world government', 'Methods of collective decision making']);
});

test('a reading that names one of the solution\'s issues gets the other added after it', async () => {
  const p = await setup(TWO);
  p.location.search = '?solution=decisions%20by%20consensus';
  p.get('about-issue').dataset = {...CONSENSUS};
  await p.type('Majority votes'); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Methods of collective decision making'}], solutions: [], evidence: []}, source: 'model'});
  await p.flush();
  assert.deepEqual(issueNames(p), ['Methods of collective decision making', 'Need for world government']);
});

test('an evidence page adds no issue to a reading that found its own, as before', async () => {
  const p = await setup(TWO);
  p.location.search = '?evidence=who%20pays';
  p.get('about-issue').dataset = {issue: 'Need for world government', issueKey: 'need for world government', evidence: 'Who pays'};
  await p.type('Something'); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Methods of collective decision making'}], solutions: [], evidence: []}, source: 'model'});
  await p.flush();
  assert.deepEqual(issueNames(p), ['Methods of collective decision making']);
});

test('evidence added by hand on a solution page is about that solution, and refutes it once the writer opposes it', async () => {
  const p = await setup(TWO);
  p.get('about-issue').dataset = {...CONSENSUS};
  await p.get('stop').emit('click'); await p.flush();
  await p.get('add-evidence').emit('click');
  assert.deepEqual(evidenceRow(p), {stance: 'supports', about: 'Decisions by consensus'});
  p.load('about_issue.js');
  await p.get('about-issue').emit('change', {target: {type: 'radio', dataset: {solution: 'Decisions by consensus'}, value: 'oppose', name: 'about-0-consensus'}});
  await p.get('add-evidence').emit('click');
  assert.deepEqual(evidenceRow(p), {stance: 'refutes', about: 'Decisions by consensus'});
});

test('evidence added by hand on an evidence page is about that evidence', async () => {
  const p = await setup(TWO);
  p.get('about-issue').dataset = {issue: 'Need for world government', issueKey: 'need for world government', evidence: 'Who pays'};
  await p.get('stop').emit('click'); await p.flush();
  await p.get('add-evidence').emit('click');
  assert.deepEqual(evidenceRow(p), {stance: 'supports', about: 'Who pays'});
});

test('evidence added by hand on the plain write page is still about the first issue on the form', async () => {
  const p = await setup(TWO);
  await p.get('stop').emit('click'); await p.flush();
  p.get('issue-rows').children[0].children[1].value = 'Need for world government';
  await p.get('add-evidence').emit('click');
  assert.deepEqual(evidenceRow(p), {stance: 'supports', about: 'Need for world government'});
});

async function postFrom(dataset) {
  const p = await setup(TWO);
  p.get('about-issue').dataset = dataset;
  await p.type('Majority votes'); await p.get('stop').emit('click'); await p.flush();
  if (!dataset.issueKey) { p.get('issue-rows').children[0].children[1].value = 'Need for world government'; await p.get('issue-rows').children[0].emit('input'); }
  await p.runTimer(200);
  p.requests.at(-1).resolve({sentences: ['x'], valid: true, dropped: [], corrected: []}); await p.flush();
  p.get('post').emit('click'); await p.flush();
  assert.equal(p.requests.at(-1).url, '/api/posts');
  p.requests.at(-1).resolve({id: 'p1'}); await p.flush();
  return p;
}

test('posting from a solution or an evidence page goes back to that page', async () => {
  for (const back of ['/solutions/decisions%20by%20consensus', '/evidence/who%20pays']) {
    const p = await postFrom({...CONSENSUS, return: back});
    assert.equal(p.location.href, back);
  }
});

test('posting from the plain write page stays there', async () => {
  const p = await postFrom({});
  assert.equal(p.location.href, undefined);
  assert.equal(p.get('compose-message').textContent, 'Added to the database');
});
