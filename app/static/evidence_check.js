// Phase 2: the page behind each evidence link on the card is read, and the row says what it found
// (04_interface.md, "Phase 2" and its revision round). Loads before card.js, which calls it only when the
// write form carries data-evidence-check; data-no-reading there means no reading service, so links are
// not read but a row with no link still says so. Post never waits for a reading.
window.ociEvidenceCheck = ({request, node, text, changed, addRow, removeRow, reading = true}) => {
  // John's words for the readings that rest on a sentence from the page (21 October 2026).
  const SAYS = {
    supports: 'Agrees',
    partly: 'Partly agrees',
    refutes: 'Contradicts',
    unclear: 'The page does not clearly say either way.',
    unread: 'Could not open this page.',
    unsupported: 'This kind of link cannot be read yet.'
  };
  // Which side of supports or refutes a reading takes; partly agrees counts as supports.
  const SIDE = {supports: 'supports', partly: 'supports', refutes: 'refutes'};
  const NO_SOURCE = 'No source given.';
  const PERSONAL = 'From personal experience.';
  const PERSONAL_TICK = 'From my own experience';
  const SLOW = 'Still reading. A slow page can take up to a minute.';
  const SLOW_AFTER_MS = 10000;
  const DIFFERENT = 'You chose differently from the reading. That is fine; others will see both.';
  const ALSO_HINT = 'Tick any you want to add to your statement; you can edit it before you post. Evidence you tick keeps this page\'s link.';
  const KINDS = [['issues', 'Issue'], ['solutions', 'Solution'], ['evidence', 'Evidence']];
  // Verdicts a post may carry; the server keeps one only when it made that reading itself.
  const KEPT = ['supports', 'partly', 'refutes', 'unclear', 'unread'];

  function say(row, message) {
    row.check = null; row.verdict = null; row.differentLine = null; row.noLinkShown = false;
    row.checkBox.replaceChildren(...(message ? [node('p', message, 'check-result')] : []));
  }
  // A row with no link says so; the writer may tick that it is from their own experience. Nothing is read.
  function noLink(row) {
    row.checkSerial = (row.checkSerial || 0) + 1;  // a reading still under way is for a link no longer there
    say(row, '');
    row.noSource.textContent = row.personal.checked ? PERSONAL : NO_SOURCE;
    row.checkBox.replaceChildren(row.noSource, row.personalLabel);
    row.noLinkShown = true;
  }
  function different(row) {
    if (!row.differentLine) return;
    const side = SIDE[row.verdict];
    row.differentLine.textContent = side && row.stance.value !== side ? DIFFERENT : '';
  }
  function suggestions(row, suggested) {
    const items = KINDS.flatMap(([group, label]) => (suggested[group] || []).map(item => ({group, label, name: item.name})));
    if (!items.length) return;
    const box = node('fieldset', '', 'check-also');
    box.append(node('legend', 'The page also mentions'), node('p', ALSO_HINT, 'check-hint'));
    for (const item of items) {
      const label = node('label', '', 'check'), input = node('input');
      input.type = 'checkbox';
      label.append(input, document.createTextNode(`${item.label}: ${item.name}`));
      input.addEventListener('change', () => {
        if (input.checked) {
          // Evidence found on the page keeps the page's link, so it stays tied to where it was found (John, 20 October).
          input.row = addRow(item.group, item.group === 'evidence'
            ? {name: item.name, about: row.about.value, url: row.url.value.trim(), fromPage: true} : {name: item.name});
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
    const lines = [node('p', SAYS[result.verdict], SIDE[result.verdict] ? 'check-result check-verdict' : 'check-result')];
    // Agrees, partly agrees or contradicts: the writer's sentence and the page's, one under the other.
    if (SIDE[result.verdict]) {
      if (result.claim) lines.push(node('p', `You wrote: "${result.claim}"`, 'check-claim'));
      if (result.quote) lines.push(node('p', `The page says: "${result.quote}"`, 'check-quote'));
    }
    // Partly agrees and unclear say why, for example what the writer's words claim that the page does not.
    if ((result.verdict === 'partly' || result.verdict === 'unclear') && result.reason) lines.push(node('p', result.reason, 'check-reason'));
    if (result.line) lines.push(node('p', result.line, 'check-source'));
    row.differentLine = node('p', '', 'check-different');
    row.checkBox.replaceChildren(...lines, row.differentLine);
    // The reading sets supports or refutes only until the writer chooses; then the choice is theirs.
    const side = SIDE[result.verdict];
    if (!row.stanceChosen && side && row.stance.value !== side) row.stance.value = side;
    different(row);
    if (!row.fromPage) suggestions(row, result.suggested || {});  // a row ticked from a page does not list that page again
    changed();  // the card now carries the check, and the preview says so
  }
  async function run(row) {
    const url = row.url.value.trim(), about = row.about.value;
    if (!url) { noLink(row); return; }
    const serial = row.checkSerial = (row.checkSerial || 0) + 1;
    if (!about || !reading) { say(row, ''); return; }
    say(row, 'Reading the page…');
    const slow = setTimeout(() => {
      if (serial === row.checkSerial && !row.verdict) row.checkBox.append(node('p', SLOW, 'check-slow'));
    }, SLOW_AFTER_MS);
    try {
      const result = await request('/api/check-evidence', {url, evidence: row.name.value, about, text: text.value, stance: row.stance.value});
      if (serial === row.checkSerial) show(row, result);
    } catch (error) {
      // Only the busy reader has words of its own; anything else under a link is that the page was not opened.
      if (serial === row.checkSerial) say(row, error.status === 429 ? error.message : SAYS.unread);
    } finally {
      clearTimeout(slow);
    }
  }
  function watch(row, item = {}) {
    row.checkBox = node('div', '', 'evidence-check');
    row.fromPage = Boolean(item.fromPage);
    row.checkBox.setAttribute('aria-live', 'polite');
    row.about.after(row.checkBox);  // under the choice it speaks to, after supports or refutes and about
    row.noSource = node('p', '', 'check-result check-no-source');
    row.personalLabel = node('label', '', 'check check-personal');
    row.personal = node('input');
    row.personal.type = 'checkbox';
    row.personal.checked = Boolean(item.personal);
    row.personalLabel.append(row.personal, document.createTextNode(PERSONAL_TICK));
    row.personal.addEventListener('change', () => { row.noSource.textContent = row.personal.checked ? PERSONAL : NO_SOURCE; changed(); });
    row.lastAsked = '';
    const asked = () => `${row.url.value.trim()}\n${row.about.value}`;
    const ask = () => { if (asked() !== row.lastAsked) { row.lastAsked = asked(); run(row); } };
    row.url.addEventListener('change', ask);
    // The tick is only for a row with no link: typing one clears it, removing the link brings it back.
    row.url.addEventListener('input', () => {
      if (!row.url.value.trim()) { row.lastAsked = asked(); noLink(row); }
      else if (row.noLinkShown) { row.personal.checked = false; say(row, ''); }
    });
    row.about.addEventListener('change', ask);
    row.stance.addEventListener('change', () => { row.stanceChosen = true; different(row); });
    // A link the reading found is read as soon as its row exists, once the row has its "about". A row of a
    // post being edited shows the reading the post holds instead, and its supports or refutes stays the writer's.
    Promise.resolve().then(() => {
      if (!row.url.value.trim()) { noLink(row); return; }
      if (item.check && SAYS[item.check.verdict]) { row.lastAsked = asked(); row.stanceChosen = true; show(row, item.check); } else ask();
    });
  }
  return {watch};
};
