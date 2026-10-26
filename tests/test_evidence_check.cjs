// Phase 2: each evidence link on the card is read, and the row says what the page says. The writer
// keeps the last word on supports or refutes, and Post never waits for a reading.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const URL = 'https://news.example.org/story';
const QUOTE = 'A survey of forty coastal towns found flooding days doubled since 2000.';
const reading = evidence => ({payload: {found: true, language_ok: true, issues: [{name: 'Coastal flooding'}], solutions: [],
  evidence}, source: 'model', extraction_raw: '{}', model: 'reader', latency_ms: 5});
const fields = row => ({name: row.children[1], url: row.children[4], stance: row.children[6], about: row.children[8]});
const box = row => fields(row).about.afterNodes[0];
const lines = row => box(row).children.filter(c => c.tag === 'p').map(c => c.textContent);
const checks = p => p.requests.filter(r => r.url === '/api/check-evidence');

async function readWith(p, evidence) {
  await p.type('Coastal flooding is worse. ' + URL); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve(reading(evidence)); await p.flush();
  return p.get('evidence-rows').children;
}

test('a link the reading found is read at once and the row says what the page says', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [row] = await readWith(p, [{name: 'Forty town survey', url: URL, stance: 'refutes', about: 'Coastal flooding'}]);
  assert.equal(checks(p).length, 1);
  assert.deepEqual(JSON.parse(checks(p)[0].options.body), {url: URL, evidence: 'Forty town survey', about: 'Coastal flooding',
    text: 'Coastal flooding is worse. ' + URL, stance: 'refutes'});
  assert.deepEqual(lines(row), ['Reading the page…']);
  checks(p)[0].resolve({verdict: 'supports', quote: QUOTE, line: 'A news report from March 2024. Secondary source.', suggested: {}});
  await p.flush();
  assert.deepEqual(lines(row), ['Agrees', `The page says: "${QUOTE}"`, 'A news report from March 2024. Secondary source.', '']);
  assert.equal(fields(row).stance.value, 'supports');            // set from the reading: the writer had not chosen
  await p.runTimer(200);
  const preview = JSON.parse(p.requests.at(-1).options.body);
  assert.deepEqual(preview.evidence[0].check, {verdict: 'supports', quote: QUOTE});
});

test('once the writer chooses, the reading does not change it and says they differ', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [row] = await readWith(p, [{name: 'Survey', url: URL, stance: 'supports', about: 'Coastal flooding'}]);
  const {stance} = fields(row);
  stance.value = 'supports'; await stance.emit('change');
  checks(p)[0].resolve({verdict: 'refutes', quote: QUOTE, line: null, suggested: {}}); await p.flush();
  assert.equal(stance.value, 'supports');
  assert.equal(lines(row).at(-1), BOTH_REFUTES);
  stance.value = 'refutes'; await stance.emit('change');
  assert.equal(lines(row).at(-1), '');
});

// Issue 29: a page read as taking a side the writer did not choose is added on its own side, and the
// writer's statement on theirs; the row says so, and choosing the page's side adds the page alone.
const BOTH_REFUTES = 'The page refutes this and your statement supports it, so both will be added, each on its own side. To add only the page, choose refutes.';
const BOTH_SUPPORTS = 'The page supports this and your statement refutes it, so both will be added, each on its own side. To add only the page, choose supports.';

test('a page that agrees under a writer who refutes says both will be added, until the writer matches it', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [row] = await readWith(p, [{name: 'Climate change article', url: URL, stance: 'refutes', about: 'Coastal flooding'}]);
  const {stance} = fields(row);
  stance.value = 'refutes'; await stance.emit('change');
  checks(p)[0].resolve({verdict: 'supports', quote: QUOTE, line: null, suggested: {}}); await p.flush();
  assert.equal(stance.value, 'refutes');                         // the writer's side stays theirs
  assert.equal(lines(row).at(-1), BOTH_SUPPORTS);
  await p.runTimer(200);
  const preview = JSON.parse(p.requests.at(-1).options.body).evidence[0];
  assert.deepEqual([preview.stance, preview.check], ['refutes', {verdict: 'supports', quote: QUOTE}]);
  stance.value = 'supports'; await stance.emit('change');
  assert.equal(lines(row).at(-1), '');
});

