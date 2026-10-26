// Phase 3: follow-up questions under the card's new rows (04_interface.md, "Follow-up questions on the card").
// Loads before card.js, only with FOLLOW_UPS_ENABLED, and registers on the card hook. Questions are asked once,
// when the card opens; an answer is added to the statement as one line, and the card is not read again.
// Post never waits for a question, and nothing shows while they are being thought of.
(window.ociCardExtras ||= []).push(({find, request, node, text, changed, state}) => {
  const INTRO = 'A question that would make this clearer:';
  const ADD = 'Add to my statement';
  const SKIP = 'Skip';
  const PUBLIC = 'Your answer is added to your statement, so everyone who reads the post sees it.';
  const TOO_LONG = 'That is longer than this demo can read at once. Please shorten it to a few paragraphs.';
  const LONGEST = 4000;
  // Which rows are new is known only once the record's names have arrived (/api/candidates); a card that opens
  // before them waits, checking every quarter second for at most a minute, then asks once.
  const WAIT_MS = 250, WAIT_TRIES = 240;
  const ROW = {issues: 'issue', solutions: 'solution', evidence: 'evidence'};
  let asking = 0, serial = 0;
  // The same key as card.js, so a question finds its row by name as the record would.
  const key = value => {
    let result = (value || '').normalize('NFKC').toLowerCase().trim().replace(/^(the|a|an)( |$)/u, '');
    result = result.replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    return result.length >= 2 ? result : '';
  };
  const rows = () => Object.entries(state.groups).flatMap(([group, list]) => list.map(row => ({kind: ROW[group], row})));

  // One line at the end of the statement: the question, then the answer. The writer's own words, so the page
  // treats it as typing in the box (the preview follows, dictation carries on after it); nothing is read again.
  function addLine(line) {
    const before = text.value.replace(/\s+$/u, '');
    const next = before ? `${before}\n${line}` : line;
    if ([...next].length > LONGEST) return false;
    text.value = next;
    if (typeof text.dispatchEvent === 'function' && typeof Event === 'function') text.dispatchEvent(new Event('input', {bubbles: true}));
    else changed();
    return true;
  }
  function show(row, question) {
    const box = node('div', '', 'follow-up');
    const input = node('input');
    input.type = 'text'; input.maxLength = 300; input.id = `follow-up-${++serial}`;
    const label = node('label', question.text, 'follow-up-question'); label.htmlFor = input.id;
    const add = node('button', ADD); add.type = 'button';
    const skip = node('button', SKIP, 'quiet'); skip.type = 'button';
    const actions = node('div', '', 'follow-up-actions'); actions.append(add, skip);
    const note = node('p', PUBLIC, 'follow-up-note');
    box.append(node('p', INTRO, 'follow-up-intro'), label, input, actions, note);
    const close = () => { box.remove(); row.followUp = null; };
    const answer = () => {
      const words = input.value.replace(/\s+/gu, ' ').trim();
      if (!words) { input.focus(); return; }
      if (addLine(`${question.text} ${words}`)) close(); else note.textContent = TOO_LONG;
    };
    // Typing an answer is not a change to the row: the card would release a position chosen in the panel.
    for (const name of ['input', 'change']) input.addEventListener(name, event => event.stopPropagation?.());
    // Enter in the box adds the answer instead of sending the form.
    input.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); answer(); } });
    add.addEventListener('click', answer);
    skip.addEventListener('click', close);
    if (question.fixed) {
      // The missing source question goes once the row has a link or the own experience tick.
      const settled = () => { if (row.followUp === box && (row.url?.value.trim() || row.personal?.checked)) close(); };
      row.url?.addEventListener('input', settled);
      row.personal?.addEventListener('change', settled);
    }
    row.followUp = box;
    row.element.append(box);
  }
  function opened() {
    const mine = ++asking;
    for (const {row} of rows()) { row.followUp?.remove(); row.followUp = null; }
    let tries = 0;
    const whenKnown = () => {
      if (mine !== asking || find('card').hidden) return;  // the card opened again, or closed
      if (state.candidatesReady) ask(mine);
      else if (++tries <= WAIT_TRIES) setTimeout(whenKnown, WAIT_MS);
    };
    whenKnown();
  }
  async function ask(mine) {
    const fresh = rows().filter(({row}) => row.badge.textContent === 'new' && row.name.value.trim());
    if (!fresh.length) return;
    const body = {text: text.value, rows: fresh.map(({kind, row}) => ({row: kind, name: row.name.value.trim(), existing: false,
      url: row.url?.value.trim() || null, personal: Boolean(row.personal?.checked)}))};
    let result;
    try { result = await request('/api/follow-ups', body); } catch { return; }  // no questions; nothing to say
    if (mine !== asking) return;  // the card opened again since
    for (const question of result?.questions || []) {
      const match = rows().find(({kind, row}) => kind === question.row && !row.followUp
        && row.badge.textContent === 'new' && key(row.name.value) === key(question.name));
      if (match) show(match.row, question);
    }
  }
  return {opened};
});
