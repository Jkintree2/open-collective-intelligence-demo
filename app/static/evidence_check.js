// Phase 2: the page behind each evidence link on the card is read, and the row says what it found
// (04_interface.md, "Phase 2"; the copy is a draft for John). Loads before card.js, which calls it only
// when the write form carries data-evidence-check. Post never waits for a reading.
window.ociEvidenceCheck = ({request, node, text, changed, addRow, removeRow}) => {
  const SAYS = {
    supports: quote => `The page seems to support this: "${quote}"`,
    refutes: quote => `The page seems to argue against this: "${quote}"`,
    unclear: () => 'The page does not clearly say either way.',
    unread: () => 'Could not open this page.',
    unsupported: () => 'This kind of link cannot be read yet.'
  };
  const DIFFERENT = 'You chose differently from the reading. That is fine; others will see both.';
  const KINDS = [['issues', 'Issue'], ['solutions', 'Solution'], ['evidence', 'Evidence']];
  // Verdicts a post may carry; the server keeps one only when it made that reading itself.
  const KEPT = ['supports', 'refutes', 'unclear', 'unread'];

  function say(row, message) {
    row.check = null; row.verdict = null;
    row.checkBox.replaceChildren(...(message ? [node('p', message, 'check-result')] : []));
  }
  function different(row) {
    if (!row.differentLine) return;
    const reading = row.verdict === 'supports' || row.verdict === 'refutes' ? row.verdict : null;
    row.differentLine.textContent = reading && row.stance.value !== reading ? DIFFERENT : '';
  }
  function suggestions(row, suggested) {
    const items = KINDS.flatMap(([group, label]) => (suggested[group] || []).map(item => ({group, label, name: item.name})));
    if (!items.length) return;
    const box = node('fieldset', '', 'check-also');
    box.append(node('legend', 'The page also mentions'));
    for (const item of items) {
      const label = node('label', '', 'check'), input = node('input');
      input.type = 'checkbox';
      label.append(input, document.createTextNode(`${item.label}: ${item.name}`));
      input.addEventListener('change', () => {
        if (input.checked) {
          input.row = addRow(item.group, item.group === 'evidence' ? {name: item.name, about: row.about.value} : {name: item.name});
          if (!input.row) input.checked = false;  // the card is full
        } else if (input.row) { removeRow(item.group, input.row); input.row = null; }
      });
      box.append(label);
    }
    row.checkBox.append(box);
  }
  function show(row, result) {
    if (!SAYS[result.verdict]) { say(row, ''); return; }
    row.verdict = result.verdict;
    row.check = KEPT.includes(result.verdict) ? {verdict: result.verdict, quote: result.quote || null} : null;
    const lines = [node('p', SAYS[result.verdict](result.quote), 'check-result')];
    if (result.line) lines.push(node('p', result.line, 'check-source'));
    row.differentLine = node('p', '', 'check-different');
    row.checkBox.replaceChildren(...lines, row.differentLine);
    // The reading sets supports or refutes only until the writer chooses; then the choice is theirs.
    if (!row.stanceChosen && (result.verdict === 'supports' || result.verdict === 'refutes') && row.stance.value !== result.verdict) {
      row.stance.value = result.verdict;
    }
    different(row);
    suggestions(row, result.suggested || {});
    changed();  // the card now carries the check, and the preview says so
  }
  async function run(row) {
    const url = row.url.value.trim(), about = row.about.value;
    const serial = row.checkSerial = (row.checkSerial || 0) + 1;
    if (!url || !about) { say(row, ''); return; }
    say(row, 'Reading the page…');
    try {
      const result = await request('/api/check-evidence', {url, evidence: row.name.value, about, text: text.value, stance: row.stance.value});
      if (serial === row.checkSerial) show(row, result);
    } catch (error) {
      // Only the busy reader has words of its own; anything else under a link is that the page was not opened.
      if (serial === row.checkSerial) say(row, error.status === 429 ? error.message : SAYS.unread());
    }
  }
  function watch(row, item = {}) {
    row.checkBox = node('div', '', 'evidence-check');
    row.checkBox.setAttribute('aria-live', 'polite');
    row.about.after(row.checkBox);  // under the choice it speaks to, after supports or refutes and about
    row.lastAsked = '';
    const asked = () => `${row.url.value.trim()}\n${row.about.value}`;
    const ask = () => { if (asked() !== row.lastAsked) { row.lastAsked = asked(); run(row); } };
    row.url.addEventListener('change', ask);
    row.about.addEventListener('change', ask);
    row.stance.addEventListener('change', () => { row.stanceChosen = true; different(row); });
    // A link the reading found is read as soon as its row exists, once the row has its "about". A row of a
    // post being edited shows the reading the post holds instead, and its supports or refutes stays the writer's.
    Promise.resolve().then(() => {
      if (!row.url.value.trim()) return;
      if (item.check && SAYS[item.check.verdict]) { row.lastAsked = asked(); row.stanceChosen = true; show(row, item.check); } else ask();
    });
  }
  return {watch};
};
