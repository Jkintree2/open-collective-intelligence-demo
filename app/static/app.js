(() => {
  const find = id => document.getElementById(id);
  const form = find('compose'), text = find('text'), card = find('card');
  if (!form) return;
  const unavailable = 'The reading service is not answering right now. You can fill in the form by hand, or try again in a minute.';
  const tooLong = 'That is longer than this demo can read at once. Please shorten it to a few paragraphs.';
  let candidates = {issues: {}, solutions: {}, evidence: {}}, candidatesReady = false;
  let metadata = {source: 'manual'}, plain = false, reading = false, posting = false;
  let prefillConsumed = false;
  let readController, previewController, slowTimer, abandonTimer, previewTimer, revision = 0, serial = 0;
  const groups = {issues: [], solutions: [], evidence: []};
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const dictate = find('dictate');
  let recognition, listening = false, speechBase = '', speechCount = 0, speechFloor = 0;
  let speechLast = '', speechBoundary = '';
  function stopDictation() {
    listening = false;
    const previous = recognition; recognition = null;
    dictate.textContent = '🎙 Dictate'; dictate.setAttribute('aria-pressed', 'false');
    previous?.abort(); updateText();
  }
  function startDictation() {
    if (!listening || reading || posting) return;
    const current = new Recognition(); recognition = current;
    speechBase = text.value; speechCount = 0; speechFloor = 0; speechLast = ''; speechBoundary = '';
    current.lang = 'en-US'; current.continuous = true; current.interimResults = true;
    current.onresult = event => {
      if (!listening || recognition !== current) return;
      speechCount = event.results.length;
      speechLast = event.results[speechCount - 1]?.[0].transcript || '';
      const parts = Array.from(event.results).slice(speechFloor).map(result => result[0].transcript);
      // Keep typed edits, but retain new words extending the interim result they followed.
      const boundary = event.results[speechFloor - 1]?.[0].transcript;
      const base = speechBase + (speechFloor && boundary?.startsWith(speechBoundary) ? boundary.slice(speechBoundary.length) : '');
      const spoken = parts.join(' ').trim();
      const next = base + (spoken && base && !/\s$/.test(base) ? ' ' : '') + spoken;
      text.value = [...next].slice(0, 4000).join('');
      metadata = {source: 'manual'}; updateText(); changed();
      if ([...next].length >= 4000) {
        stopDictation();
        if ([...next].length > 4000) find('compose-message').textContent = tooLong;
      }
    };
    current.onend = () => { if (recognition === current && listening) startDictation(); };
    current.onerror = () => { if (recognition === current) stopDictation(); };
    try { current.start(); } catch { stopDictation(); }
  }
  dictate.hidden = !Recognition;
  dictate.addEventListener('click', () => {
    if (listening) { stopDictation(); return; }
    if (!Recognition || reading || posting || [...text.value].length >= 4000) return;
    listening = true; dictate.textContent = 'Listening… press to stop';
    dictate.setAttribute('aria-pressed', 'true'); startDictation();
  });
  window.addEventListener('pagehide', stopDictation);
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
    const anonymous = find('anonymous').checked || !key(find('display_name').value);
    return {anonymous, display_name: anonymous ? '' : find('display_name').value};
  }
  async function request(url, body, signal) {
    const response = await fetch(url, {method: body ? 'POST' : 'GET', signal,
      headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
    let data = null;
    try { data = await response.json(); } catch (parseError) { data = null; }
    if (response.ok && data) return data;
    // A reply that is not ours, such as a gateway page while the site restarts, reads as offline.
    const failure = new Error(data ? (data.message || 'Please check the form and try again.') : unavailable);
    failure.offline = !data;
    if (response.status === 401 && data && data.redirect) location.href = data.redirect;
    throw failure;
  }
  function options(select, values, emptyLabel) {
    const previous = select.value;
    select.replaceChildren(new Option(emptyLabel, ''));
    [...new Set(values.filter(Boolean))].forEach(value => select.add(new Option(value, value)));
    if (values.includes(previous)) select.value = previous;
  }
  function field(row, name, labelText, type = 'input') {
    const label = node('label', labelText);
    const control = node(type === 'input' && name === 'name' ? 'textarea' : type);
    control.id = `card-${++serial}`;
    label.htmlFor = control.id;
    if (type === 'input' && name === 'name') {
      control.className = 'name';
      control.rows = 1; control.maxLength = 300;
      control.addEventListener('input', () => { control.value = control.value.replace(/[\r\n]+/g, ' '); control.style.height = 'auto'; control.style.height = `${control.scrollHeight}px`; });
    } else if (type === 'input') { control.type = 'text'; control.maxLength = name === 'url' ? 2000 : 120; }
    row.element.append(label, control);
    row[name] = control;
    return control;
  }
  function suggest(row, group) {
    const box = row.suggest || (row.suggest = node('div', '', 'suggest'));
    if (!box.parentNode) row.name.after(box);
    const typed = key(row.name.value);
    const pool = group === 'issues' ? Object.values(candidates.issues).map(item => item.name) : Object.values(candidates[group]);
    const hits = typed ? pool.filter(name => key(name).includes(typed) && key(name) !== typed).slice(0, 8) : [];
    box.replaceChildren(...hits.map(name => { const b = node('button', name, 'quiet suggestion'); b.type = 'button';
      b.addEventListener('click', () => { row.name.value = name; box.replaceChildren(); changed(); }); return b; }));
  }
  function collect() {
    const payload = {...identity(), ...metadata, text: text.value, plain};
    for (const [group, rows] of Object.entries(groups)) {
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
    const names = Object.values(candidates.issues).map(item => item.name);
    const issues = groups.issues.map(row => row.name.value.trim()).filter(Boolean);
    const solutions = groups.solutions.map(row => row.name.value.trim()).filter(Boolean);
    const top = Object.values(candidates.issues).filter(item => !item.parent_key).map(item => item.name);
    for (const [group, rows] of Object.entries(groups)) {
      for (const row of rows) {
        const known = candidates[group][key(row.name.value)];
        row.badge.textContent = row.name.value.trim() ? known ? 'existing' : 'new' : '';
        if (row.parent) {
          options(row.parent, top.filter(name => key(name) !== key(row.name.value)), 'none, this is a new top level issue');
          if (known?.parent_key) row.parent.value = candidates.issues[known.parent_key]?.name || '';
          row.parent.disabled = Boolean(known?.parent_key);
        }
        if (row.for_issue) {
          options(row.for_issue, [...issues, ...names], 'Choose an issue');
          if (!row.for_issue.value && issues.length) row.for_issue.value = issues[0];
        }
        if (row.about) {
          options(row.about, [...issues, ...solutions, ...names, ...Object.values(candidates.solutions), ...Object.values(candidates.evidence)], 'Choose what this is about');
          if (!row.about.value && issues.length) row.about.value = issues[0];
        }
      }
      find(`add-${group === 'issues' ? 'issue' : group === 'solutions' ? 'solution' : 'evidence'}`).disabled = rows.length >= (group === 'issues' ? 3 : 5);
    }
  }
  function changed() {
    revision++;
    clearTimeout(previewTimer);
    previewController?.abort();
    find('post').disabled = true;
    refresh();
    const poster = identity();
    find('credit').textContent = poster.anonymous ? 'Posting adds this to the shared record, listed as Anonymous.' : `Posting adds this to the shared record, credited to ${poster.display_name}.`;
    const payload = collect();
    const incomplete = payload.solutions.some(item => !item.for_issue) || payload.evidence.some(item => !item.about);
    if (card.hidden || !candidatesReady || !text.value.trim() || [...text.value].length > 4000 || incomplete || posting) return;
    const expected = revision;
    previewTimer = setTimeout(async () => {
      previewController = new AbortController();
      try {
        const result = await request('/api/preview', payload, previewController.signal);
        if (expected !== revision || card.hidden) return;
        find('sentences').replaceChildren(...result.sentences.map(sentence => node('li', sentence)));
        find('card-errors').textContent = result.dropped.length ? 'Please check the names and choices in the form.' : '';
        find('post').disabled = !result.valid;
      } catch (error) {
        if (expected === revision && error.name !== 'AbortError') find('card-errors').textContent = error.message;
      }
    }, 200);
  }
  function addRow(group, item = {}) {
    if (groups[group].length >= (group === 'issues' ? 3 : 5)) return;
    const row = {element: node('div', '', 'card-row')};
    const label = group === 'issues' ? 'Issue' : group === 'solutions' ? 'Solution' : 'Evidence';
    field(row, 'name', label).value = item.name || '';
    row.badge = node('span', '', 'badge'); row.element.append(row.badge);
    if (group === 'issues') field(row, 'parent', 'Part of', 'select');
    if (group === 'solutions') {
      field(row, 'for_issue', 'for issue', 'select');
      const choices = node('fieldset'), legend = node('legend', 'Your position'); choices.append(legend);
      const radioName = `stance-${++serial}`;
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
    const remove = node('button', 'remove', 'quiet'); remove.type = 'button';
    remove.addEventListener('click', () => { groups[group] = groups[group].filter(other => other !== row); row.element.remove(); changed(); });
    row.element.append(remove);
    row.element.addEventListener('input', () => { suggest(row, group); changed(); });
    row.element.addEventListener('change', changed);
    groups[group].push(row);
    find(group === 'issues' ? 'issue-rows' : group === 'solutions' ? 'solution-rows' : 'evidence-rows').append(row.element);
    refresh();
    for (const name of ['parent', 'for_issue', 'about']) if (row[name] && item[name]) row[name].value = item[name];
    changed();
  }
  function stopReading() {
    readController?.abort(); readController = null;
    clearTimeout(slowTimer); clearTimeout(abandonTimer);
    reading = false; text.readOnly = false;
    find('read').textContent = 'Read my statement'; find('stop').hidden = true;
    updateText();
  }
  function openCard(payload = {}, message = '', meta = {source: 'manual'}) {
    stopDictation(); stopReading(); metadata = meta; plain = false;
    card.hidden = false;
    find('card-message').textContent = message;
    find('card-note').textContent = payload.note || '';
    find('compose-message').textContent = '';
    find('card-errors').textContent = '';
    find('retry').hidden = message !== unavailable;
    for (const group of Object.keys(groups)) { groups[group].forEach(row => row.element.remove()); groups[group] = []; }
    const prefill = candidates.issues[new URLSearchParams(location.search).get('issue')];
    if ((!payload.issues || !payload.issues.length) && prefill) payload.issues = [{name: prefill.name, parent: candidates.issues[prefill.parent_key]?.name}];
    for (const group of Object.keys(groups)) (payload[group] || []).forEach(item => addRow(group, item));
    if (!groups.issues.length) addRow('issues');
    changed();
  }
  function noteShortened() {
    const note = find('card-note');
    note.textContent = [note.textContent, 'A long name was shortened to 300 characters. You can edit it.'].filter(Boolean).join(' ');
  }
  async function read() {
    stopDictation();
    if (!text.value.trim() || [...text.value].length > 4000 || posting) return;
    stopReading(); card.hidden = true; reading = true; text.readOnly = true;
    dictate.disabled = true;
    find('read').textContent = 'Reading…'; find('read').disabled = true; find('stop').hidden = false;
    find('retry').hidden = true;
    const controller = new AbortController(); readController = controller;
    slowTimer = setTimeout(() => { find('compose-message').textContent = 'Still reading. This can take up to half a minute.'; }, 8000);
    abandonTimer = setTimeout(() => openCard({}, unavailable), 25000);
    try {
      const result = await request('/api/extract', {text: text.value, ...identity()}, controller.signal);
      if (readController !== controller) return;
      if (result.payload.language_ok === false) {
        stopReading(); find('compose-message').textContent = result.message; return;
      }
      openCard(result.payload, result.message, {source: result.source, extraction_raw: result.extraction_raw,
        model: result.model, latency_ms: result.latency_ms});
      if (result.shortened) noteShortened();
    } catch (error) {
      if (readController !== controller) return;
      openCard({}, error.name === 'TypeError' || error.offline ? unavailable : error.message);
    }
  }
  function updateText() {
    const size = [...text.value].length;
    dictate.disabled = reading || posting || (!listening && size >= 4000);
    find('read').disabled = !text.value.trim() || size > 4000 || reading || posting;
    find('skip').disabled = !text.value.trim() || size > 4000 || posting;
    find('counter').hidden = size < 3500; find('counter').textContent = `${size} / 4000`;
    text.style.height = 'auto'; text.style.height = `${text.scrollHeight}px`;
  }
  async function loadCandidates() {
    try {
      candidates = await request('/api/candidates'); candidatesReady = true;
      for (const group of Object.keys(groups)) {
        let list = find(`names-${group}`);
        if (!list) { list = node('datalist'); list.id = `names-${group}`; form.append(list); }
        const names = group === 'issues' ? Object.values(candidates.issues).map(item => item.name) : Object.values(candidates[group]);
        list.replaceChildren(...names.map(name => new Option(name, name)));
      }
      if (new URLSearchParams(location.search).has('issue') && !prefillConsumed && card.hidden && !reading) {
        prefillConsumed = true; openCard();
      }
      changed();
    } catch (error) { find('compose-message').textContent = error.message; }
  }
  form.addEventListener('submit', event => { event.preventDefault(); read(); });
  text.addEventListener('input', () => {
    // Typed edits become the new baseline; do not overwrite them with revised interim speech.
    speechBase = text.value; speechFloor = speechCount; speechBoundary = speechLast;
    metadata = {source: 'manual'}; updateText(); changed(); });
  text.addEventListener('paste', event => {
    const paste = event.clipboardData.getData('text');
    const next = text.value.slice(0, text.selectionStart) + paste + text.value.slice(text.selectionEnd);
    if ([...next].length > 4000) { event.preventDefault(); find('compose-message').textContent = tooLong; }
  });
  find('anonymous').addEventListener('change', changed);
  find('display_name').addEventListener('input', changed);
  find('skip').hidden = false; find('skip').addEventListener('click', () => { openCard(); if (!candidatesReady) loadCandidates(); });
  find('stop').addEventListener('click', () => openCard());
  find('retry').addEventListener('click', read);
  find('add-issue').addEventListener('click', () => addRow('issues'));
  find('add-solution').addEventListener('click', () => addRow('solutions'));
  find('add-evidence').addEventListener('click', () => addRow('evidence'));
  find('plain').addEventListener('click', () => { openCard(); groups.issues.forEach(row => { row.name.value = ''; }); plain = true; changed(); });
  find('discard').addEventListener('click', () => { stopDictation(); stopReading(); card.hidden = true; changed(); text.focus(); });
  find('post').addEventListener('click', async () => {
    if (find('post').disabled || posting) return;
    stopDictation();
    const payload = collect(); posting = true; find('post').disabled = true;
    const controls = [...form.querySelectorAll('input, textarea, select, button')];
    const disabled = controls.map(control => control.disabled); controls.forEach(control => { control.disabled = true; });
    try {
      await request('/api/posts', payload);
      card.hidden = true; text.value = ''; metadata = {source: 'manual'};
      find('compose-message').textContent = 'Added to the record';
      setTimeout(() => { if (find('compose-message').textContent === 'Added to the record') find('compose-message').textContent = ''; }, 6000);
      try {
        const response = await fetch('/feed');
        if (!response.ok || response.redirected) throw new Error();
        find('feed').innerHTML = await response.text();
      } catch { find('compose-message').textContent = 'Added to the record. Reload the page to see the updated record.'; }
      loadCandidates();
    } catch (error) { find('card-errors').textContent = error.message; }
    finally { controls.forEach((control, index) => { control.disabled = disabled[index]; }); posting = false; updateText(); changed(); }
  });
  find('read').textContent = 'Read my statement'; updateText(); loadCandidates();
})();