test('a link typed by hand is read when the writer leaves the field, and an old answer is ignored', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  await readWith(p, []);
  await p.get('add-evidence').emit('click');
  const [row] = p.get('evidence-rows').children; const {url, name} = fields(row);
  name.value = 'Survey'; url.value = 'https://first.example.org/'; await url.emit('change'); await p.flush();
  url.value = URL; await url.emit('change'); await p.flush();
  assert.equal(checks(p).length, 2);
  checks(p)[0].resolve({verdict: 'refutes', quote: 'old answer', suggested: {}});
  checks(p)[1].resolve({verdict: 'unclear', quote: null, line: 'A page. Date not given.', suggested: {}}); await p.flush();
  assert.equal(lines(row)[0], 'The page does not clearly say either way.');
  await url.emit('change'); await p.flush();
  assert.equal(checks(p).length, 2);                            // the same link and claim are not asked twice
});

test('what the page also mentions can be ticked onto the card and off again', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [row] = await readWith(p, [{name: 'Survey', url: URL, stance: 'supports', about: 'Coastal flooding'}]);
  checks(p)[0].resolve({verdict: 'supports', quote: QUOTE, line: null,
    suggested: {issues: [{name: 'Sea walls not keeping pace', existing: false}], solutions: [], evidence: [{name: 'NOAA tide gauges', existing: true}]}});
  await p.flush();
  const also = box(row).children.find(c => c.tag === 'fieldset');
  assert.equal(also.children[0].textContent, 'The page also mentions');
  assert.match(also.children[1].textContent, /^Tick any you want to add to your statement/);
  const [issue, evidence] = also.children.slice(2);
  assert.deepEqual([issue.children[1], evidence.children[1]], ['Issue: Sea walls not keeping pace', 'Evidence: NOAA tide gauges']);
  issue.children[0].checked = true; await issue.children[0].emit('change');
  assert.deepEqual(p.get('issue-rows').children.map(r => r.children[1].value), ['Coastal flooding', 'Sea walls not keeping pace']);
  evidence.children[0].checked = true; await evidence.children[0].emit('change'); await p.flush();
  const added = p.get('evidence-rows').children[1];
  assert.equal(fields(added).about.value, 'Coastal flooding');
  assert.equal(fields(added).url.value, URL);                  // keeps the link of the page it was found on
  assert.equal(checks(p).length, 2);
  checks(p)[1].resolve({verdict: 'supports', quote: QUOTE, line: null,
    suggested: {issues: [{name: 'Sea walls not keeping pace', existing: false}], solutions: [], evidence: []}});
  await p.flush();
  assert.equal(box(added).children.find(c => c.tag === 'fieldset'), undefined);   // and does not list the page again
  issue.children[0].checked = false; await issue.children[0].emit('change');
  assert.deepEqual(p.get('issue-rows').children.map(r => r.children[1].value), ['Coastal flooding']);
});

test('a page that cannot be read, and a busy reader, say so and keep no check', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [first, second] = await readWith(p, [{name: 'A', url: URL, about: 'Coastal flooding'},
                                             {name: 'B', url: 'https://x.example.org/r.pdf', about: 'Coastal flooding'}]);
  checks(p)[0].resolve({verdict: 'unread', quote: null, line: null, suggested: {}});
  checks(p)[1].fail(429, {message: 'Too many links read just now. Please wait a minute; you can still post.'}); await p.flush();
  assert.equal(lines(first)[0], 'Could not open this page.');
  assert.equal(lines(second)[0], 'Too many links read just now. Please wait a minute; you can still post.');
  await p.runTimer(200);
  const preview = JSON.parse(p.requests.at(-1).options.body);
  assert.deepEqual(preview.evidence.map(e => e.check), [{verdict: 'unread', quote: null}, undefined]);
});

test('a reading that fails says only that the page could not be opened', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [first, second] = await readWith(p, [{name: 'A', url: URL, about: 'Coastal flooding'},
                                             {name: 'B', url: 'https://y.example.org/', about: 'Coastal flooding'}]);
  checks(p)[0].fail(502); checks(p)[1].fail(403, {message: 'Please check the form and try again.'}); await p.flush();
  assert.equal(lines(first)[0], 'Could not open this page.');
  assert.equal(lines(second)[0], 'Could not open this page.');
  await p.runTimer(200);
  assert.deepEqual(JSON.parse(p.requests.at(-1).options.body).evidence.map(e => e.check), [undefined, undefined]);
});

