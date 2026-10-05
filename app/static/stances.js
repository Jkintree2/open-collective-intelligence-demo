// One-click approve and oppose on the issue page (sub-plan C). Without this file the buttons are
// plain forms; with it the counts and the buttons change in place, one change at a time.
(() => {
  const lines = {APPROVE: 'You approve this. Press Approve again to withdraw.',
    OPPOSE: 'You oppose this. Press Oppose again to withdraw.'};
  const notSaved = 'Your position was not saved. Please try again.';
  function show(form, result) {
    const section = form.closest('.solution');
    section.querySelector('[data-approves]').textContent = result.approves;
    section.querySelector('[data-opposes]').textContent = result.opposes;
    const [approve, oppose] = form.querySelectorAll('button');
    approve.value = result.my_stance === 'APPROVE' ? 'withdraw' : 'approve';
    oppose.value = result.my_stance === 'OPPOSE' ? 'withdraw' : 'oppose';
    approve.setAttribute('aria-pressed', String(result.my_stance === 'APPROVE'));
    oppose.setAttribute('aria-pressed', String(result.my_stance === 'OPPOSE'));
    form.querySelector('[data-stance-line]').textContent = lines[result.my_stance] || '';
  }
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches || !form.matches('form.stance')) return;
    // A browser that does not say which button was pressed (older iOS Safari) posts the plain form.
    const button = event.submitter;
    if (!button) return;
    event.preventDefault();
    if (form.hasAttribute('aria-busy')) return;  // a second tap while one is saving is ignored
    form.setAttribute('aria-busy', 'true');
    const body = new URLSearchParams(new FormData(form));
    body.set('choice', button.value);
    try {
      const response = await fetch(form.action, {method: 'POST', body, headers: {Accept: 'application/json'}});
      const type = response.headers.get('content-type') || '';
      const data = type.includes('json') ? await response.json() : null;
      if (response.status === 401 && data && data.redirect) { location.href = data.redirect + '?next=' + encodeURIComponent(location.pathname + location.search); return; }
      if (!response.ok || !data || data.approves === undefined) throw new Error('not saved');
      show(form, data);
    } catch {
      form.querySelector('[data-stance-line]').textContent = notSaved;
    } finally {
      form.removeAttribute('aria-busy');
    }
  });
})();
