// Editing one's own post (sub-plan D). The write page opens with the statement and the card filled
// from the post; Save changes sends it back under the same post id (card.js), then goes home.
(() => {
  const find = id => document.getElementById(id);
  const data = find('edit-post');
  const card = window.oci && window.oci.card;
  if (!data || !data.textContent || !card) return;
  const post = JSON.parse(data.textContent);
  const intro = 'Saving replaces what this post added. It keeps the name or Anonymous it was first posted with. '
    + 'Removing a position here does not withdraw it; use the buttons on the issue page.';
  card.state.editing = post.id;
  find('text').value = post.text;
  find('anonymous').checked = post.anonymous;
  find('anonymous').disabled = true;
  // A reading would clear the intro line, skipping it would empty the card, and a plain statement would
  // drop every claim the post makes: the card is the edit.
  for (const id of ['read', 'skip', 'skip-help', 'plain']) find(id).hidden = true;
  // Enter in a card field submits the form, which would start a reading (app.js); while editing it does nothing.
  find('compose').addEventListener('submit', event => { event.preventDefault(); event.stopImmediatePropagation(); }, true);
  function open() {
    card.openCard(post.card, '', {source: 'manual'});
    // A post with nothing on its card (a plain statement, or tidied down to none) saves as one, with the
    // plain statement button hidden. A post with a card stays structured: emptying it is not saved.
    if (!['issues', 'solutions', 'evidence'].some(group => (post.card[group] || []).length)) {
      card.state.plain = true; card.changed();
    }
    find('card-title').textContent = 'Edit your post';
    find('card-note').textContent = intro;
    find('post').textContent = 'Save changes';
    find('discard').textContent = 'Cancel';
  }
  // The card's choices need the record's names; app.js has already asked for them.
  let tries = 0;
  (function wait() { if (card.state.candidatesReady || ++tries > 100) open(); else setTimeout(wait, 50); })();
  find('discard').addEventListener('click', () => { location.href = '/'; });
})();
