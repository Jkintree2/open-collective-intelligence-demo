// A form marked data-once is sent once per tap: its button is disabled until the page changes,
// and a second submit meanwhile is ignored. A page shown again from the back button re-enables it.
(function () {
  function buttons(form) {
    return form.querySelectorAll('button[type="submit"], button:not([type])');
  }
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || !form.hasAttribute || !form.hasAttribute('data-once')) return;
    if (form.dataset.sending === 'yes') { event.preventDefault(); return; }
    form.dataset.sending = 'yes';
    var pressed = event.submitter;
    if (pressed) pressed.disabled = true;
    else Array.prototype.forEach.call(buttons(form), function (button) { button.disabled = true; });
  });
  window.addEventListener('pageshow', function () {
    Array.prototype.forEach.call(document.querySelectorAll('form[data-once]'), function (form) {
      form.dataset.sending = '';
      Array.prototype.forEach.call(buttons(form), function (button) { button.disabled = false; });
    });
  });
})();
