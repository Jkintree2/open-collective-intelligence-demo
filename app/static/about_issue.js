// The summary above the form (C7): a position choice there opens the card with that solution (C8).
(() => {
  const about = document.getElementById('about-issue');
  if (!about) return;
  about.addEventListener('change', event => {
    const radio = event.target;
    if (radio.type !== 'radio' || !radio.dataset.solution || !window.oci) return;
    window.oci.setPositionOnExisting(radio.dataset.solution, about.dataset.issue, radio.value);
  });
})();
