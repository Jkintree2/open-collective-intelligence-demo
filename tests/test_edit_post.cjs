// Editing one's own post on the write page: the card opens from the post, the reading buttons are
// hidden, and Save changes sends it back under the same id, then goes home where the page says it is updated.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {setup} = require('./page_harness.js');

const POST = {id: 'post-1', text: 'Flooding matters', anonymous: true,
  card: {issues: [{name: 'Flooding', parent: null}], solutions: [], evidence: []}};

test('the edit page opens the card from the post and saves under its id', async () => {
  const p = await setup(undefined, {issues: {flooding: {name: 'Flooding', parent_key: null}}, solutions: {}, evidence: {}},
                        {member: 'Ada Lovelace'});
  p.get('edit-post').textContent = JSON.stringify(POST);
  p.load('edit_post.js'); await p.flush();
  assert.equal(p.get('text').value, 'Flooding matters');
  assert.equal(p.get('anonymous').checked, true);
  assert.equal(p.get('anonymous').disabled, true);
  assert.equal(p.get('card').hidden, false);
  // "Read my statement" would clear the intro line, and "Skip the reading" would empty the card.
  assert.equal(p.get('read').hidden, true);
  assert.equal(p.get('skip').hidden, true);
  assert.equal(p.get('skip-help').hidden, true);
  // "post it as a plain statement anyway" would drop every claim the post makes: the card is the edit.
  assert.equal(p.get('plain').hidden, true);
  assert.equal(p.get('card-title').textContent, 'Edit your post');
  assert.equal(p.get('post').textContent, 'Save changes');
  assert.equal(p.get('discard').textContent, 'Cancel');
  assert.equal(p.get('issue-rows').children.at(-1).children[1].value, 'Flooding');
  // Enter in a card field submits the form; while editing that must not start a reading. The fake page
  // does not model capture or stopping, so the edit page's own listener (added last) is called alone.
  let stopped = false, prevented = false;
  p.get('compose').listeners.submit.at(-1)({preventDefault() { prevented = true; }, stopImmediatePropagation() { stopped = true; }});
  assert.equal(stopped && prevented, true);
  await p.runTimer(200);
  // The preview resolves as the save does, keeping the post's own claim and proposal.
  assert.equal(p.requests.at(-1).url, '/api/posts/post-1/preview');
  p.requests.at(-1).resolve({sentences: ['Anonymous claims Flooding'], valid: true, dropped: [], corrected: []});
  await p.flush();
  // Not awaited: the click's handler waits on the save request, which the test answers below.
  p.get('post').emit('click'); await p.flush();
  const save = p.requests.at(-1);
  assert.equal(save.url, '/api/posts/post-1');
  save.resolve({id: 'post-1', message: 'Your post is updated.'}); await p.flush();
  assert.equal(p.location.href, '/?done=edited');
});

test('a post with an empty card saves as a plain statement, and a full card stays structured', async () => {
  const p = await setup(undefined, {issues: {}, solutions: {}, evidence: {}}, {member: 'Ada Lovelace'});
  p.get('edit-post').textContent = JSON.stringify({id: 'post-2', text: 'Just some words', anonymous: false,
    card: {issues: [], solutions: [], evidence: []}});
  p.load('edit_post.js'); await p.flush();
  await p.runTimer(200);
  const preview = p.requests.at(-1);
  assert.equal(preview.url, '/api/posts/post-2/preview');
  assert.equal(JSON.parse(preview.options.body).plain, true);
  preview.resolve({sentences: [], valid: true, dropped: [], corrected: []}); await p.flush();
  assert.equal(p.get('post').disabled, false);
  p.get('post').emit('click'); await p.flush();
  const save = p.requests.at(-1);
  assert.equal(save.url, '/api/posts/post-2');
  assert.equal(JSON.parse(save.options.body).plain, true);
  // A post with a card is not made plain: emptying its card does not quietly drop what it made.
  const q = await setup(undefined, {issues: {flooding: {name: 'Flooding', parent_key: null}}, solutions: {}, evidence: {}},
                        {member: 'Ada Lovelace'});
  q.get('edit-post').textContent = JSON.stringify(POST);
  q.load('edit_post.js'); await q.flush(); await q.runTimer(200);
  assert.equal(JSON.parse(q.requests.at(-1).options.body).plain, false);
});

test('a page without a post to edit is left alone', async () => {
  const p = await setup();
  p.load('edit_post.js'); await p.flush();
  assert.equal(p.get('card').hidden, true);
  assert.equal(p.get('read').hidden, false);
  assert.equal(p.get('post').textContent || '', '');
  // On a normal write page the plain statement button stays visible once the card is open, and the
  // preview goes to the usual place.
  await p.type('Flooding matters'); await p.get('skip').emit('click');
  assert.equal(p.get('card').hidden, false);
  assert.equal(p.get('plain').hidden, false);
  await p.runTimer(200);
  assert.equal(p.requests.at(-1).url, '/api/preview');
});

test('a failed save keeps its message on screen and the button usable', async () => {
  const p = await setup(undefined, {issues: {flooding: {name: 'Flooding', parent_key: null}}, solutions: {}, evidence: {}},
                        {member: 'Ada Lovelace'});
  p.get('edit-post').textContent = JSON.stringify(POST);
  p.load('edit_post.js'); await p.flush(); await p.runTimer(200);
  p.requests.at(-1).resolve({sentences: ['Anonymous claims Flooding'], valid: true, dropped: [], corrected: []}); await p.flush();
  p.get('post').emit('click'); await p.flush();
  const save = p.requests.at(-1);
  assert.equal(save.url, '/api/posts/post-1');
  save.fail(429, {detail: 'Please wait a little before posting again.'}); await p.flush();
  const message = p.get('card-errors').textContent;
  assert.notEqual(message, '');
  const before = p.requests.length;
  await p.runTimer(200);
  assert.equal(p.requests.length, before);
  assert.equal(p.get('card-errors').textContent, message);
  assert.equal(p.get('post').disabled, false);
  // The writer can tap again after waiting.
  p.get('post').emit('click'); await p.flush();
  assert.equal(p.requests.at(-1).url, '/api/posts/post-1');
  assert.equal(p.requests.length, before + 1);
});
