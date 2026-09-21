// The summary above the form (C7): a position choice there opens the card with that solution (C8).
(() => {
  const about = document.getElementById('about-issue');
  if (!about) return;
  const why = {
    full: 'The form already holds five solutions. Remove one from the form to add this.',
    reading: 'Please wait for the reading to finish, then choose a position.'
  };
  about.addEventListener('change', event => {
    const radio = event.target;
    if (radio.type !== 'radio' || !radio.dataset.solution || !window.oci) return;
    const result = window.oci.setPositionOnExisting(radio.dataset.solution, about.dataset.issue, radio.value);
    if (result === true) return;
    // The choice was not taken, so the panel goes back to no position and says why.
    for (const other of about.querySelectorAll('input[type=radio]')) if (other.name === radio.name) other.checked = other.value === 'none';
    const card = document.getElementById('card');
    const where = card && !card.hidden ? 'card-errors' : 'compose-message';
    document.getElementById(where).textContent = why[result] || '';
  });
})();
