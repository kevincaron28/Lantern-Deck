// Loads a Lantern page into jsdom with a scripted fetch. Development tool only.
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const web = path.join(__dirname, '..', '..', 'web');

function respond(status, data) {
  return { ok: status < 400, status, body: null, json: async () => data };
}

function load(page, { url, fetch, before }) {
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', e => { if (!/Not implemented/.test(e.message)) console.error(e); });
  const html = fs.readFileSync(path.join(web, page), 'utf8');
  const dom = new JSDOM(html, { url, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole });
  const w = dom.window;
  w.HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
    if (this.autoAnswer) { this.returnValue = this.autoAnswer; setTimeout(() => this.close(), 0); }
  };
  w.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new w.Event('close')); };
  w.HTMLElement.prototype.scrollIntoView = function () {};
  w.confirm = () => true;
  w.fetch = fetch;
  if (!w.AbortSignal.timeout) w.AbortSignal.timeout = () => undefined;
  if (before) before(w);
  for (const m of html.matchAll(/<script src="\/([^"]+)"/g)) w.eval(fs.readFileSync(path.join(web, m[1]), 'utf8'));
  return dom;
}

const wait = ms => new Promise(r => setTimeout(r, ms));
module.exports = { load, respond, wait };
