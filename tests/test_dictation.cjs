// Offline DOM and Web Speech API regression checks. No microphone or browser is used.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

class Element {
  constructor() { this.value = ''; this.hidden = false; this.disabled = false; this.checked = false;
    this.style = {}; this.children = []; this.listeners = {}; this.attributes = {}; this.scrollHeight = 120; }
  addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
  emit(name, event = {}) { return Promise.all((this.listeners[name] || []).map(fn => fn({preventDefault() {}, ...event}))); }
  setAttribute(name, value) { this.attributes[name] = value; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  add(child) { this.children.push(child); }
  remove() {}
  after() {}
  focus() {}
  querySelectorAll() { return []; }
}
async function setup(speech = 'SpeechRecognition') {
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  get('card').hidden = true;
  const recognizers = [], requests = [], timers = new Map();
  let timerId = 0;
  class Recognition {
    constructor() { recognizers.push(this); }
    start() { this.started = true; }
    abort() { this.aborted = true; this.onend?.(); }
    result(...values) { this.onresult({results: values.map(value => [{transcript: value}])}); }
  }
  const win = new Element(); if (speech) win[speech] = Recognition;
  const fetch = (url, options = {}) => {
    if (url === '/api/candidates') return Promise.resolve({ok: true, status: 200, json: async () => ({issues: {}, solutions: {}, evidence: {}})});
    return new Promise(resolve => requests.push({url, options,
      resolve: data => resolve({ok: true, status: 200, json: async () => data}),
      // No body means a reply that is not ours, such as a gateway page during a restart.
      fail: (status, body) => resolve({ok: false, status, json: async () => {
        if (body === undefined) throw new SyntaxError('Unexpected token <');
        return body;
      }})}));
  };
  const location = {search: ''};
  const context = {document: {getElementById: get, createElement: tag => Object.assign(new Element(), {tag}), createTextNode: text => text},
    window: win, location, Option: class extends Element { constructor(text, value) { super(); this.value = value; } },
    AbortController, URLSearchParams, fetch,
    setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, {fn, delay}); return id; },
    clearTimeout: id => timers.delete(id)};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8'), context);
  const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
  await flush();
  const type = async value => { get('text').value = value; await get('text').emit('input'); };
  const runTimer = async delay => { for (const [id, timer] of [...timers]) if (timer.delay === delay) { timers.delete(id); await timer.fn(); } await flush(); };
  return {get, recognizers, requests, type, flush, runTimer, win, location};
}

test('dictation is hidden without recognition; standard and prefixed APIs are configured', async () => {
  assert.equal((await setup(null)).get('dictate').hidden, true);
  for (const api of ['SpeechRecognition', 'webkitSpeechRecognition']) {
    const {get, recognizers} = await setup(api);
    assert.equal(get('dictate').hidden, false);
    await get('dictate').emit('click');
    assert.equal(get('dictate').textContent, 'Listening… press to stop');
    assert.equal(get('dictate').attributes['aria-pressed'], 'true');
    assert.equal(recognizers[0].continuous, true);
    assert.equal(recognizers[0].interimResults, true);
  }
});

test('interim revisions replace speech, typed edits survive and automatic end restarts', async () => {
  const {get, type, recognizers} = await setup();
  await type('Typed introduction.'); await get('dictate').emit('click');
  const first = recognizers[0];
  first.result('Coast'); first.result('Coastal flooding');
  assert.equal(get('text').value, 'Typed introduction. Coastal flooding');
  await type('Edited introduction. Coastal flooding matters.');
  first.result('Flooding revised', 'We need seawalls.');
  assert.equal(get('text').value, 'Edited introduction. Coastal flooding matters. We need seawalls.');
  first.onend(); assert.equal(recognizers.length, 2);
  first.result('late old cycle');
  recognizers[1].result('A new sentence.');
  assert.equal(get('text').value, 'Edited introduction. Coastal flooding matters. We need seawalls. A new sentence.');
  await get('dictate').emit('click');
  assert.equal(recognizers[1].aborted, true);
  assert.equal(get('dictate').attributes['aria-pressed'], 'false');
  recognizers[1].result('late'); recognizers[1].onend();
  assert.equal(recognizers.length, 2);
  assert.ok(!get('text').value.endsWith('late'));
});

test('typing during an interim result retains its continuing words without duplicates', async () => {
  const {get, type, recognizers} = await setup();
  await type('Intro.'); await get('dictate').emit('click');
  const current = recognizers[0];
  current.result('Coastal flooding');
  await type('Corrected intro. Coastal flooding');
  current.result('Coastal flooding threatens');
  assert.equal(get('text').value, 'Corrected intro. Coastal flooding threatens');
  current.result('Coastal flooding threatens our homes');
  current.result('Coastal flooding threatens our homes');
  assert.equal(get('text').value, 'Corrected intro. Coastal flooding threatens our homes');
  current.result('Coastal flooding threatens our homes', 'We should prepare.');
  assert.equal(get('text').value, 'Corrected intro. Coastal flooding threatens our homes We should prepare.');
  await type('Corrected intro. Coastal flooding threatens our homes We must prepare.');
  current.result('Coastal flooding threatens our homes', 'We should prepare. Today.');
  assert.equal(get('text').value, 'Corrected intro. Coastal flooding threatens our homes We must prepare. Today.');
});