test('without the flag nothing is read and the card is the Phase 1 card', async () => {
  const p = await setup(); await p.flush();
  const [row] = await readWith(p, [{name: 'Survey', url: URL, about: 'Coastal flooding'}]);
  await p.flush();
  assert.equal(checks(p).length, 0);
  assert.equal(fields(row).about.afterNodes, undefined);
});

test('a post being edited shows the reading it holds, and lists what else the page mentions', async () => {
  const p = await setup(undefined, {issues: {'coastal flooding': {name: 'Coastal flooding', parent_key: null}}, solutions: {}, evidence: {}},
                        {member: 'Ada Lovelace', evidenceCheck: true});
  const stored = {verdict: 'refutes', quote: QUOTE, line: 'A news report from March 2024. Secondary source.'};
  p.get('edit-post').textContent = JSON.stringify({id: 'post-1', text: 'Coastal flooding is worse.', anonymous: false,
    card: {issues: [{name: 'Coastal flooding', parent: null}], solutions: [],
           evidence: [{name: 'Survey', url: URL, stance: 'supports', about: 'Coastal flooding', check: stored}]}});
  p.load('edit_post.js'); await p.flush();
  const [row] = p.get('evidence-rows').children;
  assert.deepEqual(lines(row), ['Contradicts', `The page says: "${QUOTE}"`, stored.line,
    BOTH_REFUTES]);
  assert.equal(fields(row).stance.value, 'supports');  // the writer's choice stays
  // The page is read again only for what else it mentions (Beth, 22 October 2026): the stored reading stands,
  // whatever the fresh one says, and the list appears under it.
  assert.equal(checks(p).length, 1);
  checks(p)[0].resolve({verdict: 'supports', quote: 'another sentence', line: 'A page. Date not given.',
    suggested: {issues: [{name: 'Sea walls not keeping pace', existing: false}], solutions: [], evidence: []}});
  await p.flush();
  assert.deepEqual(lines(row), ['Contradicts', `The page says: "${QUOTE}"`, stored.line,
    BOTH_REFUTES]);
  assert.equal(fields(row).stance.value, 'supports');
  const also = box(row).children.find(c => c.tag === 'fieldset');
  assert.equal(also.children[0].textContent, 'The page also mentions');
  assert.equal(also.children[2].children[1], 'Issue: Sea walls not keeping pace');
  await p.runTimer(200);
  assert.deepEqual(JSON.parse(p.requests.at(-1).options.body).evidence[0].check, {verdict: 'refutes', quote: QUOTE});
  // A new link is read as usual.
  fields(row).url.value = 'https://other.example.org/'; await fields(row).url.emit('change'); await p.flush();
  assert.equal(checks(p).length, 2);
});

test('a post being edited with no reading service shows its reading and asks for nothing', async () => {
  const p = await setup(undefined, {issues: {'coastal flooding': {name: 'Coastal flooding', parent_key: null}}, solutions: {}, evidence: {}},
                        {member: 'Ada Lovelace', evidenceCheck: true, noReading: true});
  const stored = {verdict: 'refutes', quote: QUOTE, line: 'A news report from March 2024. Secondary source.'};
  p.get('edit-post').textContent = JSON.stringify({id: 'post-1', text: 'Coastal flooding is worse.', anonymous: false,
    card: {issues: [{name: 'Coastal flooding', parent: null}], solutions: [],
           evidence: [{name: 'Survey', url: URL, stance: 'supports', about: 'Coastal flooding', check: stored}]}});
  p.load('edit_post.js'); await p.flush();
  const [row] = p.get('evidence-rows').children;
  assert.equal(lines(row)[0], 'Contradicts');
  assert.equal(checks(p).length, 0);
});

test('a slow page says so after ten seconds, and the line goes when the reading comes', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [row] = await readWith(p, [{name: 'Survey', url: URL, about: 'Coastal flooding'}]);
  await p.runTimer(10000);
  assert.deepEqual(lines(row), ['Reading the page…', 'Still reading. A slow page can take up to a minute.']);
  checks(p)[0].resolve({verdict: 'supports', quote: QUOTE, line: null, suggested: {}}); await p.flush();
  assert.equal(lines(row)[0], 'Agrees');
  assert.ok(!lines(row).includes('Still reading. A slow page can take up to a minute.'));
});

