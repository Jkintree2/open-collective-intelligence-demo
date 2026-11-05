// v0.3 Home, offline: one box for Write and Ask. home.js asks /api/home/kind what a text is, then starts the
// reading (app.js's ociStartReading) or the answer in place (ask.js's ociAsk, stubbed here), or shows the two
// buttons when the site can't tell. The link under the box switches a text from one to the other.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const {setup} = require('./page_harness.js');

const QUESTION = 'how does homelessness relate to the UDHR';
const STATEMENT = 'Data centers raise electricity prices.';

async function home(options = {}) {
  const asked = [];
  const ociAsk = (box, text) => new Promise(resolve => asked.push({box, text, resolve}));
  const page = await setup(undefined, {issues: {}, solutions: {}, evidence: {}},
    {member: 'Ada Tester', home: true, mine: 'm1', ociAsk, after: ['home.js'], ...options});
  const urls = () => page.requests.map(request => request.url);
  const kinds = () => page.requests.filter(request => request.url === '/api/home/kind');
  // The answer to the latest /api/home/kind request.
  const say = async kind => { kinds().at(-1).resolve({kind}); await page.flush(); };
  const send = async (text, submitter) => {
    if (text !== undefined) await page.type(text);
    await page.get('compose').emit('submit', submitter ? {submitter} : {});
    await page.flush();
  };
  return {...page, asked, urls, kinds, say, send};
}

test('the button keeps its Home words', async () => {
  const page = await home();
  assert.equal(page.get('read').textContent, 'Read my statement or question');
});

test('question goes to ask', async () => {
  const page = await home();
  await page.send(QUESTION);
  assert.deepEqual(page.kinds().map(request => JSON.parse(request.options.body)), [{text: QUESTION}]);
  assert.equal(page.kinds()[0].options.method, 'POST');
  await page.say('question');
  assert.equal(page.asked.length, 1);
  assert.equal(page.asked[0].text, QUESTION);
  assert.equal(page.asked[0].box, page.get('home-ask'));
  assert.equal(page.get('home-ask').hidden, false);
  assert.equal(page.get('home-switch').hidden, false);
  assert.equal(page.get('home-switch').textContent, 'Post it as a statement instead');
  assert.ok(!page.urls().includes('/api/extract'));
  page.asked[0].resolve({status: 'answered', question_id: 'q1'});
  await page.flush();
  assert.equal(page.get('text').value, '', 'an answered question leaves the box empty for the next one');
});

test('statement opens the card', async () => {
  const page = await home();
  await page.send(STATEMENT);
  await page.say('statement');
  assert.ok(page.urls().includes('/api/extract'), 'the reading started, as Read my statement starts it');
  assert.equal(page.asked.length, 0);
  assert.equal(page.get('home-switch').hidden, false);
  assert.equal(page.get('home-switch').textContent, 'Ask it as a question instead');
  assert.equal(page.get('home-ask').hidden, true);
});

test('unsure shows both buttons and each works', async () => {
  const page = await home();
  await page.send('What we need is a global referendum.');
  await page.say('unsure');
  assert.equal(page.get('home-unsure').hidden, false);
  assert.ok(!page.urls().includes('/api/extract'));
  assert.equal(page.asked.length, 0);
  await page.send(undefined, {name: 'kind', value: 'question'});
  assert.equal(page.kinds().length, 1, 'a chosen kind is not asked about again');
  assert.equal(page.asked.length, 1);
  assert.equal(page.get('home-unsure').hidden, true);

  const other = await home();
  await other.send('What we need is a global referendum.');
  await other.say('unsure');
  await other.send(undefined, {name: 'kind', value: 'statement'});
  assert.ok(other.urls().includes('/api/extract'));
  assert.equal(other.get('home-unsure').hidden, true);
});

test('switch link from answer to card and back', async () => {
  const page = await home();
  await page.send(QUESTION);
  await page.say('question');
  page.asked[0].resolve({status: 'answered', question_id: 'q1'});
  await page.flush();
  page.get('home-switch').click();  // not awaited: going the question way waits for the answer
  await page.flush();
  assert.equal(page.get('text').value, QUESTION, 'the question comes back into the box');
  assert.ok(page.urls().includes('/api/extract'));
  assert.equal(page.get('home-switch').textContent, 'Ask it as a question instead');
  page.get('home-switch').click();
  await page.flush();
  assert.equal(page.get('card').hidden, true, 'the reading is stopped and the card put away');
  assert.equal(page.asked.length, 2);
  assert.equal(page.asked[1].text, QUESTION);
  assert.equal(page.get('home-switch').textContent, 'Post it as a statement instead');
});

