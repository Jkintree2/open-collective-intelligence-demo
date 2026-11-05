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
    {member: 'Ada Tester', home: true, ociAsk, after: ['home.js'], ...options});
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
