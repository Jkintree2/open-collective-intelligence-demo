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
  assert.equal(p.get('card-title').textContent, 'Edit your post');
  assert.equal(p.get('post').textContent, 'Save changes');
  assert.equal(p.get('discard').textContent, 'Cancel');
  assert.equal(p.get('issue-rows').children.at(-1).children[1].value, 'Flooding');
  await p.runTimer(200);
  p.requests.at(-1).resolve({sentences: ['Anonymous claims Flooding'], valid: true, dropped: [], corrected: []});
  await p.flush();
  // Not awaited: the click's handler waits on the save request, which the test answers below.
  p.get('post').emit('click'); await p.flush();
  const save = p.requests.at(-1);
  assert.equal(save.url, '/api/posts/post-1');
  save.resolve({id: 'post-1', message: 'Your post is updated.'}); await p.flush();
  assert.equal(p.location.href, '/?done=edited');
});

test('a page without a post to edit is left alone', async () => {
  const p = await setup();
  p.load('edit_post.js'); await p.flush();
  assert.equal(p.get('card').hidden, true);
  assert.equal(p.get('read').hidden, false);
  assert.equal(p.get('post').textContent || '', '');
});