test('a second send while the first is still being sorted does nothing', async () => {
  const page = await home();
  await page.send(QUESTION);
  await page.send();
  assert.equal(page.kinds().length, 1);
});

test('when the kind cannot be had, the reading starts as before', async () => {
  const page = await home();
  await page.send(STATEMENT);
  page.kinds()[0].fail(502);
  await page.flush();
  assert.ok(page.urls().includes('/api/extract'));
});

test('dictation still fills the box', async () => {
  const page = await home();
  assert.equal(page.get('dictate').hidden, false);
  await page.get('dictate').emit('click');
  page.recognizers[0].result('data centers raise electricity prices');
  await page.flush();
  assert.match(page.get('text').value, /data centers raise electricity prices/);
  await page.send();
  assert.equal(JSON.parse(page.kinds()[0].options.body).text, page.get('text').value);
});

test('start set from another page runs on load', async () => {
  const page = await home({start: true, text: QUESTION});
  assert.equal(page.kinds().length, 1);
  assert.equal(JSON.parse(page.kinds()[0].options.body).text, QUESTION);
});

test('without asking (Home on, Ask off) the page reads as the Write page does', async () => {
  const page = await home({home: 'post-only'});
  assert.equal(page.get('read').textContent, 'Read my statement');
  await page.send(STATEMENT);
  assert.deepEqual(page.urls().filter(url => url !== '/api/home/kind'), page.urls());
  assert.ok(page.urls().includes('/api/extract'));
});

test('without Home the page is the Write page, even with home.js loaded', async () => {
  const page = await setup(undefined, {issues: {}, solutions: {}, evidence: {}}, {member: 'Ada Tester', after: ['home.js']});
  assert.equal(page.get('read').textContent, 'Read my statement');
  await page.type(STATEMENT);
  await page.get('compose').emit('submit', {});
  await page.flush();
  const urls = page.requests.map(request => request.url);
  assert.ok(urls.includes('/api/extract') && !urls.includes('/api/home/kind'));
});

// Review Focus 3: "Tell me more" right after a question on Home reads what the question before it read, so
// Home's box carries its earlier questions as the Ask box does (ask.js, the real file).
test('tell me more passes the earlier question', async () => {
  const requests = [];
  const node = () => ({textContent: '', children: [], className: '', append() {}, prepend(...kids) { this.children.unshift(...kids); }});
  const status = node(), answers = node(), attrs = {};
  const box = {dataset: {}, querySelector: selector => ({'[data-ask-status]': status, '[data-ask-answers]': answers})[selector] || null,
    setAttribute: (key, value) => { attrs[key] = value; }, removeAttribute: key => { delete attrs[key]; }, hasAttribute: key => key in attrs};
  const context = {location: {pathname: '/', search: ''}, AbortController,
    document: {addEventListener() {}, createElement: () => node(), createTextNode: text => text},
    setTimeout: () => 0, clearTimeout() {},
    fetch: (url, options) => new Promise(resolve => requests.push({url, body: JSON.parse(options.body),
      resolve: data => resolve({ok: true, status: 200, json: async () => data})}))};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/ask.js'), 'utf8'), context);
  const first = context.ociAsk(box, 'Why do people oppose the carbon tax?');
  await Promise.resolve();
  requests[0].resolve({status: 'answered', paragraphs: [], sources: []});
  assert.equal((await first).status, 'answered');
  const second = context.ociAsk(box, 'Tell me more');
  await Promise.resolve();
  assert.equal(requests[1].url, '/api/ask');
  assert.deepEqual(requests[1].body.earlier, ['Why do people oppose the carbon tax?']);
  assert.equal(requests[1].body.question, 'Tell me more');
  requests[1].resolve({status: 'answered', paragraphs: [], sources: []});
  await second;
});

// Task 5: My most recent statements and questions. The page draws the writer's statements; home.js adds the
// questions answered on this device (localStorage "oci.myQuestions", which ask.js keeps), newest first, five shown.
const {Element} = require('./page_harness.js');
function storage(questions, owner = 'm1') {
  const data = questions === undefined ? {} : {[`oci.myQuestions.${owner}`]: JSON.stringify(questions)};
  return {data, getItem: key => (key in data ? data[key] : null), setItem: (key, value) => { data[key] = String(value); }};
}
function statements(...rows) {
  return get => {
    get('home-mine').children = rows.map(([at, text]) => Object.assign(new Element(), {tag: 'li', textContent: text,
      dataset: {at, kind: 'statement'}}));
    get('home-mine-section').hidden = rows.length === 0;
  };
}
const shown = page => page.get('home-mine').children.map(item => item.dataset ? item.textContent
  : (item.children[0].href ? 'link ' + item.children[0].href + ' ' : 'button ') + item.children[0].textContent);

