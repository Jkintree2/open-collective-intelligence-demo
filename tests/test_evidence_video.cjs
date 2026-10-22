// Revision round, YouTube videos: a video whose captions cannot be read asks for the transcript; what is
// pasted is sent to be read for that link only; the reading says where in the video, or that it was pasted.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const VIDEO = 'https://www.youtube.com/watch?v=AbCdEfGhIj0';
const reading = evidence => ({payload: {found: true, language_ok: true, issues: [{name: 'Four day week'}], solutions: [],
  evidence}, source: 'model', extraction_raw: '{}', model: 'reader', latency_ms: 5});
const fields = row => ({stance: row.children[6], about: row.children[8]});
const box = row => fields(row).about.afterNodes[0];
const lines = row => box(row).children.filter(c => c.tag === 'p').map(c => c.textContent);
const checks = p => p.requests.filter(r => r.url === '/api/check-evidence');
const QUOTE = 'After six months, fifty six of the sixty one companies chose to keep the four day week.';

async function videoRow() {
  const p = await setup(undefined, undefined, {evidenceCheck: true}); await p.flush();
  await p.type('The trial talk shows a four day week works. ' + VIDEO); await p.get('compose').emit('submit');
  p.requests.find(r => r.url === '/api/extract').resolve(reading([{name: 'Trial talk', url: VIDEO, stance: 'supports',
    about: 'Four day week'}]));
  await p.flush();
  return {p, row: p.get('evidence-rows').children[0]};
}

test('a video is read as a video, and its sentence says where it is', async () => {
  const {p, row} = await videoRow();
  assert.equal(lines(row)[0], 'Reading the video…');
  checks(p)[0].resolve({verdict: 'supports', quote: QUOTE, quote_at: '0:14', pasted: false, video: true,
    line: 'A news video from March 2024. Secondary source.', suggested: {}});
  await p.flush();
  assert.deepEqual(lines(row).filter(Boolean), ['Agrees', `The video says at 0:14: "${QUOTE}"`,
    'A news video from March 2024. Secondary source.']);
});

test('no captions: the transcript box, and the paste is read for this link only', async () => {
  const {p, row} = await videoRow();
  checks(p)[0].resolve({verdict: 'nocaptions', quote: null, line: null, video: true, suggested: {}}); await p.flush();
  assert.deepEqual(lines(row), ["Could not read this video's captions. Paste the transcript below and it will be read."]);
  const area = box(row).children.find(c => c.tag === 'textarea');
  const button = box(row).children.find(c => c.tag === 'button');
  assert.equal(button.textContent, 'Read the transcript');
  assert.equal(area.maxLength, 60000);
  await button.emit('click');
  assert.equal(checks(p).length, 1);                                // nothing pasted, nothing sent
  area.value = '0:14\n' + QUOTE;
  await button.emit('click'); await p.flush();
  assert.equal(lines(row)[0], 'Reading the transcript…');
  const asked = JSON.parse(checks(p)[1].options.body);
  assert.equal(asked.url, VIDEO); assert.equal(asked.transcript, '0:14\n' + QUOTE);
  checks(p)[1].resolve({verdict: 'supports', quote: QUOTE, quote_at: '0:14', pasted: true, video: true,
    line: 'A video from 2025. Read from a transcript the writer pasted.', suggested: {}});
  await p.flush();
  assert.deepEqual(lines(row).filter(Boolean), ['Agrees', `The transcript says at 0:14: "${QUOTE}"`,
    'A video from 2025. Read from a transcript the writer pasted.']);
  await p.runTimer(200);
  const preview = JSON.parse(p.requests.at(-1).options.body);
  assert.deepEqual(preview.evidence[0].check, {verdict: 'supports', quote: QUOTE});   // the paste is never in the card
});
