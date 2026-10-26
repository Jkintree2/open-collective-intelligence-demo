// Follow-up questions under the card's new rows (followups.js), driven through the card hook with a fake card.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const {Element} = require('./page_harness.js');

const MISSING = 'Where did you read or hear this?';

function card(rows) {
  const window = {};
  const context = {window, document: {createElement: tag => Object.assign(new Element(), {tag})}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/followups.js'), 'utf8'), context, {filename: 'followups.js'});
  const node = (tag, content, className) => {
    const element = Object.assign(new Element(), {tag});
    if (content) element.textContent = content;
    if (className) element.className = className;
    return element;
  };
  const make = (name, badge, more = {}) => {
    const row = {element: new Element(), name: Object.assign(new Element(), {value: name}),
      badge: Object.assign(new Element(), {textContent: badge}), ...more};
    return row;
  };
  const groups = {issues: [], solutions: [], evidence: []};
  for (const [group, name, badge, more] of rows) groups[group].push(make(name, badge, more));
  const text = Object.assign(new Element(), {value: 'Rents doubled in our town.'});
  const requests = [];
  let changes = 0;
  const request = (url, body) => new Promise((resolve, reject) => requests.push({url, body, resolve, reject}));
  assert.equal(window.ociCardExtras.length, 1);
  const extra = window.ociCardExtras[0]({request, node, text, changed: () => { changes++; }, state: {groups}});
  const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
  const boxes = row => row.element.children.filter(child => child.className === 'follow-up');
  const find = (box, test) => {
    const walk = element => [element, ...(element.children || []).flatMap(child => child instanceof Element ? walk(child) : [])];
    return walk(box).find(test);
  };
  return {extra, groups, text, requests, flush, boxes, find, changes: () => changes};
}

test('only new named rows are sent, with their link and tick', async () => {
  const page = card([['issues', 'Rent rises', 'new'], ['issues', 'Housing', 'existing'], ['solutions', '', ''],
    ['evidence', 'A survey', 'new', {url: Object.assign(new Element(), {value: ' https://example.org '}),
      personal: Object.assign(new Element(), {checked: false})}]]);
  page.extra.opened();
  await page.flush();
  assert.equal(page.requests.length, 1);
  assert.equal(page.requests[0].url, '/api/follow-ups');
  assert.deepEqual(JSON.parse(JSON.stringify(page.requests[0].body)), {text: 'Rents doubled in our town.', rows: [
    {row: 'issue', name: 'Rent rises', existing: false, url: null, personal: false},
    {row: 'evidence', name: 'A survey', existing: false, url: 'https://example.org', personal: false}]});
});

test('no new row, no request', async () => {
  const page = card([['issues', 'Housing', 'existing']]);
  page.extra.opened();
  await page.flush();
  assert.equal(page.requests.length, 0);
});

test('a question shows under its row; the answer is added as one line and the card is not read again', async () => {
  const page = card([['issues', 'Rent rises', 'new'], ['solutions', 'Build homes', 'new']]);
  page.extra.opened();
  await page.flush();
  page.requests[0].resolve({questions: [{row: 'issue', name: 'rent rises', kind: 'who', text: 'Who is most affected?'},
    {row: 'issue', name: 'Something else', kind: 'who', text: 'Who?'}]});
  await page.flush();
  const issue = page.groups.issues[0];
  const [box] = page.boxes(issue);
  assert.ok(box);
  assert.equal(page.boxes(page.groups.solutions[0]).length, 0);
  assert.equal(box.children[0].textContent, 'A question that would make this clearer:');
  assert.equal(box.children[1].textContent, 'Who is most affected?');
  assert.equal(find(box, 'Your answer is added to your statement, so everyone who reads the post sees it.', page), true);
  const input = page.find(box, element => element.tag === 'input');
  input.value = '  Families   with children ';
  const add = page.find(box, element => element.textContent === 'Add to my statement');
  await add.emit('click');
  assert.equal(page.text.value, 'Rents doubled in our town.\nWho is most affected? Families with children');
  assert.equal(page.boxes(issue).length, 0);
  assert.equal(page.changes(), 1);  // the preview follows; nothing else is asked
  assert.equal(page.requests.length, 1);
});

function find(box, words, page) {
  return Boolean(page.find(box, element => element.textContent === words));
}

test('an empty answer adds nothing; Skip removes the box', async () => {
  const page = card([['issues', 'Rent rises', 'new']]);
  page.extra.opened();
  await page.flush();
  page.requests[0].resolve({questions: [{row: 'issue', name: 'Rent rises', kind: 'where', text: 'Where is this?'}]});
  await page.flush();
  const [box] = page.boxes(page.groups.issues[0]);
  await page.find(box, element => element.textContent === 'Add to my statement').emit('click');
  assert.equal(page.text.value, 'Rents doubled in our town.');
  assert.equal(page.boxes(page.groups.issues[0]).length, 1);
  await page.find(box, element => element.textContent === 'Skip').emit('click');
  assert.equal(page.boxes(page.groups.issues[0]).length, 0);
  assert.equal(page.text.value, 'Rents doubled in our town.');
});

test('Enter in the answer box adds it instead of sending the form, and typing is not a change to the row', async () => {
  const page = card([['issues', 'Rent rises', 'new']]);
  page.extra.opened();
  await page.flush();
  page.requests[0].resolve({questions: [{row: 'issue', name: 'Rent rises', kind: 'when', text: 'When did this start?'}]});
  await page.flush();
  const [box] = page.boxes(page.groups.issues[0]);
  const input = page.find(box, element => element.tag === 'input');
  let stopped = 0;
  await input.emit('input', {stopPropagation() { stopped++; }});
  assert.equal(stopped, 1);
  input.value = 'In 2023.';
  let prevented = false;
  await input.emit('keydown', {key: 'Enter', preventDefault() { prevented = true; }});
  assert.ok(prevented);
  assert.equal(page.text.value, 'Rents doubled in our town.\nWhen did this start? In 2023.');
});

test('an answer that would make the statement too long is not added', async () => {
  const page = card([['issues', 'Rent rises', 'new']]);
  page.text.value = 'x'.repeat(3990);
  page.extra.opened();
  await page.flush();
  page.requests[0].resolve({questions: [{row: 'issue', name: 'Rent rises', kind: 'who', text: 'Who is affected?'}]});
  await page.flush();
  const [box] = page.boxes(page.groups.issues[0]);
  page.find(box, element => element.tag === 'input').value = 'Everyone here';
  await page.find(box, element => element.textContent === 'Add to my statement').emit('click');
  assert.equal(page.text.value.length, 3990);
  assert.ok(page.find(box, element => /longer than this demo/.test(element.textContent || '')));
});

test('the missing source question goes once the row has a link or the tick', async () => {
  const url = Object.assign(new Element(), {value: ''}), personal = Object.assign(new Element(), {checked: false});
  const page = card([['evidence', 'A survey', 'new', {url, personal}]]);
  page.extra.opened();
  await page.flush();
  page.requests[0].resolve({questions: [{row: 'evidence', name: 'A survey', kind: 'where', text: MISSING, fixed: true}]});
  await page.flush();
  const row = page.groups.evidence[0];
  assert.equal(page.boxes(row).length, 1);
  personal.checked = true;
  await personal.emit('change');
  assert.equal(page.boxes(row).length, 0);
});

test('a failed request shows nothing, and a reply for an earlier opening is ignored', async () => {
  const page = card([['issues', 'Rent rises', 'new']]);
  page.extra.opened();
  await page.flush();
  page.requests[0].reject(new Error('Too many requests.'));
  await page.flush();
  assert.equal(page.boxes(page.groups.issues[0]).length, 0);
  page.extra.opened();
  await page.flush();
  page.extra.opened();
  await page.flush();
  page.requests[1].resolve({questions: [{row: 'issue', name: 'Rent rises', kind: 'who', text: 'Who is affected?'}]});
  await page.flush();
  assert.equal(page.boxes(page.groups.issues[0]).length, 0);
  page.requests[2].resolve({questions: [{row: 'issue', name: 'Rent rises', kind: 'who', text: 'Who is affected?'}]});
  await page.flush();
  assert.equal(page.boxes(page.groups.issues[0]).length, 1);
});
