// The write form: the statement box, the reading, and the buttons. The card is in card.js and
// speech input in dictation.js; both load before this file.
(() => {
  const find = id => document.getElementById(id);
  const form = find('compose'), text = find('text'), dictate = find('dictate');
  if (!form) return;
  const unavailable = 'The reading service is not answering right now. You can fill in the form by hand, or try again in a minute.';
  const tooLong = 'That is longer than this demo can read at once. Please shorten it to a few paragraphs.';
  let readController, slowTimer, abandonTimer;
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
  const card = window.ociCard({find, request, unavailable, stopDictation: () => dictation.stop(), stopReading, updateText});
  const {state} = card;
  const dictation = window.ociDictation({find, tooLong, updateText, busy: () => state.reading || state.posting,
    heard: () => { state.metadata = {source: 'manual'}; updateText(); card.changed(); }});
  function stopReading() {
    readController?.abort(); readController = null;
    clearTimeout(slowTimer); clearTimeout(abandonTimer);
    state.reading = false; text.readOnly = false;
    find('read').textContent = 'Read my statement'; find('stop').hidden = true;
    updateText();
  }
  async function read() {
    dictation.stop();
    if (!text.value.trim() || [...text.value].length > 4000 || state.posting) return;
    stopReading(); find('card').hidden = true; state.reading = true; text.readOnly = true;
    dictate.disabled = true;
    find('read').textContent = 'Reading…'; find('read').disabled = true; find('stop').hidden = false;
    find('retry').hidden = true;
    const controller = new AbortController(); readController = controller;
    slowTimer = setTimeout(() => { find('compose-message').textContent = 'Still reading. This can take up to half a minute.'; }, 8000);
    abandonTimer = setTimeout(() => card.openCard({}, unavailable), 25000);
    const issue = new URLSearchParams(location.search).get('issue');
    try {
      const result = await request('/api/extract', {text: text.value, ...card.identity(), issue}, controller.signal);
      if (readController !== controller) return;
      if (result.payload.language_ok === false) {
        stopReading(); find('compose-message').textContent = result.message; return;
      }
      card.openCard(result.payload, result.message, {source: result.source, extraction_raw: result.extraction_raw,
        model: result.model, latency_ms: result.latency_ms});
      if (result.shortened) card.noteShortened();
    } catch (error) {
      if (readController !== controller) return;
      card.openCard({}, error.name === 'TypeError' || error.offline ? unavailable : error.message);
    }
  }
  function updateText() {
    const size = [...text.value].length;
    dictate.disabled = state.reading || state.posting || (!dictation.listening && size >= 4000);
    find('read').disabled = !text.value.trim() || size > 4000 || state.reading || state.posting;
    find('skip').disabled = size > 4000 || state.posting;
    find('counter').hidden = size < 3500; find('counter').textContent = `${size} / 4000`;
    card.grow(text);
  }
  form.addEventListener('submit', event => { event.preventDefault(); read(); });
  text.addEventListener('input', () => { state.metadata = {...state.metadata, source: 'manual'}; updateText(); card.changed(); });
  text.addEventListener('paste', event => {
    const paste = event.clipboardData.getData('text');
    const next = text.value.slice(0, text.selectionStart) + paste + text.value.slice(text.selectionEnd);
    if ([...next].length > 4000) { event.preventDefault(); find('compose-message').textContent = tooLong; }
  });
  find('anonymous').addEventListener('change', card.changed);
  find('display_name')?.addEventListener('input', card.changed);
  find('skip').hidden = false; find('skip-help').hidden = false; find('skip').addEventListener('click', () => { card.openCard(); if (!state.candidatesReady) card.loadCandidates(); });
  find('stop').addEventListener('click', () => card.openCard());
  find('retry').addEventListener('click', read);
  find('add-issue').addEventListener('click', () => card.addRow('issues'));
  find('add-solution').addEventListener('click', () => card.addRow('solutions'));
  find('add-evidence').addEventListener('click', () => card.addRow('evidence'));
  find('plain').addEventListener('click', card.openPlain);
  find('discard').addEventListener('click', () => { dictation.stop(); stopReading(); find('card').hidden = true; card.changed(); text.focus(); });
  find('post').addEventListener('click', card.post);
  // The summary above the form (about_issue.js) chooses positions through this.
  window.oci = {setPositionOnExisting: card.setPositionOnExisting, card};
  find('read').textContent = 'Read my statement'; updateText(); card.loadCandidates();
})();
