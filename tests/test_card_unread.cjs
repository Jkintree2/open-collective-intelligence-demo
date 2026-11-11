// John, 31 October 2026: on a solution's Write page the card is open on arrival, so a statement written beside it
// could be posted without ever being read, and his counter proposal was lost that way. The card now says so.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const UNREAD = 'Your statement has not been read yet. Press "Read my statement" to fill in the form from it.';
const CANDIDATES = {issues: {climate: {name: 'Climate', parent_key: null}}, solutions: {}, evidence: {}};

async function openFirst(options = {}) {
  const p = await setup('SpeechRecognition', CANDIDATES, options);
  await p.get('stop').emit('click'); await p.flush();  // the card open before anything is written
  return p;
}

test('a statement written beside a card that was never read says so', async () => {
  const p = await openFirst();
  assert.equal(p.get('card-message').textContent, '');
  await p.type('Majority votes and Roberts rules of order would work better');
  assert.equal(p.get('card-message').textContent, UNREAD);
  await p.type('');
  assert.equal(p.get('card-message').textContent, '');
});

test('once the statement is read the line goes, and editing the statement afterwards does not bring it back', async () => {
  const p = await openFirst();
  await p.type('Majority votes would work better');
  await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Climate'}], solutions: [{name: 'Majority votes', for_issue: 'Climate', stance: 'approve'}], evidence: []},
    message: '', source: 'model', extraction_raw: '{}', model: 'reader', latency_ms: 5});
  await p.flush();
  assert.equal(p.get('card-message').textContent, '');
  await p.type('Majority votes would work much better');
  assert.equal(p.get('card-message').textContent, '');
});

test('a reading that could not run does not ask for another one', async () => {
  const p = await openFirst();
  await p.type('Majority votes would work better');
  await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').fail(503, {message: 'The language model is not answering right now.'});
  await p.flush();
  assert.notEqual(p.get('card-message').textContent, UNREAD);
});

// Since John's "Asking" email (11 November 2026) the plain card has a line of its own (tests/test_card_plain.cjs).
test('no unread line without a language model, or when posting the text as it is', async () => {
  const off = await openFirst({noReading: true});
  await off.type('Majority votes would work better');
  assert.equal(off.get('card-message').textContent, '');
  const plain = await setup('SpeechRecognition', CANDIDATES);
  await plain.type('Majority votes would work better');
  await plain.get('plain').emit('click'); await plain.flush();
  assert.equal(plain.get('card-message').textContent,
    'Your statement will be posted on its own. It will not be listed under any issue.');
});

// Review of 11 November 2026: when the names in the database could not be fetched as the page loaded (a restart
// during a deploy), Post never came on and nothing tried again, leaving the plain link as the only way to post.
test('the card asks for the names again when the first try failed', async () => {
  let calls = 0;
  const names = () => (++calls === 1 ? null : {issues: {climate: {name: 'Climate', parent_key: null}}, solutions: {}, evidence: {}});
  const p = await setup(undefined, names, {});
  assert.equal(p.win.oci.card.state.candidatesReady, false);
  await p.type('The river floods every spring.');
  await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve({payload: {found: true, language_ok: true,
    issues: [{name: 'Climate'}], solutions: [], evidence: []}, message: '', source: 'model', extraction_raw: 'RAW',
    model: 'reader', latency_ms: 5});
  await p.flush(); await p.flush();
  assert.equal(calls, 2);
  assert.equal(p.win.oci.card.state.candidatesReady, true);
  await p.runTimer(200);
  assert.ok(p.requests.some(r => r.url === '/api/preview'));
});
