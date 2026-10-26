// Phase 3: the Ask box, offline. The answer shows in place as text, the visit's last three questions go
// with the next one, never the answers, and the browser waits 50 seconds with a second line after 10.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; this.className = ''; this.attrs = {}; }
  append(...kids) { this.children.push(...kids); }
  prepend(...kids) { this.children.unshift(...kids); }
  get text() { return this.textContent + this.children.map(c => typeof c === 'string' ? c : c.text).join(''); }
  find(className) {
    if (this.className === className) return this;
    for (const child of this.children) { const hit = typeof child === 'object' && child.find(className); if (hit) return hit; }
    return null;
  }
}

function page(issue) {
  const status = new Node('p'), answers = new Node('div'), field = {value: ''};
  const box = {dataset: issue ? {issue} : {}, querySelector: s => ({'[data-ask-status]': status, '[data-ask-answers]': answers})[s]};
  const attrs = {};
  const form = {matches: s => s === 'form.ask-form', closest: () => box, querySelector: () => field,
    setAttribute: (k, v) => { attrs[k] = v; }, removeAttribute: k => { delete attrs[k]; }, hasAttribute: k => k in attrs};
  let submit; const requests = [], timers = new Map(); let timerId = 0;
  const location = {href: '/issues/veto', pathname: '/issues/veto', search: ''};
  const context = {
    document: {addEventListener: (name, fn) => { if (name === 'submit') submit = fn; },
      createElement: tag => new Node(tag), createTextNode: text => text},
    location, AbortController,
    setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, {fn, delay}); return id; },
    clearTimeout: id => timers.delete(id),
    fetch: (url, options) => new Promise(resolve => requests.push({url, options, resolve,
      body: JSON.parse(options.body)}))};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/ask.js'), 'utf8'), context);
  const ask = question => { field.value = question; const event = {target: form, prevented: false,
    preventDefault() { this.prevented = true; }}; const done = submit(event); return {event, done}; };
  const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };
  const fire = delay => { for (const [id, t] of [...timers]) if (t.delay === delay) { timers.delete(id); t.fn(); } };
  return {ask, status, answers, field, requests, flush, fire, timers, attrs, location};
}
const json = (data, status = 200) => ({ok: status < 400, status, json: async () => data});
const ANSWER = {status: 'answered', message: null, partial: null,
  paragraphs: [{text: 'Two writers oppose it <b>loudly</b>.', refs: [1, 2]}],
  sources: [{name: 'Anonymous', when: '30 October 2026', text: 'The veto blocks action.', issue: 'Security Council veto', href: '/issues/veto'},
            {name: 'Carbon tax', when: null, text: null, issue: 'Climate', href: '/issues/climate'}]};

test('an answer shows in place, as text, with its numbered sources', async () => {
  const p = page('veto');
  const {event} = p.ask('  Why   do people oppose it? ');
  assert.equal(event.prevented, true);
  assert.equal(p.requests.length, 1);
  assert.deepEqual(p.requests[0].body, {question: 'Why do people oppose it?', earlier: [], issue: 'veto'});
  assert.equal(p.status.textContent, 'Reading the record… The first question after a quiet spell can take a minute.');
  assert.equal(p.attrs['aria-busy'], 'true');
  p.requests[0].resolve(json(ANSWER)); await p.flush();
  assert.equal(p.status.textContent, '');
  const block = p.answers.children[0];
  assert.equal(block.find('ask-question').textContent, 'Why do people oppose it?');
  assert.equal(block.find('ask-paragraph').text, 'Two writers oppose it <b>loudly</b>. [1] [2]');  // text, never markup
  const sources = block.find('ask-sources');
  assert.equal(sources.children[0].text, 'Anonymous, 30 October 2026: “The veto blocks action.” On Security Council veto');
  assert.equal(sources.children[0].children[2].href, '/issues/veto');
  assert.equal(sources.children[1].text, 'Carbon tax. On Climate');
  assert.equal(p.field.value, '');
  assert.equal('aria-busy' in p.attrs, false);
});

test('the last three questions go with the next one, never the answers', async () => {
  const p = page();
  for (const q of ['one?', 'two?', 'three?', 'four?']) {
    p.ask(q); p.requests.at(-1).resolve(json(ANSWER)); await p.flush();
  }
  p.ask('five?');
  assert.deepEqual(p.requests.at(-1).body, {question: 'five?', earlier: ['two?', 'three?', 'four?'], issue: null});
  assert.equal(JSON.stringify(p.requests.at(-1).body).includes('Two writers'), false);
  assert.equal(p.answers.children[0].find('ask-question').textContent, 'four?');  // newest first
});

test('a question that cannot go ahead is never sent', async () => {
  const p = page();
  p.ask('   ');
  assert.equal(p.status.textContent, 'Please write a question.');
  p.ask('x'.repeat(501));
  assert.equal(p.status.textContent, 'Please keep the question under 500 characters.');
  assert.equal(p.requests.length, 0);
});

test('a second line after ten seconds, and the browser gives up after fifty', async () => {
  const p = page();
  p.ask('Why?');
  assert.deepEqual([...p.timers.values()].map(t => t.delay).sort((a, b) => a - b), [10000, 50000]);
  p.fire(10000);
  assert.equal(p.status.textContent, 'Reading the record… The first question after a quiet spell can take a minute. '
    + 'Still reading. A long issue can take up to a minute.');
  p.fire(50000);
  assert.equal(p.requests[0].options.signal.aborted, true);
});

test('a late, refused or unreadable reply says so; a limit says its own line', async () => {
  const p = page();
  p.ask('Why?');
  p.requests[0].resolve({ok: false, status: 502, json: async () => { throw new SyntaxError('<html>'); }}); await p.flush();
  assert.equal(p.status.textContent, 'The question could not be answered just now. Please try again in a minute.');
  p.ask('Why?');
  p.requests[1].resolve(json({message: 'You have asked 30 questions today. Please ask again tomorrow.'}, 429)); await p.flush();
  assert.equal(p.status.textContent, 'You have asked 30 questions today. Please ask again tomorrow.');
  p.ask('Why?');
  p.requests[2].resolve(json({message: 'Something went wrong. Please try again in a minute.'}, 500)); await p.flush();
  assert.equal(p.status.textContent, 'The question could not be answered just now. Please try again in a minute.');
  assert.equal(p.answers.children.length, 0);
});

test('no reading service: the line shows and the question is not kept', async () => {
  const p = page();
  p.ask('Why?');
  p.requests[0].resolve(json({message: 'Asking needs the reading service, which is not set up.'})); await p.flush();
  assert.equal(p.answers.children[0].find('ask-message').textContent, 'Asking needs the reading service, which is not set up.');
  p.ask('Again?');
  assert.deepEqual(p.requests[1].body.earlier, []);
});

test('an empty answer shows the empty line', async () => {
  const p = page();
  p.ask('Mars?');
  p.requests[0].resolve(json({status: 'empty', message: 'The record does not say anything about this yet.', paragraphs: [], sources: []}));
  await p.flush();
  assert.equal(p.answers.children[0].find('ask-message').textContent, 'The record does not say anything about this yet.');
});

test('signed out on the way goes to the door', async () => {
  const p = page();
  p.ask('Why?');
  p.requests[0].resolve(json({message: 'Please sign in again.', redirect: '/sign-in'}, 401)); await p.flush();
  assert.equal(p.location.href, '/sign-in?next=' + encodeURIComponent('/issues/veto'));
});

test('one question at a time', () => {
  const p = page();
  p.ask('Why?'); p.ask('Why again?');
  assert.equal(p.requests.length, 1);
});
