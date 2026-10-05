// Signed in, the card credits the account's name and never sends a typed one (members.posting_identity).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

test('a signed-in card is credited to the account', async () => {
  const {get, type, requests, runTimer} = await setup(undefined, undefined, {member: 'Ada Tester'});
  await type('Flooding'); await get('skip').emit('click');
  assert.equal(get('credit').textContent, 'Posting adds this to the shared record, credited to Ada Tester.');
  await runTimer(200);
  const body = JSON.parse(requests.at(-1).options.body);
  assert.equal(body.display_name, 'Ada Tester');
  assert.equal(body.anonymous, false);
});

test('a signed-in anonymous card is listed as Anonymous', async () => {
  const {get, type} = await setup(undefined, undefined, {member: 'Ada Tester'});
  get('anonymous').checked = true;
  await type('Flooding'); await get('skip').emit('click');
  assert.equal(get('credit').textContent, 'Posting adds this to the shared record, listed as Anonymous.');
});
