// Speech into the statement box, where the browser can recognise it. The page says when it is busy
// (reading or posting), what follows a change to the box, and how to bring its buttons up to date.
window.ociDictation = ({find, tooLong, busy, heard, updateText}) => {
  const text = find('text'), dictate = find('dictate');
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition, listening = false, speechBase = '', speechCount = 0, speechFloor = 0;
  let speechLast = '', speechBoundary = '';
  function stopDictation() {
    listening = false;
    const previous = recognition; recognition = null;
    dictate.textContent = '🎙 Dictate'; dictate.setAttribute('aria-pressed', 'false');
    previous?.abort(); updateText();
  }
  function startDictation() {
    if (!listening || busy()) return;
    const current = new Recognition(); recognition = current;
    speechBase = text.value; speechCount = 0; speechFloor = 0; speechLast = ''; speechBoundary = '';
    current.lang = 'en-US'; current.continuous = true; current.interimResults = true;
    current.onresult = event => {
      if (!listening || recognition !== current) return;
      speechCount = event.results.length;
      speechLast = event.results[speechCount - 1]?.[0].transcript || '';
      // A phone repeats the utterance so far in every result, often changing only case or punctuation
      // (lower case while interim, capitalised when final); collapse each growing run to its longest.
      const plainWords = t => t.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
      const merge = (kept, t) => { const last = kept.at(-1), a = plainWords(t), b = last === undefined ? '' : plainWords(last);
        return last !== undefined && (a.startsWith(b) || b.startsWith(a)) ? [...kept.slice(0, -1), a.length >= b.length ? t : last] : [...kept, t]; };
      // Keep typed edits, but retain new words extending the interim result they followed.
      const boundary = event.results[speechFloor - 1]?.[0].transcript;
      const base = speechBase + (speechFloor && boundary?.startsWith(speechBoundary) ? boundary.slice(speechBoundary.length) : '');
      const spoken = Array.from(event.results).slice(speechFloor).map(r => r[0].transcript.trim()).reduce(merge, []).join(' ').trim();
      const next = base + (spoken && base && !/\s$/.test(base) ? ' ' : '') + spoken;
      text.value = [...next].slice(0, 4000).join('');
      heard();
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
    if (!Recognition || busy() || [...text.value].length >= 4000) return;
    listening = true; dictate.textContent = 'Listening… press to stop';
    dictate.setAttribute('aria-pressed', 'true'); startDictation();
  });
  // Typed edits become the new baseline; do not overwrite them with revised interim speech.
  text.addEventListener('input', () => { speechBase = text.value; speechFloor = speechCount; speechBoundary = speechLast; });
  window.addEventListener('pagehide', stopDictation);
  return {stop: stopDictation, get listening() { return listening; }};
};
