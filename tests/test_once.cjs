// Forms that send an email are sent once per tap (app/static/once.js). A minimal fake page: no browser.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function page() {
  const listeners = {document: {}, window: {}};
  const button = {disabled: false};
  const form = {
    dataset: {}, attributes: {'data-once': ''},
    hasAttribute(name) { return name in this.attributes; },
    querySelectorAll() { return [button]; },
  };
  const other = {dataset: {}, attributes: {}, hasAttribute() { return false; }, querySelectorAll() { return [button]; }};
  const on = where => (name, fn) => { (listeners[where][name] ||= []).push(fn); };
  const document = {addEventListener: on('document'), querySelectorAll: () => [form]};
  const window = {addEventListener: on('window')};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/once.js'), 'utf8'), {document, window});
  const fire = (where, name, event) => { for (const fn of listeners[where][name] || []) fn(event); };
  const submit = (target, submitter) => {
    const event = {target, submitter, prevented: false, preventDefault() { this.prevented = true; }};
    fire('document', 'submit', event);
    return event;
  };
  return {button, form, other, submit, pageshow: persisted => fire('window', 'pageshow', {persisted})};
}

test('the pressed button is disabled after the first submit and a second submit is ignored', () => {
  const {button, form, submit} = page();
  const first = submit(form, button);
  assert.equal(first.prevented, false);
  assert.equal(button.disabled, true);
  const second = submit(form, button);
  assert.equal(second.prevented, true);
});

test('a second submit is ignored even when it comes without a button (Enter in a field)', () => {
  const {button, form, submit} = page();
  submit(form, button);
  assert.equal(submit(form, undefined).prevented, true);
});

test('a form without data-once is left alone', () => {
  const {button, other, submit} = page();
  const event = submit(other, button);
  assert.equal(event.prevented, false);
  assert.equal(button.disabled, false);
});

test('a pageshow, including one restored from the back and forward cache, enables the button again', () => {
  const {button, form, submit, pageshow} = page();
  submit(form, button);
  pageshow(true);
  assert.equal(button.disabled, false);
  assert.equal(submit(form, button).prevented, false);
});
