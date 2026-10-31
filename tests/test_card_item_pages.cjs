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