test('speech respects the Unicode character cap and clears listening on errors or navigation', async () => {
  const {get, type, recognizers, win} = await setup();
  await type('😀'.repeat(3998)); await get('dictate').emit('click');
  recognizers[0].result('abc');
  assert.equal([...get('text').value].length, 4000);
  assert.equal(recognizers[0].aborted, true);
  assert.equal(get('dictate').disabled, true);
  assert.match(get('compose-message').textContent, /^That is longer than this demo can read at once\./);
  await type('Hello'); await get('dictate').emit('click');
  recognizers[1].onerror({error: 'not-allowed'});
  assert.equal(get('dictate').attributes['aria-pressed'], 'false');
  recognizers[1].onend(); assert.equal(recognizers.length, 2);
  await get('dictate').emit('click'); await win.emit('pagehide');
  assert.equal(recognizers[2].aborted, true);
});

test('read, manual form and post stop recognition before capturing text', async () => {
  for (const action of ['read', 'skip', 'post']) {
    const {get, type, recognizers, requests} = await setup();
    await type('Initial statement'); await get('dictate').emit('click');
    recognizers[0].result('spoken');
    if (action === 'read') await get('compose').emit('submit');
    else if (action === 'post') { get('post').disabled = false; get('post').emit('click'); }
    else await get('skip').emit('click');
    assert.equal(recognizers[0].aborted, true, action);
    recognizers[0].result('late text');
    assert.equal(get('text').value, 'Initial statement spoken');
    if (action !== 'skip') assert.equal(JSON.parse(requests[0].options.body).text, 'Initial statement spoken');
  }
});

test('cancel and timeout abandon late reading responses and preserve manual edits', async () => {
  for (const timeout of [false, true]) {
    const {get, type, requests, runTimer, flush} = await setup();
    await type('Statement'); await get('compose').emit('submit');
    assert.equal(get('text').readOnly, true); assert.equal(get('dictate').disabled, true);
    assert.equal(get('stop').hidden, false);
    await runTimer(8000);
    assert.equal(get('compose-message').textContent, 'Still reading. This can take up to half a minute.');
    if (timeout) await runTimer(25000); else await get('stop').emit('click');
    assert.equal(get('text').readOnly, false); assert.equal(get('card').hidden, false);
    if (timeout) assert.equal(get('retry').hidden, false);
    await type('Manually corrected');
    requests[0].resolve({payload: {language_ok: true, issues: [{name: 'Late issue'}]}, source: 'model'});
    await flush();
    assert.equal(get('text').value, 'Manually corrected');
    assert.equal(get('issue-rows').children.at(-1).children[1].value, '');
  }
});

test('a reply that is not ours reads as the reading service not answering', async () => {
  const {get, type, requests, flush} = await setup();
  await type('Statement'); await get('compose').emit('submit');
  requests[0].fail(502);
  await flush();
  assert.equal(get('card').hidden, false);
  assert.equal(get('card-message').textContent, 'The reading service is not answering right now. You can fill in the form by hand, or try again in a minute.');
  assert.equal(get('retry').hidden, false);
});

test('an expired passphrase sends the writer back to the gate', async () => {
  const {get, type, requests, flush, location} = await setup();
  await type('Statement'); await get('compose').emit('submit');
  requests[0].fail(401, {message: 'Please enter the passphrase again.', redirect: '/enter'});
  await flush();
  assert.equal(location.href, '/enter');
  assert.equal(get('card-message').textContent, 'Please enter the passphrase again.');
});

test('card name fields are wrapping text areas capped at 300 characters', async () => {
  const {get} = await setup();
  await get('skip').emit('click');
  const control = get('issue-rows').children.at(-1).children[1];
  assert.equal(control.tag, 'textarea');
  assert.equal(control.maxLength, 300);
  assert.equal(control.rows, 1);
});

test('overlong paste leaves text unchanged and explains the limit', async () => {
  const {get, type} = await setup();
  await type('Keep me'); get('text').selectionStart = 7; get('text').selectionEnd = 7;
  let prevented = false;
  await get('text').emit('paste', {clipboardData: {getData: () => 'x'.repeat(4000)}, preventDefault: () => { prevented = true; }});
  assert.equal(prevented, true); assert.equal(get('text').value, 'Keep me');
});