test('list mixes statements and device questions by time', async () => {
  const page = await home({prepare: statements(['2026-11-05T12:00:00Z', 'My noon statement.'],
                                               ['2026-11-05T10:00:00Z', 'My ten o\'clock statement.']),
    localStorage: storage([{id: 'q2', text: 'Asked at one?', at: '2026-11-05T13:00:00.000Z'},
                           {id: 'q1', text: 'Asked at eleven?', at: '2026-11-05T11:00:00.000Z'},
                           {id: null, text: 'Asked at nine?', at: '2026-11-05T09:00:00.000Z'},
                           {id: 'q0', text: 'Asked at eight?', at: '2026-11-05T08:00:00.000Z'}])});
  assert.deepEqual(shown(page), ['link /ask/answers/q2 Asked at one?', 'My noon statement.',
    'link /ask/answers/q1 Asked at eleven?', 'My ten o\'clock statement.', 'button Asked at nine?']);
  assert.equal(page.get('home-mine-section').hidden, false);
});

test('storage blocked still draws statements', async () => {
  const page = await home({prepare: statements(['2026-11-05T12:00:00Z', 'My noon statement.'])});
  assert.deepEqual(shown(page), ['My noon statement.']);
  const broken = await home({prepare: statements(['2026-11-05T12:00:00Z', 'My noon statement.']),
    localStorage: {getItem() { throw new Error('SecurityError'); }, setItem() { throw new Error('SecurityError'); }}});
  assert.deepEqual(shown(broken), ['My noon statement.']);
  const junk = await home({prepare: statements(['2026-11-05T12:00:00Z', 'My noon statement.']),
    localStorage: {getItem: () => '{not json', setItem() {}}});
  assert.deepEqual(shown(junk), ['My noon statement.']);
});

test('nothing posted and nothing asked keeps the list hidden; a first question shows it', async () => {
  const kept = storage([]);
  const asked = [];
  const page = await home({prepare: statements(), localStorage: kept,
    ociAsk: (box, text) => new Promise(resolve => asked.push({text, resolve}))});
  assert.equal(page.get('home-mine-section').hidden, true);
  await page.send(QUESTION);
  await page.say('question');
  kept.setItem('oci.myQuestions.m1', JSON.stringify([{id: 'q9', text: QUESTION, at: '2026-11-05T14:00:00.000Z'}]));
  asked[0].resolve({status: 'answered', question_id: 'q9'});
  await page.flush();
  assert.deepEqual(shown(page), [`link /ask/answers/q9 ${QUESTION}`]);
  assert.equal(page.get('home-mine-section').hidden, false);
});

test('question without id is a button that refills the box', async () => {
  const page = await home({prepare: statements(),
    localStorage: storage([{id: null, text: 'Is the veto fair?', at: '2026-11-05T09:00:00.000Z'}])});
  const button = page.get('home-mine').children[0].children[0];
  assert.equal(button.className, 'home-again');
  assert.equal(button.type, 'button');
  for (const listener of page.documentListeners.click) listener({target: {closest: s => (s === '.home-again' ? button : null)}});
  assert.equal(page.get('text').value, 'Is the veto fair?');
});