test('an unclear reading says why, for example what the page does not say', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [row] = await readWith(p, [{name: 'Pol.is article', url: URL, about: 'Coastal flooding'}]);
  const reason = 'The page says 80% of 26 issues led to government action, not that they became law.';
  checks(p)[0].resolve({verdict: 'unclear', quote: null, reason, line: null, suggested: {}}); await p.flush();
  assert.deepEqual(lines(row).slice(0, 2), ['The page does not clearly say either way.', reason]);
});

// Revision round (04_interface.md, "Revision round: agrees, partly agrees, contradicts").
test('partly agrees shows the writer\'s sentence beside the page\'s, says what the page does not, and sets supports', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [row] = await readWith(p, [{name: 'Pol.is article', url: URL, stance: 'refutes', about: 'Coastal flooding'}]);
  const claim = 'The survey shows flooding days tripled.';
  const reason = 'The page says flooding days doubled, not tripled.';
  checks(p)[0].resolve({verdict: 'partly', quote: QUOTE, claim, reason, line: 'A news report. Date not given. Names its sources.', suggested: {}});
  await p.flush();
  assert.deepEqual(lines(row), ['Partly agrees', `You wrote: "${claim}"`, `The page says: "${QUOTE}"`, reason,
    'A news report. Date not given. Names its sources.', '']);
  assert.equal(fields(row).stance.value, 'supports');          // partly agrees counts as supports
  fields(row).stance.value = 'refutes'; await fields(row).stance.emit('change');
  assert.equal(lines(row).at(-1), 'You chose differently from the reading. That is fine; others will see both.');
  await p.runTimer(200);
  assert.deepEqual(JSON.parse(p.requests.at(-1).options.body).evidence[0].check, {verdict: 'partly', quote: QUOTE});
});

test('a row with no link says no source given, and the tick says personal experience and is posted', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  const [row] = await readWith(p, [{name: 'What I saw at the harbour', url: null, about: 'Coastal flooding'}]);
  await p.flush();
  assert.equal(checks(p).length, 0);                            // nothing to read
  assert.deepEqual(lines(row), ['No source given.']);
  const tick = box(row).children.find(c => c.tag === 'label');
  assert.equal(tick.children[1], 'From my own experience');
  tick.children[0].checked = true; await tick.children[0].emit('change'); await p.flush();
  assert.deepEqual(lines(row), ['From personal experience.']);
  await p.runTimer(200);
  assert.equal(JSON.parse(p.requests.at(-1).options.body).evidence[0].personal, true);
  // Typing a link clears the tick and the line; the link is read when the writer leaves the field.
  fields(row).url.value = URL; await fields(row).url.emit('input');
  assert.equal(tick.children[0].checked, false);
  assert.deepEqual(lines(row), []);
  await fields(row).url.emit('change'); await p.flush();
  assert.equal(checks(p).length, 1);
  await p.runTimer(200);
  assert.equal(JSON.parse(p.requests.at(-1).options.body).evidence[0].personal, undefined);
  // Removing the link brings the line back.
  fields(row).url.value = ''; await fields(row).url.emit('input');
  assert.deepEqual(lines(row), ['No source given.']);
});

test('an edited post keeps its personal experience tick', async () => {
  const p = await setup(undefined, {issues: {'coastal flooding': {name: 'Coastal flooding', parent_key: null}}, solutions: {}, evidence: {}},
                        {member: 'Ada Lovelace', evidenceCheck: true});
  p.get('edit-post').textContent = JSON.stringify({id: 'post-1', text: 'Coastal flooding is worse.', anonymous: false,
    card: {issues: [{name: 'Coastal flooding', parent: null}], solutions: [],
           evidence: [{name: 'What I saw', url: null, stance: 'supports', about: 'Coastal flooding', personal: true}]}});
  p.load('edit_post.js'); await p.flush();
  const [row] = p.get('evidence-rows').children;
  assert.deepEqual(lines(row), ['From personal experience.']);
});

test('without a reading service a link is not read, and a row with no link still says so', async () => {
  const p = await setup(undefined, undefined, {evidenceCheck: true, noReading: true}); await p.flush();
  const [linked, bare] = await readWith(p, [{name: 'Survey', url: URL, about: 'Coastal flooding'},
                                            {name: 'What I saw', url: null, about: 'Coastal flooding'}]);
  await p.flush();
  assert.equal(checks(p).length, 0);
  assert.deepEqual(lines(linked), []);
  assert.deepEqual(lines(bare), ['No source given.']);
});
