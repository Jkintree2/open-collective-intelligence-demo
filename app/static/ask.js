// Phase 3: ask the record, on /ask and in the box on each issue page (04_interface.md, "Ask the
// record"). Without this file the box is a plain form that posts to /ask. With it the answer shows in
// place, under the box, newest first, and the visit's last three questions on this page go with the
// next one (never the answers). Nothing is kept after the page is left. Every piece of text is set
// as text, never as markup.
(() => {
  const lines = {
    noQuestion: 'Please write a question.',
    tooLong: 'Please keep the question under 500 characters.',
    waiting: 'Reading the database… The first question after a quiet spell can take a minute.',
    still: 'Still reading. A long issue can take up to a minute.',
    failed: 'The question could not be answered just now. Please try again in a minute.',
  };
  const QUESTION_MAX = 500, EARLIER = 3, STILL_AFTER = 10000, WAIT_FOR = 50000;
  const earlier = new WeakMap();  // each box's own questions

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // 04_interface.md: a post is "{name}, {date}: “{first 200 characters}” On {issue}"; a solution or a piece
  // of evidence is "Solution: {name}. On {issue}" or "Evidence: {name}. On {issue}".
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
    const words = source.kind === 'post'
      ? source.name + (source.when ? ', ' + source.when : '') + (source.text ? ': \u201c' + source.text + '\u201d' : '')
      : (KINDS[source.kind] || '') + source.name + '.';
    item.append(document.createTextNode(words));
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

  async function submit(event) {
    const form = event.target;
    if (!form.matches || !form.matches('form.ask-form')) return;
    event.preventDefault();
    if (form.hasAttribute('aria-busy')) return;
    const box = form.closest('[data-ask]');
    const status = box.querySelector('[data-ask-status]');
    const answers = box.querySelector('[data-ask-answers]');
    const field = form.querySelector('[name=question]');
    const question = field.value.split(/\s+/).filter(Boolean).join(' ');
    if (!question) { status.textContent = lines.noQuestion; return; }
    if (question.length > QUESTION_MAX) { status.textContent = lines.tooLong; return; }
    // Questions asked before this page was drawn (the answer page without JavaScript) start the list.
    const asked = earlier.get(box) || [...form.querySelectorAll('[name=earlier]')].map(input => input.value);
    form.setAttribute('aria-busy', 'true');
    status.textContent = lines.waiting;
    const still = setTimeout(() => { status.textContent = lines.waiting + ' ' + lines.still; }, STILL_AFTER);
    // The browser waits longer than the server's 40 seconds, so a late reply is the server's to report.
    const controller = new AbortController();
    const giveUp = setTimeout(() => controller.abort(), WAIT_FOR);
    let data = null, response = null;
    try {
      response = await fetch('/api/ask', {method: 'POST', signal: controller.signal,
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify({question, earlier: asked.slice(-EARLIER), issue: box.dataset.issue || null})});
      data = await response.json();
    } catch {
      data = null;
    } finally {
      clearTimeout(still); clearTimeout(giveUp);
      form.removeAttribute('aria-busy');
    }
    if (response && response.status === 401 && data && data.redirect) {
      location.href = data.redirect + '?next=' + encodeURIComponent(location.pathname + location.search);
      return;
    }
    if (!data || typeof data !== 'object' || (!response.ok && !data.message) || response.status >= 500) {
      status.textContent = lines.failed;
      return;
    }
    if (!response.ok) { status.textContent = data.message; return; }  // a question too long, a limit
    status.textContent = '';
    if (data.status) {  // the reading service was asked: this question goes with the next one
      asked.push(question);
      earlier.set(box, asked.slice(-EARLIER));
      field.value = '';
    }
    answers.prepend(answerBlock(question, data));
  }

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
