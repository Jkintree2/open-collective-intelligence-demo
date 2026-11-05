// Phase 3: ask the record, on /ask and in the box on each issue page (04_interface.md, "Ask the
// record"). Without this file the box is a plain form that posts to /ask. With it the answer shows in
// place, under the box, newest first, and the visit's last three questions on this page go with the
// next one (never the answers). The server keeps an answered question with its answer for the list under
// the box (never who asked), and the list links to it. Every piece of text is set as text, never as markup.
(() => {
  const lines = {
    noQuestion: 'Please write a question.',
    tooLong: 'Please keep the question under 500 characters.',
    waiting: 'Reading the database…',
    still: 'Still reading. A long issue can take up to a minute.',
    failed: 'The question could not be answered just now. Please try again in a minute.',
  };
  const QUESTION_MAX = 500, EARLIER = 3, STILL_AFTER = 10000, WAIT_FOR = 50000;
  const KEPT = 'oci.myQuestions', KEEP = 20;  // v0.3: answered questions kept on this device for Home's list
  const earlier = new WeakMap();  // each box's own questions

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // 04_interface.md: a post is "{name}, {date}: “{first 200 characters}” On {issue}"; a solution or a piece
  // of evidence is "Solution: {name}. On {issue}" or "Evidence: {name}. On {issue}", its name a link to its own
  // page (GitHub issue 55).
  const KINDS = {solution: 'Solution: ', evidence: 'Evidence: '};
  function sourceLine(source) {
    const item = el('li');
    // A guiding document (John, 28 October): "Guiding document: {name}.", the name linked to the About page.
    if (source.kind === 'document') {
      item.append(document.createTextNode('Guiding document: '));
      if (source.href) {
        const link = el('a', '', source.name);
        link.href = source.href;
        item.append(link);
      } else item.append(document.createTextNode(source.name));
      item.append(document.createTextNode('.'));
      return item;
    }
    if (source.kind !== 'post' && source.page) {
      item.append(document.createTextNode(KINDS[source.kind] || ''));
      const link = el('a', '', source.name);
      link.href = source.page;
      item.append(link, document.createTextNode('.'));
    } else {
      const words = source.kind === 'post'
        ? source.name + (source.when ? ', ' + source.when : '') + (source.text ? ': \u201c' + source.text + '\u201d' : '')
        : (KINDS[source.kind] || '') + source.name + '.';
      item.append(document.createTextNode(words));
    }
    if (source.issue && source.href) {
      item.append(document.createTextNode(' On '));
      const link = el('a', '', source.issue);
      link.href = source.href;
      item.append(link);
    }
    return item;
  }

  // One answer block: the question, the paragraphs with their source numbers, the partial line, the sources.
  function answerBlock(question, data) {
    const block = el('div', 'ask-answer');
    block.append(el('p', 'ask-question', question));
    if (data.message) block.append(el('p', 'ask-message', data.message));
    for (const paragraph of data.paragraphs || []) {
      const p = el('p', 'ask-paragraph', paragraph.text);
      if (paragraph.refs && paragraph.refs.length) p.append(el('span', 'ask-refs', ' ' + paragraph.refs.map(n => '[' + n + ']').join(' ')));
      block.append(p);
    }
    if (data.partial) block.append(el('p', 'ask-partial', data.partial));
    if (data.sources && data.sources.length) {
      block.append(el('h3', 'ask-sources-title', 'Sources'));
      const list = el('ol', 'ask-sources');
      for (const source of data.sources) list.append(sourceLine(source));
      block.append(list);
    }
    return block;
  }

  // GitHub issue 55: the box on a solution's or a piece of evidence's page says which.
  function on(box) {
    if (box.dataset.solution) return {solution: box.dataset.solution};
    return box.dataset.evidence ? {evidence: box.dataset.evidence} : {};
  }

  // One question in one box, the answer shown in it; the box's form (none on Home) is busy meanwhile. Resolves to
  // the answer's data, or null when nothing came back to show.
  async function ask(box, text, form) {
    const busy = form || box;
    const status = box.querySelector('[data-ask-status]');
    const answers = box.querySelector('[data-ask-answers]');
    const question = text.split(/\s+/).filter(Boolean).join(' ');
    if (!question) { status.textContent = lines.noQuestion; return null; }
    if (question.length > QUESTION_MAX) { status.textContent = lines.tooLong; return null; }
    // Questions asked before this page was drawn (the answer page without JavaScript) start the list.
    const asked = earlier.get(box) || (form ? [...form.querySelectorAll('[name=earlier]')].map(input => input.value) : []);
    busy.setAttribute('aria-busy', 'true');
    status.textContent = lines.waiting;
    const still = setTimeout(() => { status.textContent = lines.waiting + ' ' + lines.still; }, STILL_AFTER);
    // The browser waits longer than the server's 40 seconds, so a late reply is the server's to report.
    const controller = new AbortController();
    const giveUp = setTimeout(() => controller.abort(), WAIT_FOR);
    let data = null, response = null;
    try {
      response = await fetch('/api/ask', {method: 'POST', signal: controller.signal,
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify({question, earlier: asked.slice(-EARLIER), issue: box.dataset.issue || null, ...on(box)})});
      data = await response.json();
    } catch {
      data = null;
    } finally {
      clearTimeout(still); clearTimeout(giveUp);
      busy.removeAttribute('aria-busy');
    }
    if (response && response.status === 401 && data && data.redirect) {
      location.href = data.redirect + '?next=' + encodeURIComponent(location.pathname + location.search);
      return null;
    }
    if (!data || typeof data !== 'object' || (!response.ok && !data.message) || response.status >= 500) {
      status.textContent = lines.failed;
      return null;
    }
    if (!response.ok) { status.textContent = data.message; return null; }  // a question too long, a limit
    status.textContent = '';
    if (data.status) {  // the language model was asked: this question goes with the next one
      asked.push(question);
      earlier.set(box, asked.slice(-EARLIER));
    }
    if (data.status === 'answered') { listed(box, question, data.question_id); keep(question, data.question_id); }
    answers.prepend(answerBlock(question, data));
    return data;
  }

  async function submit(event) {
    const form = event.target;
    if (!form.matches || !form.matches('form.ask-form')) return;
    event.preventDefault();
    if (form.hasAttribute('aria-busy')) return;
    const field = form.querySelector('[name=question]');
    const data = await ask(form.closest('[data-ask]'), field.value, form);
    if (data && data.status) field.value = '';
  }

  // v0.3 Home: its one box asks through here (window.ociAsk), with Home's answer area as the box, which keeps its
  // own earlier questions.
  globalThis.ociAsk = (box, text) => (box.hasAttribute('aria-busy') ? Promise.resolve(null) : ask(box, text, null));

  // John, 28 October: an answered question is kept and listed for everyone; show it at the top here too.
  // John, 30 October: it links to the answer it got; one the server could not keep is a button, as before.
  function listed(box, question, id) {
    const recent = box.querySelector('[data-ask-recent]');
    if (!recent) return;
    const list = recent.querySelector('ul');
    const same = text => text.toLowerCase().replace(/[?.!\s]+$/, '');
    for (const item of [...list.children]) {
      if (same(item.children[0].textContent) === same(question)) item.remove();
    }
    const item = el('li');
    if (id) {
      const link = el('a', 'ask-answered', question);
      link.href = '/ask/answers/' + encodeURIComponent(id);
      item.append(link);
    } else {
      const again = el('button', 'ask-again', question);
      again.type = 'button';
      item.append(again);
    }
    list.prepend(item);
    recent.hidden = false;
  }

  // v0.3: Home lists "My most recent statements and questions". The database never keeps who asked, so the
  // questions are kept here, on this device, under the member the page names: newest first, at most 20, the same
  // question once. Storage that is
  // blocked or full leaves the question out of the list, and nothing else changes.
  function keep(question, id) {
    // The page names the member (<body data-mine>) only when Home is on for them; otherwise nothing is kept.
    const owner = document.body && document.body.dataset ? document.body.dataset.mine : '';
    if (!owner) return;
    const same = text => String(text).toLowerCase().replace(/[?.!\s]+$/, '');
    try {
      const old = JSON.parse(localStorage.getItem(KEPT + '.' + owner) || '[]');
      const items = (Array.isArray(old) ? old : []).filter(item => item && same(item.text) !== same(question));
      items.unshift({id: id || null, text: question, at: new Date().toISOString()});
      localStorage.setItem(KEPT + '.' + owner, JSON.stringify(items.slice(0, KEEP)));
    } catch {
      // the list leaves it out
    }
  }

  // A tap on a listed question puts it in the box, ready to ask or change.
  document.addEventListener('click', event => {
    const again = event.target.closest && event.target.closest('.ask-again');
    if (!again) return;
    const field = again.closest('[data-ask]').querySelector('form.ask-form textarea');
    field.value = again.textContent;
    field.focus();
  });

  document.addEventListener('submit', submit);
  // Enter asks; Shift and Enter starts a new line.
  document.addEventListener('keydown', event => {
    const field = event.target;
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing || !field.matches
        || !field.matches('form.ask-form textarea')) return;
    event.preventDefault();
    field.form.requestSubmit();
  });
})();
