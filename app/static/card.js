// The card under the statement: its rows, the preview of what it will add, and Post.
// Everything the card holds is in `state`, so a reading, a choice in the panel and a post see the same card.
window.ociCard = ({find, request, unavailable, stopDictation, stopReading, updateText}) => {
  const form = find('compose'), text = find('text'), card = find('card');
  const state = {
    candidates: {issues: {}, solutions: {}, evidence: {}}, candidatesReady: false, prefillConsumed: false,
    groups: {issues: [], solutions: [], evidence: []},
    metadata: {source: 'manual'}, plain: false, reading: false, posting: false,
    previewController: null, previewTimer: null, revision: 0, serial: 0,
    // The preview a tap on Post waits for, so a blur that re-runs it does not swallow the tap.
    previewPending: null, previewSettle: null
  };
  const key = value => {
    let result = value.normalize('NFKC').toLowerCase().trim().replace(/^(the|a|an)( |$)/u, '');
    result = result.replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    return result.length >= 2 ? result : '';
  };
  function node(tag, content, className) {
    const element = document.createElement(tag);
    if (content) element.textContent = content;
    if (className) element.className = className;
    return element;
  }
  function identity() {
    // Signed in, the name is the account's and the page has no name field (members.posting_identity).
    const member = form.dataset?.member;
    if (member !== undefined) {
      const anonymous = find('anonymous').checked;
      return {anonymous, display_name: anonymous ? '' : member};
    }
    const anonymous = find('anonymous').checked || !key(find('display_name').value);
    return {anonymous, display_name: anonymous ? '' : find('display_name').value};
  }
  function options(select, groups, emptyLabel) {
    const previous = select.value;
    select.replaceChildren(new Option(emptyLabel, ''));
    const seen = new Set();
    for (const [label, values] of groups) {
      const fresh = [...new Set(values.filter(Boolean))].filter(value => !seen.has(value));
      fresh.forEach(value => seen.add(value));
      if (!fresh.length) continue;
      if (!label) { fresh.forEach(value => select.add(new Option(value, value))); continue; }
      const group = document.createElement('optgroup'); group.label = label;
      fresh.forEach(value => group.append(new Option(value, value)));
      select.add(group);
    }
    if (seen.has(previous)) select.value = previous;
  }
  // The issue the writer is writing about, its top level issue and that issue's family.
  function family() {
    const issueKey = new URLSearchParams(location.search).get('issue');
    const about = state.candidates.issues[issueKey];
    if (!about) return {label: '', names: []};
    const topKey = about.parent_key || issueKey;
    const top = state.candidates.issues[topKey];
    const names = [top?.name, ...Object.entries(state.candidates.issues)
      .filter(([, item]) => item.parent_key === topKey).map(([, item]) => item.name)];
    return {label: `About ${top?.name || about.name}`, names: names.filter(Boolean)};
  }
  const grow = box => { box.style.height = 'auto'; box.style.height = `${box.scrollHeight + box.offsetHeight - box.clientHeight}px`; };  // Show all of a filled box.
  function field(row, name, labelText, type = 'input') {
    const label = node('label', labelText);
    const control = node(type === 'input' && name === 'name' ? 'textarea' : type);
    control.id = `card-${++state.serial}`;
    label.htmlFor = control.id;
    if (type === 'input' && name === 'name') {
      control.className = 'name';
      control.rows = 1; control.maxLength = 300;
      control.addEventListener('input', () => { control.value = control.value.replace(/[\r\n]+/g, ' '); grow(control); });
    } else if (type === 'input') { control.type = 'text'; control.maxLength = name === 'url' ? 2000 : 120; }
    row.element.append(label, control);
    row[name] = control;
    return control;
  }
  function suggest(row, group) {
    const box = row.suggest || (row.suggest = node('div', '', 'suggest'));
    if (!box.parentNode) row.name.after(box);
    const typed = key(row.name.value);
    const pool = group === 'issues' ? Object.values(state.candidates.issues).map(item => item.name) : Object.values(state.candidates[group]);
    const hits = typed ? pool.filter(name => key(name).includes(typed) && key(name) !== typed).slice(0, 8) : [];
    box.replaceChildren(...hits.map(name => { const b = node('button', name, 'quiet suggestion'); b.type = 'button';
      b.addEventListener('click', () => { row.name.value = name; box.replaceChildren(); changed(); }); return b; }));
  }
  function collect() {
    const payload = {...identity(), ...state.metadata, text: text.value, plain: state.plain};
    for (const [group, rows] of Object.entries(state.groups)) {
      payload[group] = rows.filter(row => row.name.value.trim()).map(row => {
        const item = {name: row.name.value};
        for (const fieldName of ['parent', 'for_issue', 'url', 'about']) {
          if (row[fieldName]) item[fieldName] = row[fieldName].value || null;
        }
        if (row.stance) item.stance = row.stance.value;
        if (row.radios) item.stance = row.radios.find(radio => radio.checked).value;
        return item;
      });
    }
    return payload;
  }
  function refresh() {
    const {candidates, groups} = state;
    const names = Object.values(candidates.issues).map(item => item.name);
    const issues = groups.issues.map(row => row.name.value.trim()).filter(Boolean);
    const solutions = groups.solutions.map(row => row.name.value.trim()).filter(Boolean);
    const top = Object.values(candidates.issues).filter(item => !item.parent_key).map(item => item.name);
    const fam = family();
    // A row that is itself part of something is not offered as a parent; the record allows one level.
    const cardTop = groups.issues.filter(row => row.name.value.trim() && !row.parent?.value
      && !candidates.issues[key(row.name.value)]?.parent_key).map(row => row.name.value.trim());
    for (const [group, rows] of Object.entries(groups)) {
      for (const row of rows) {
        const known = candidates[group][key(row.name.value)];
        row.badge.textContent = row.name.value.trim() ? known ? 'existing' : 'new' : ''; grow(row.name);
        if (row.parent) {
          const self = key(row.name.value);
          options(row.parent, [['On this form', cardTop.filter(name => key(name) !== self)],
            [fam.label, fam.names.filter(name => key(name) !== self && !candidates.issues[key(name)]?.parent_key)],
            ['All issues', top.filter(name => key(name) !== self)]], known ? 'none, this is already a top level issue' : 'none, this is a new top level issue');
          if (known?.parent_key) row.parent.value = candidates.issues[known.parent_key]?.name || '';
          row.parent.disabled = Boolean(known?.parent_key);
        }
        if (row.for_issue) {
          options(row.for_issue, [['On this form', issues], [fam.label, fam.names], ['All issues', names]], 'Choose an issue');
          if (!row.for_issue.value && issues.length) row.for_issue.value = issues[0];
        }
        if (row.about) {
          options(row.about, [['On this form', [...issues, ...solutions]], [fam.label, fam.names], ['All issues', names],
            ['Solutions', Object.values(candidates.solutions)], ['Evidence', Object.values(candidates.evidence)]], 'Choose what this is about');
          if (!row.about.value && issues.length) row.about.value = issues[0];
        }
      }
      find(`add-${group === 'issues' ? 'issue' : group === 'solutions' ? 'solution' : 'evidence'}`).disabled = rows.length >= (group === 'issues' ? 3 : 5);
    }
    // Posting the text with no structure needs text; an empty box has nothing plain to post.
    find('plain').disabled = !text.value.trim();
  }
  function changed() {
    state.revision++;
    clearTimeout(state.previewTimer);
    state.previewController?.abort();
    // A tap waiting on a superseded preview waits on the next one instead: on a phone the keyboard
    // can commit the last word after the tap, and that late change must not swallow it.
    const waiting = state.previewSettle; state.previewSettle = null; state.previewPending = null;
    refresh();
    const poster = identity();
    find('credit').textContent = poster.anonymous ? 'Posting adds this to the shared record, listed as Anonymous.' : `Posting adds this to the shared record, credited to ${poster.display_name}.`;
    const payload = collect();
    const incomplete = payload.solutions.some(item => !item.for_issue) || payload.evidence.some(item => !item.about);
    const filled = payload.issues.length || payload.solutions.length || payload.evidence.length;
    const noStatement = !text.value.trim();
    // A card filled in by hand is posted on its own: its sentences become the statement.
    if (!card.hidden && noStatement && filled && !state.reading) find('card-message').textContent = 'No statement written. The lines under "What this will add" will be posted as your statement.';
    else if (!card.hidden && find('card-message').textContent.startsWith('No statement written')) find('card-message').textContent = '';
    if (card.hidden || !state.candidatesReady || (noStatement && !filled) || [...text.value].length > 4000 || incomplete || state.posting) {
      waiting?.(false); find('post').disabled = true; return;
    }
    const expected = state.revision;
    // The tap can arrive before the timer fires, so the promise it waits on exists from now on.
    state.previewPending = new Promise(resolve => { state.previewSettle = resolve; });
    const settle = state.previewSettle;
    if (waiting) state.previewPending.then(waiting);
    state.previewTimer = setTimeout(() => {
      state.previewController = new AbortController();
      (async () => {
        try {
          const result = await request('/api/preview', payload, state.previewController.signal);
          if (expected !== state.revision || card.hidden) return false;
          find('sentences').replaceChildren(...result.sentences.map(sentence => node('li', sentence)));
          find('card-errors').textContent = result.dropped.length ? 'Please check the names and choices in the form.' : '';
          find('post').disabled = !result.valid;
          return result.valid;
        } catch (error) {
          if (expected === state.revision && error.name !== 'AbortError') {
            find('card-errors').textContent = error.message; find('post').disabled = true;
          }
          return false;
        }
      })().then(ok => { if (expected === state.revision) settle(ok); });
    }, 200);
  }
  function addRow(group, item = {}) {
    if (state.groups[group].length >= (group === 'issues' ? 3 : 5)) return;
    const row = {element: node('div', '', 'card-row')};
    const label = group === 'issues' ? 'Issue' : group === 'solutions' ? 'Solution' : 'Evidence';
    field(row, 'name', label).value = item.name || '';
    row.badge = node('span', '', 'badge'); row.element.append(row.badge);
    if (group === 'issues') field(row, 'parent', 'Part of', 'select');
    if (group === 'solutions') {
      field(row, 'for_issue', 'for issue', 'select');
      const choices = node('fieldset'), legend = node('legend', 'Your position'); choices.append(legend);
      const radioName = `stance-${++state.serial}`;
      row.radios = ['none', 'approve', 'oppose'].map((value, index) => {
        const label = node('label', '', 'check'), input = node('input');
        input.type = 'radio'; input.name = radioName; input.value = value;
        input.checked = value === (item.stance || 'none');
        label.append(input, document.createTextNode(['no position', 'I approve this', 'I oppose this'][index]));
        choices.append(label); return input;
      });
      row.element.append(choices);
    }
    if (group === 'evidence') {
      field(row, 'url', 'Link (optional)').value = item.url || '';
      field(row, 'stance', 'supports / refutes', 'select');
      ['supports', 'refutes'].forEach(value => row.stance.add(new Option(value, value)));
      row.stance.value = item.stance || 'supports';
      field(row, 'about', 'about', 'select');
    }
    const remove = node('button', 'remove from this form', 'quiet'); remove.type = 'button';
    remove.addEventListener('click', () => { state.groups[group] = state.groups[group].filter(other => other !== row); row.element.remove(); changed(); });
    row.element.append(remove);
    row.element.addEventListener('input', () => { suggest(row, group); changed(); });
    row.element.addEventListener('change', changed);
    state.groups[group].push(row);
    find(group === 'issues' ? 'issue-rows' : group === 'solutions' ? 'solution-rows' : 'evidence-rows').append(row.element);
    refresh();
    for (const name of ['parent', 'for_issue', 'about']) if (row[name] && item[name]) row[name].value = item[name];
    changed();
  }
  function openCard(payload = {}, message = '', meta = {source: 'manual'}) {
    stopDictation(); stopReading(); state.metadata = meta; state.plain = false;
    card.hidden = false;
    find('card-message').textContent = message;
    find('card-note').textContent = payload.note || '';
    find('compose-message').textContent = '';
    find('card-errors').textContent = '';
    find('retry').hidden = message !== unavailable;
    for (const group of Object.keys(state.groups)) { state.groups[group].forEach(row => row.element.remove()); state.groups[group] = []; }
    const prefill = state.candidates.issues[new URLSearchParams(location.search).get('issue')];
    if ((!payload.issues || !payload.issues.length) && prefill) payload.issues = [{name: prefill.name, parent: state.candidates.issues[prefill.parent_key]?.name}];
    for (const group of Object.keys(state.groups)) (payload[group] || []).forEach(item => addRow(group, item));
    if (!state.groups.issues.length) addRow('issues');
    changed();
  }
  // Posting the text with no structure: the card opens with its issue rows emptied.
  function openPlain() {
    openCard(); state.groups.issues.forEach(row => { row.name.value = ''; }); state.plain = true; changed();
  }
  function noteShortened() {
    const note = find('card-note');
    note.textContent = [note.textContent, 'A long name was shortened to 300 characters. You can edit it.'].filter(Boolean).join(' ');
  }
  async function loadCandidates() {
    try {
      state.candidates = await request('/api/candidates'); state.candidatesReady = true;
      if (new URLSearchParams(location.search).has('issue') && !state.prefillConsumed && card.hidden && !state.reading) {
        state.prefillConsumed = true; openCard();
      }
      changed();
    } catch (error) { find('compose-message').textContent = error.message; }
  }
  async function post() {
    if (state.posting) return;
    stopDictation();
    // A tap that arrives while the preview is still running waits for its answer.
    const ok = await (state.previewPending || Promise.resolve(!find('post').disabled));
    if (!ok || find('post').disabled) return;
    const payload = collect(); state.posting = true; find('post').disabled = true;
    const controls = [...form.querySelectorAll('input, textarea, select, button')];
    const disabled = controls.map(control => control.disabled); controls.forEach(control => { control.disabled = true; });
    try {
      await request('/api/posts', payload);
      card.hidden = true; text.value = ''; state.metadata = {source: 'manual'};
      find('compose-message').textContent = 'Added to the record';
      setTimeout(() => { if (find('compose-message').textContent === 'Added to the record') find('compose-message').textContent = ''; }, 6000);
      try {
        const response = await fetch('/feed');
        if (!response.ok || response.redirected) throw new Error();
        find('feed').innerHTML = await response.text();
      } catch { find('compose-message').textContent = 'Added to the record. Reload the page to see the updated record.'; }
      loadCandidates();
    } catch (error) { find('card-errors').textContent = error.message; }
    finally { controls.forEach((control, index) => { control.disabled = disabled[index]; }); state.posting = false; updateText(); changed(); }
  }
  // The summary above the form (about_issue.js) sets a position on a solution the record already holds.
  // The answer lets the panel undo the choice and say why: 'reading', 'full' or true.
  function setPositionOnExisting(name, forIssue, stance) {
    if (state.reading) return 'reading';  // A reading in flight is never abandoned by a choice up there.
    if (card.hidden) openCard();
    const mine = () => state.groups.solutions.find(r => key(r.name.value) === key(name)); let row = mine();
    if (stance === 'none') { if (row) { state.groups.solutions = state.groups.solutions.filter(r => r !== row); row.element.remove(); changed(); } return true; }
    // A full card takes no more rows, and the last row there belongs to someone else.
    if (!row) { addRow('solutions', {name, for_issue: forIssue, stance}); row = mine(); }
    if (!row) return 'full';
    row.radios.forEach(r => { r.checked = r.value === stance; });
    changed(); return true;
  }
  return {state, grow, identity, changed, addRow, openCard, openPlain, noteShortened, loadCandidates, post, setPositionOnExisting};
};
