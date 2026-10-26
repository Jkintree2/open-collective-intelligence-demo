// Phase 3: the card hook. A script before card.js (followups.js, place.js) pushes a function onto
// window.ociCardExtras; card.js calls it once with its helpers, then row() for each row and opened() for the card.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const candidates = {issues: {flooding: {name: 'Flooding', parent_key: null}}, solutions: {}, evidence: {}};
const READING = {payload: {found: true, language_ok: true, issues: [{name: 'Flooding'}, {name: 'Erosion'}],
  solutions: [{name: 'Sea walls', for_issue: 'Erosion'}], evidence: [{name: 'Tide gauges', about: 'Erosion'}]},
  source: 'model', extraction_raw: '{}', model: 'reader', latency_ms: 5};

function recorder() {
  const seen = {helpers: [], rows: [], opened: []};
  const extra = helpers => {
    seen.helpers.push(helpers);
    return {
      row: (group, row, item) => seen.rows.push({group, name: item.name, badge: row.badge.textContent, row}),
      opened: (payload, meta) => seen.opened.push({payload, meta, rows: Object.values(helpers.state.groups).flat().length})
    };
  };
  return {seen, extra};
}

async function read(p) {
  await p.type('Flooding is getting worse and the coast is eroding'); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve(READING);
  await p.flush();
}

test('each extra is called once, with the same helpers the evidence check gets and the card state', async () => {
  const {seen, extra} = recorder();
  const p = await setup(undefined, candidates, {cardExtras: [extra]}); await p.flush();
  assert.equal(seen.helpers.length, 1);
  const helpers = seen.helpers[0];
  for (const name of ['find', 'request', 'node', 'changed', 'addRow', 'removeRow', 'updateText']) {
    assert.equal(typeof helpers[name], 'function', name);
  }
  assert.equal(helpers.text, p.get('text'));
  assert.deepEqual(Object.keys(helpers.state.groups), ['issues', 'solutions', 'evidence']);
});

test('row() is told about every row once it is filled in, and opened() once the card holds them all', async () => {
  const {seen, extra} = recorder();
  const p = await setup(undefined, candidates, {cardExtras: [extra]}); await p.flush();
  await read(p);
  assert.deepEqual(seen.rows.map(({group, name, badge}) => [group, name, badge]), [
    ['issues', 'Flooding', 'existing'], ['issues', 'Erosion', 'new'],
    ['solutions', 'Sea walls', 'new'], ['evidence', 'Tide gauges', 'new']]);
  assert.equal(seen.rows[2].row.for_issue.value, 'Erosion');
  assert.equal(seen.opened.length, 1);
  assert.equal(seen.opened[0].rows, 4);
  assert.equal(seen.opened[0].meta.source, 'model');
  assert.equal(seen.opened[0].payload.issues.length, 2);
});

test('a row added by hand is told too', async () => {
  const {seen, extra} = recorder();
  const p = await setup(undefined, candidates, {cardExtras: [extra]}); await p.flush();
  await read(p);
  await p.get('add-solution').emit('click');
  assert.deepEqual(seen.rows.at(-1).group, 'solutions');
  assert.equal(seen.opened.length, 1);
});

test('extras run in the order they were pushed, and one that answers nothing is fine', async () => {
  const order = [];
  const first = () => { order.push('first'); };
  const second = () => ({opened: () => order.push('second opened')});
  const p = await setup(undefined, candidates, {cardExtras: [first, second]}); await p.flush();
  await read(p);
  assert.deepEqual(order, ['first', 'second opened']);
  assert.equal(p.get('card').hidden, false);
});

test('an extra can add a line to the statement without the card being read again', async () => {
  let helpers;
  const p = await setup(undefined, candidates, {cardExtras: [h => { helpers = h; }]}); await p.flush();
  await read(p);
  const readings = p.requests.filter(r => r.url === '/api/extract').length;
  helpers.text.value += '\nWhen did this happen? In 2023.'; helpers.updateText(); helpers.changed();
  await p.flush();
  assert.equal(p.requests.filter(r => r.url === '/api/extract').length, readings);
  assert.equal(p.get('card').hidden, false);
  assert.equal(helpers.state.groups.issues.length, 2);
});

test('with no extras the card is as before', async () => {
  const p = await setup(candidates); await p.flush();
  await read(p);
  assert.equal(p.get('issue-rows').children.length, 2);
});
