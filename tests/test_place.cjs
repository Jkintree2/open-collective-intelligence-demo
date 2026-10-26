// Phase 3: the card's Place row (place.js, PLACES_ENABLED). The country starts as the account's for a named
// statement and empty for an anonymous one; a town needs a country; the place goes with the card as {country, area}.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const PLACES = {not_one_place: 'Not about one place', choices: [['DE', 'Germany'], ['US', 'United States']], country: 'US'};
const NEEDS_COUNTRY = 'Please choose the country for this town or area.';

async function page(options = {}, places = PLACES) {
  const p = await setup(undefined, undefined, {member: 'Ada Tester', before: ['place.js'], ...options});
  if (options.editing) p.get('edit-post').textContent = JSON.stringify(options.editing);
  if (places) p.requests.find(r => r.url === '/api/place').resolve(places);
  await p.flush();
  const row = p.get('add-evidence').afterNodes?.[0];
  return {...p, row, country: row.children[1], area: row.children[3], note: row.children[4], problem: row.children[5]};
}

async function sent(p) {
  await p.type('The river floods every spring'); await p.get('stop').emit('click'); await p.runTimer(200);
  return JSON.parse(p.requests.filter(r => r.url === '/api/preview').at(-1).options.body);
}

test('the row sits under the card rows, with the list and the town field labelled', async () => {
  const p = await page();
  assert.equal(p.row.className, 'place-row');
  assert.equal(p.row.hidden, false);
  assert.equal(p.row.children[0].textContent, 'Place');
  assert.equal(p.row.children[2].textContent, 'Town or area, optional');
  assert.deepEqual(p.country.children.map(option => [option.value, option.text]),
    [['', 'Not about one place'], ['DE', 'Germany'], ['US', 'United States']]);
  assert.equal(p.area.maxLength, 80);
});

test('a named statement starts at the account country and sends it', async () => {
  const p = await page();
  assert.equal(p.country.value, 'US');
  assert.equal(p.note.hidden, true);
  assert.deepEqual((await sent(p)).place, {country: 'US', area: null});
});

test('an anonymous statement starts empty and says what a town can tell', async () => {
  const p = await page();
  p.get('anonymous').checked = true; await p.get('anonymous').emit('change');
  assert.equal(p.country.value, '');
  assert.equal(p.note.hidden, false);
  assert.equal(p.note.textContent, 'A town can tell others who wrote an anonymous statement. Add one only if you are happy with that.');
  assert.deepEqual((await sent(p)).place, {country: null, area: null});
  // Back to the name: the account country again, as long as the writer has not chosen.
  p.get('anonymous').checked = false; await p.get('anonymous').emit('change');
  assert.equal(p.country.value, 'US');
});

test('the writer\'s own choice stays through a reading and the anonymous box', async () => {
  const p = await page();
  p.country.value = 'DE'; p.area.value = ' Hamburg '; await p.area.emit('input');
  p.get('anonymous').checked = true; await p.get('anonymous').emit('change');
  assert.equal(p.country.value, 'DE');
  assert.equal(p.note.hidden, false);
  assert.deepEqual((await sent(p)).place, {country: 'DE', area: 'Hamburg'});
});

test('a town with "Not about one place" asks for the country', async () => {
  const p = await page();
  p.country.value = ''; await p.country.emit('change');
  assert.equal(p.problem.textContent, '');
  p.area.value = 'Springfield'; await p.area.emit('input');
  assert.equal(p.problem.textContent, NEEDS_COUNTRY);
  p.country.value = 'US'; await p.country.emit('change');
  assert.equal(p.problem.textContent, '');
});

test('the edit page starts at the post\'s own place, whatever the account says', async () => {
  const editing = {id: 'post-1', text: 'Floods', anonymous: true, card: {issues: [], solutions: [], evidence: []},
    place: {country: 'DE', area: 'Hamburg'}};
  const p = await page({editing});
  assert.equal(p.country.value, 'DE');
  assert.equal(p.area.value, 'Hamburg');
  p.load('edit_post.js'); await p.flush();
  assert.equal(p.country.value, 'DE');
  const none = await page({editing: {...editing, place: {country: null, area: null}}});
  assert.equal(none.country.value, '');
});

test('without the list there is no row and the card sends no place', async () => {
  const p = await page({}, null);
  p.requests.find(r => r.url === '/api/place').fail(404, {message: 'Not found'});
  await p.flush();
  assert.equal(p.row.hidden, true);
  assert.equal('place' in await sent(p), false);
});

test('without place.js the card sends no place', async () => {
  const p = await setup(undefined, undefined, {member: 'Ada Tester'});
  assert.equal(p.requests.some(r => r.url === '/api/place'), false);
  await p.type('The river floods every spring'); await p.get('stop').emit('click'); await p.runTimer(200);
  assert.equal('place' in JSON.parse(p.requests.filter(r => r.url === '/api/preview').at(-1).options.body), false);
});

test('after a post the next statement starts afresh, empty when anonymous', async () => {
  const p = await page();
  await p.type('The river floods every spring'); await p.get('stop').emit('click');
  const row = p.get('issue-rows').children.at(-1);
  row.children[1].value = 'River flooding'; await row.emit('input');
  p.country.value = 'DE'; p.area.value = 'Hamburg'; await p.area.emit('input');
  await p.runTimer(200);
  p.requests.at(-1).resolve({sentences: ['x'], valid: true, dropped: [], corrected: []}); await p.flush();
  const clicking = p.get('post').emit('click'); await p.flush();
  const posted = p.requests.at(-1);
  assert.equal(posted.url, '/api/posts');
  assert.deepEqual(JSON.parse(posted.options.body).place, {country: 'DE', area: 'Hamburg'});
  posted.resolve({id: 'p1'}); await clicking; await p.flush();
  assert.deepEqual([p.country.value, p.area.value], ['US', '']);
  p.get('anonymous').checked = true; await p.get('anonymous').emit('change');
  await p.type('A second statement'); await p.get('stop').emit('click');
  assert.deepEqual([p.country.value, p.area.value], ['', '']);
});
