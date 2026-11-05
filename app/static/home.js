// v0.3 Home, with HOME_ENABLED and ASK_ENABLED: one box for Write and Ask (04_interface.md, "v0.3: Write and Ask
// on one Home page"). On Read my statement or question the site says what the text is (/api/home/kind): a
// statement starts the reading and the card (app.js, window.ociStartReading), a question is answered in place under
// the button (ask.js, window.ociAsk), and when the site can't tell, two buttons let the writer choose. A link under
// the box sends the same text the other way. Without this file the form posts to /home, which does the same.
(() => {
  const find = id => document.getElementById(id);
  const form = find('compose'), text = find('text');
  if (!form || !form.dataset || !('homeAsk' in form.dataset)) return;
  const box = find('home-ask'), unsure = find('home-unsure'), swap = find('home-switch');
  const switchTo = {question: 'Post it as a statement instead', statement: 'Ask it as a question instead'};
  const KEPT = 'oci.myQuestions', SHOWN = 5;
  let way = null, last = '', sorting = false;

  // "My most recent statements and questions": the page drew the writer's statements; the questions answered on
  // this device (ask.js keeps them) join them by time, newest first, five shown.
  function kept() {
    try {
      const items = JSON.parse(localStorage.getItem(KEPT) || '[]');
      return Array.isArray(items) ? items.filter(item => item && typeof item.text === 'string' && item.at) : [];
    } catch {
      return [];  // storage blocked: the statements stay as drawn
    }
  }

  function questionItem(question) {
    const item = document.createElement('li');
    item.setAttribute('data-at', question.at);
    item.setAttribute('data-kind', 'question');
    // One with no kept answer is a button that puts it back in the box, as on Ask the database.
    const inner = document.createElement(question.id ? 'a' : 'button');
    if (question.id) {
      inner.className = 'ask-answered';
      inner.href = '/ask/answers/' + encodeURIComponent(question.id);
    } else {
      inner.className = 'home-again';
      inner.type = 'button';
    }
    inner.textContent = question.text;
    item.append(inner);
    return item;
  }

  function drawMine() {
    const list = find('home-mine'), section = find('home-mine-section');
    if (!list || !section) return;
    const statements = [...list.children].filter(item => item.dataset && item.dataset.kind === 'statement');
    const entries = [...statements.map(node => ({at: node.dataset.at, node})),
      ...kept().map(question => ({at: question.at, node: questionItem(question)}))];
    entries.sort((a, b) => (Date.parse(b.at) || 0) - (Date.parse(a.at) || 0));
    const items = entries.slice(0, SHOWN).map(entry => entry.node);
    list.replaceChildren(...items);
    section.hidden = items.length === 0;
  }

  function went(kind) {  // the way the text went, and the link that sends it the other way
    way = kind;
    unsure.hidden = true;
    swap.textContent = switchTo[kind];
    swap.hidden = false;
  }

  function asStatement() {
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
    const data = await window.ociAsk(box, question);
    if (data && data.status && text.value.trim() === question) text.value = '';  // ready for "Tell me more"
    if (data && data.status === 'answered') drawMine();
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
  drawMine();
  if ('start' in form.dataset && text.value.trim()) send(null);  // brought here by the box on another page
})();
