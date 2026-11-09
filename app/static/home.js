// v0.3 Home, with HOME_ENABLED and ASK_ENABLED: one box for Write and Ask (04_interface.md, "v0.3: Write and Ask
// on one Home page"). On Read my statement or question the site says what the text is (/api/home/kind): a
// statement starts the reading and the card (app.js, window.ociStartReading), a question is answered in place under
// the button (ask.js, window.ociAsk), and when the site can't tell, two buttons let the writer choose. A link under
// the box sends the same text the other way, and after an answer the server draws the feed again (app.js,
// window.oci.refreshLists), as after a post. Without this file the form posts to /home, which does the same.
(() => {
  const find = id => document.getElementById(id);
  const form = find('compose'), text = find('text');
  if (form?.dataset?.homeAsk === undefined) return;
  const box = find('home-ask'), unsure = find('home-unsure'), swap = find('home-switch');
  const switchTo = {question: 'Post it as a statement instead', statement: 'Ask it as a question instead'};
  let way = null, last = '', sorting = false, sent = 0;  // sent: which send is the current one

  function went(kind) {  // the way the text went, and the link that sends it the other way
    way = kind;
    unsure.hidden = true;
    swap.textContent = switchTo[kind];
    swap.hidden = false;
  }

  function asStatement() {
    sent += 1;  // an answer still on its way no longer speaks for the box
    if (!text.value.trim() && last) text.value = last;  // an answered question left the box empty
    box.hidden = true;
    went('statement');
    window.ociStartReading();
  }

  async function asQuestion() {
    const question = text.value.trim() || last;
    if (!question) return;
    last = question;
    find('discard').click();  // stops a reading and puts the card away, as Discard does
    box.hidden = false;
    went('question');
    const ticket = ++sent;
    const data = await window.ociAsk(box, question);
    if (data && data.status === 'answered') window.oci.refreshLists().catch(() => {});  // a reload shows them anyway
    if (ticket !== sent) return;  // sent the other way meanwhile: the reading owns the box now
    if (data && data.status && text.value.trim() === question) text.value = '';  // ready for "Tell me more"
  }

  async function kindOf(value) {
    try {
      const response = await fetch('/api/home/kind', {method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'}, body: JSON.stringify({text: value})});
      const data = await response.json();
      if (response.status === 401 && data && data.redirect) { location.href = data.redirect; return null; }
      return response.ok && data && data.kind ? data.kind : 'statement';
    } catch {
      return 'statement';  // the reading has its own way of saying the site is not answering
    }
  }

  async function send(choice) {
    if (sorting || !text.value.trim()) return;
    let kind = choice;
    if (!kind) {
      sorting = true;
      try { kind = await kindOf(text.value); } finally { sorting = false; }
    }
    if (kind === 'question') return asQuestion();
    if (kind === 'unsure') { unsure.hidden = false; swap.hidden = true; return; }
    if (kind === 'statement') asStatement();
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    const by = event.submitter;
    send(by && by.name === 'kind' ? by.value : null);  // the two buttons say which
  });
  swap.addEventListener('click', () => (way === 'question' ? asStatement() : asQuestion()));
  // A question with no kept answer, in either list, goes back in the box to ask or change.
  document.addEventListener('click', event => {
    const again = event.target.closest && event.target.closest('.home-again');
    if (!again) return;
    text.value = again.textContent;
    text.focus();
  });
  // New words in the box: the link and the two buttons were about the text before.
  text.addEventListener('input', () => { swap.hidden = true; unsure.hidden = true; });
  if ('start' in form.dataset && text.value.trim()) {  // brought here by the box on another page
    history.replaceState(null, '', '/');  // the address was the form's /home; a reload must not send it again
    send(null);
  }
})();
