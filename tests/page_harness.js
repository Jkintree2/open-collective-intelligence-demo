// The fake page every .cjs test drives: a DOM of on-demand elements, a fake fetch, timers and
// speech recognition, with card.js, dictation.js and app.js loaded in page order. No browser.
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

class Element {
  constructor() { this.value = ''; this.hidden = false; this.disabled = false; this.checked = false;
    this.style = {}; this.children = []; this.listeners = {}; this.attributes = {}; this.scrollHeight = 120; }
  addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
  emit(name, event = {}) { return Promise.all((this.listeners[name] || []).map(fn => fn({preventDefault() {}, ...event}))); }
  setAttribute(name, value) { this.attributes[name] = value; }
  append(...children) { for (const child of children) if (child instanceof Element) child.parent = this; this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  add(child) { this.children.push(child); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); }
  after() {}
  focus() {}
  querySelectorAll() { return []; }
}
async function setup(speech = 'SpeechRecognition', candidates = {issues: {}, solutions: {}, evidence: {}}, options = {}) {
  // Candidates may be passed alone, as the only thing a card test cares about.
  if (speech && typeof speech === 'object') { candidates = speech; speech = 'SpeechRecognition'; }
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  get('card').hidden = true;
  // A signed-in write page carries the account's name on the form (sub-plan A, members.posting_identity).
  if (options.member) get('compose').dataset = {member: options.member};
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
    if (url === '/api/candidates') return Promise.resolve({ok: true, status: 200, json: async () => candidates});
    // The feed fragment after a post is read as text, as the page reads it.
    if (url === '/feed') return Promise.resolve({ok: true, status: 200, redirected: false, text: async () => ''});
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
    window: win, location, Option: class extends Element { constructor(text, value) { super(); this.text = text; this.value = value; } },
    AbortController, URLSearchParams, fetch,
    setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, {fn, delay}); return id; },
    clearTimeout: id => timers.delete(id)};
  // The page loads these in this order (index.html); app.js wires up what the first two define.
  vm.createContext(context);
  for (const file of ['card.js', 'dictation.js', 'app.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static', file), 'utf8'), context, {filename: file});
  }
  const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
  await flush();
  const type = async value => { get('text').value = value; await get('text').emit('input'); };
  // The fired callback is not awaited: a preview timer waits on a request the test resolves afterwards.
  const runTimer = async delay => { for (const [id, timer] of [...timers]) if (timer.delay === delay) { timers.delete(id); timer.fn(); } await flush(); };
  // Another script from app/static/, run in this same page after the three above.
  const load = file => vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static', file), 'utf8'), context, {filename: file});
  return {get, recognizers, requests, type, flush, runTimer, win, location, load};
}

module.exports = {Element, setup};
