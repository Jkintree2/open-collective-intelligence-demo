// The issue page's stance buttons, offline: one change at a time, and the page shows the server's answer.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function page() {
  const node = () => ({textContent: '', value: '', attributes: {}, setAttribute(k, v) { this.attributes[k] = v; }});
  const approves = node(), opposes = node(), line = node();
  const approve = Object.assign(node(), {value: 'approve'}), oppose = Object.assign(node(), {value: 'oppose'});
  const section = {querySelector: s => ({'[data-approves]': approves, '[data-opposes]': opposes})[s]};
  const form = {action: '/solutions/a/stance', dataset: {}, matches: s => s === 'form.stance', closest: () => section,
    querySelectorAll: () => [approve, oppose], querySelector: s => s === '[data-stance-line]' ? line : null};
  let submit; const requests = [];
  const location = {href: '/issues/veto'};
  const context = {
    document: {addEventListener: (name, fn) => { if (name === 'submit') submit = fn; }}, location,
    FormData: class { constructor() { return [['issue', 'veto']]; } }, URLSearchParams,
    fetch: (url, options) => new Promise(resolve => requests.push({url, options, resolve}))};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/stances.js'), 'utf8'), context);
  const press = button => { const event = {target: form, submitter: button, prevented: false,
    preventDefault() { this.prevented = true; }}; submit(event); return event; };
  const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
  return {form, approve, oppose, approves, opposes, line, requests, press, flush, location};
}
const json = (data, status = 200) => ({ok: status < 400, status, headers: {get: () => 'application/json'}, json: async () => data});

test('one change at a time and a failure says so', async () => {
  const p = page();
  p.press(p.approve); p.press(p.approve);
  assert.equal(p.requests.length, 1);
  assert.equal(p.requests[0].options.body.get('choice'), 'approve');
  p.requests[0].resolve(json({approves: 3, opposes: 1, my_stance: 'APPROVE'})); await p.flush();
  assert.equal(p.approves.textContent, 3);
  assert.equal(p.approve.value, 'withdraw'); assert.equal(p.approve.attributes['aria-pressed'], 'true');
  assert.equal(p.oppose.value, 'oppose'); assert.equal(p.line.textContent, 'You approve this. Press Approve again to withdraw.');
  p.press(p.oppose);
  p.requests[1].resolve({ok: false, status: 502, headers: {get: () => 'text/html'}, json: async () => { throw new Error(); }}); await p.flush();
  assert.equal(p.line.textContent, 'Your position was not saved. Please try again.');
  assert.equal(p.approve.value, 'withdraw');  // unchanged after a failure
});

test('a signed out page goes to sign in', async () => {
  const p = page();
  p.press(p.approve);
  p.requests[0].resolve(json({message: 'Please sign in again.', redirect: '/sign-in'}, 401)); await p.flush();
  assert.equal(p.location.href, '/sign-in');
});

test('a browser that does not say which button was pressed submits the plain form', () => {
  // Older iOS Safari has no event.submitter: the form then posts natively, with the pressed button's value.
  const p = page();
  const event = p.press(undefined);
  assert.equal(event.prevented, false);
  assert.equal(p.requests.length, 0);
});
