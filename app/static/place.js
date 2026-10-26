// Phase 3: the card's Place row (04_interface.md, "A place on the card"). Loads before card.js, only with
// PLACES_ENABLED, and registers on the card hook. The place is the writer's choice, never read from the
// statement: a country (or "Not about one place") and a town or area, sent with the post as {country, area}.
(window.ociCardExtras ||= []).push(({find, request, node, state, changed}) => {
  const AREA = 'Town or area, optional';
  const ANONYMOUS = 'A town can tell others who wrote an anonymous statement. Add one only if you are happy with that.';
  const NEEDS_COUNTRY = 'Please choose the country for this town or area.';
  const row = node('div', '', 'place-row');
  const country = node('select'), area = node('input');
  country.id = 'place-country'; area.id = 'place-area'; area.type = 'text'; area.maxLength = 80;
  const countryLabel = node('label', 'Place'), areaLabel = node('label', AREA);
  countryLabel.htmlFor = country.id; areaLabel.htmlFor = area.id;
  const note = node('p', ANONYMOUS, 'place-note'), problem = node('p', '', 'place-problem');
  problem.setAttribute('role', 'status');
  row.append(countryLabel, country, areaLabel, area, note, problem);
  row.hidden = true;
  find('add-evidence').after(row);

  const anonymous = () => Boolean(find('anonymous')?.checked);
  // The post being edited starts at its own place (Q24); a new one at the account's country when named,
  // and empty when anonymous (a town can name someone in a small group). The writer's own choice stays.
  let account = '', chosen = null;
  function editing() {
    try { return JSON.parse(find('edit-post')?.textContent || 'null')?.place || null; } catch { return null; }
  }
  const start = () => { if (!chosen) { country.value = anonymous() ? '' : account; area.value = ''; } };
  function show() {
    note.hidden = !anonymous();
    problem.textContent = area.value.trim() && !country.value ? NEEDS_COUNTRY : '';
  }
  for (const name of ['input', 'change']) {
    for (const control of [country, area]) control.addEventListener(name, () => { chosen = {}; show(); changed(); });
  }
  find('anonymous')?.addEventListener('change', () => { start(); show(); });

  (async () => {
    try {
      const places = await request('/api/place');
      country.replaceChildren(new Option(places.not_one_place, ''), ...places.choices.map(([code, name]) => new Option(name, code)));
      account = places.country || ''; chosen ||= editing();
      if (chosen) { country.value = chosen.country || ''; area.value = chosen.area || ''; } else start();
      // Sent only once the row is there; without it an edit keeps the post's place and a new post has none.
      state.place = () => ({country: country.value || null, area: area.value.trim() || null});
      row.hidden = false; show(); changed();
    } catch { /* no Place row: the card works as before */ }
  })();
  // A new statement starts at the account's country, or empty when anonymous, whatever the last one chose.
  return {opened() { start(); show(); }, posted() { chosen = null; start(); show(); }};
});