// ask.js keeps an answered question on this device for Home's list: newest first, at most 20, the same question
// once, and nothing at all when storage is blocked.
test('an answered question is kept on this device', async () => {
  const kept = storage();
  const requests = [];
  const node = () => ({textContent: '', children: [], className: '', append() {}, prepend() {}});
  const attrs = {};
  const box = {dataset: {}, querySelector: selector => ({'[data-ask-status]': node(), '[data-ask-answers]': node()})[selector] || null,
    setAttribute: (key, value) => { attrs[key] = value; }, removeAttribute: key => { delete attrs[key]; }, hasAttribute: key => key in attrs};
  const context = {location: {pathname: '/', search: ''}, AbortController, localStorage: kept,
    document: {addEventListener() {}, createElement: () => node(), createTextNode: text => text, body: {dataset: {mine: 'm1'}}},
    setTimeout: () => 0, clearTimeout() {},
    fetch: (url, options) => new Promise(resolve => requests.push({body: JSON.parse(options.body),
      resolve: data => resolve({ok: true, status: 200, json: async () => data})}))};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/ask.js'), 'utf8'), context);
  const askOnce = async (text, reply) => {
    const done = context.ociAsk(box, text);
    await Promise.resolve();
    requests.at(-1).resolve(reply);
    await done;
  };
  await askOnce('Is the veto fair?', {status: 'answered', question_id: 'a1', paragraphs: [], sources: []});
  await askOnce('Nothing to answer from?', {status: 'empty', paragraphs: [], sources: []});
  let items = JSON.parse(kept.data['oci.myQuestions.m1']);
  assert.deepEqual(items.map(item => [item.id, item.text]), [['a1', 'Is the veto fair?']]);
  assert.ok(!Number.isNaN(Date.parse(items[0].at)));
  for (let n = 0; n < 21; n++) await askOnce(`Question ${n}?`, {status: 'answered', question_id: `n${n}`, paragraphs: [], sources: []});
  await askOnce('is the veto fair', {status: 'answered', question_id: 'a2', paragraphs: [], sources: []});
  items = JSON.parse(kept.data['oci.myQuestions.m1']);
  assert.equal(items.length, 20);
  assert.deepEqual(items[0], {...items[0], id: 'a2', text: 'is the veto fair'});
  assert.equal(items.filter(item => item.text.toLowerCase().startsWith('is the veto fair')).length, 1);
});

// Found in the browser check (5 November).
test('a text brought from another page puts the address back to Home, so a reload does not post it again', async () => {
  const page = await home({start: true, text: QUESTION});
  assert.deepEqual(page.history.replaced, ['/']);
  const plain = await home();
  assert.deepEqual(plain.history.replaced, []);
});

test('typing something new puts the switch link and the two buttons away', async () => {
  const page = await home();
  await page.send(QUESTION);
  await page.say('question');
  assert.equal(page.get('home-switch').hidden, false);
  await page.type('Something else entirely.');
  assert.equal(page.get('home-switch').hidden, true);
  const other = await home();
  await other.send('What we need is a global referendum.');
  await other.say('unsure');
  await other.type('What we need is a global referendum now.');
  assert.equal(other.get('home-unsure').hidden, true);
});

// Final review, item 1: an answer that arrives after the writer sent the text the other way must not empty the box
// while the reading runs (the post would lose the writer's words).
test('switching to a statement while the answer is still coming keeps the words in the box', async () => {
  const page = await home();
  await page.send(QUESTION);
  await page.say('question');
  page.get('home-switch').click();
  await page.flush();
  assert.ok(page.urls().includes('/api/extract'));
  page.asked[0].resolve({status: 'answered', question_id: 'q1'});
  await page.flush();
  assert.equal(page.get('text').value, QUESTION);
  assert.equal(page.get('home-switch').textContent, 'Ask it as a question instead');
  assert.equal(page.get('home-ask').hidden, true);
});

// Final review, items 2 and 3: the questions kept on a device belong to the member the page names (an opaque name,
// never the account key), so a shared browser shows each member only their own; with Home off the page names no
// one and nothing is kept at all.
test('another member on the same browser does not see these questions', async () => {
  const kept = storage([{id: 'q1', text: 'Asked by someone else?', at: '2026-11-05T13:00:00.000Z'}], 'm2');
  const page = await home({prepare: statements(['2026-11-05T12:00:00Z', 'My noon statement.']), localStorage: kept});
  assert.deepEqual(shown(page), ['My noon statement.']);
});

test('with Home off nothing is kept on the device', async () => {
  const kept = storage();
  const requests = [];
  const node = () => ({textContent: '', children: [], className: '', append() {}, prepend() {}});
  const attrs = {};
  const box = {dataset: {}, querySelector: selector => ({'[data-ask-status]': node(), '[data-ask-answers]': node()})[selector] || null,
    setAttribute: (key, value) => { attrs[key] = value; }, removeAttribute: key => { delete attrs[key]; }, hasAttribute: key => key in attrs};
  const context = {location: {pathname: '/', search: ''}, AbortController, localStorage: kept,
    document: {addEventListener() {}, createElement: () => node(), createTextNode: text => text, body: {dataset: {}}},
    setTimeout: () => 0, clearTimeout() {},
    fetch: (url, options) => new Promise(resolve => requests.push({
      resolve: data => resolve({ok: true, status: 200, json: async () => data})}))};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/ask.js'), 'utf8'), context);
  const done = context.ociAsk(box, 'Is the veto fair?');
  await Promise.resolve();
  requests[0].resolve({status: 'answered', question_id: 'a1', paragraphs: [], sources: []});
  await done;
  assert.deepEqual(kept.data, {});
});
