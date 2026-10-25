// Phone deck: live state rendering, mute targets, LIVE confirmation flow.
const assert = require('node:assert/strict');
const { load, respond, wait } = require('./dom');

const state = {
  version: '3.0.0', admin: false, device: 'Test', control: true,
  studio: { connected: true, message: null, scene: 'Gaming', scenes: ['Gaming', 'BRB'], mic_muted: false, audio_muted: true, stream_status: 1, live: true, live_since: Date.now() / 1000 - 3725 },
  buttons: [
    { id: 'gaming', label: 'Main gaming', icon: '02', color: '#4dd9b1', action: { kind: 'scene', scene: 'Gaming' }, confirm: false },
    { id: 'brb', label: 'BRB', icon: '03', color: '#d3acff', action: { kind: 'scene', scene: 'BRB' }, confirm: false },
    { id: 'microphone', label: 'Microphone', icon: '♫', color: '#f4b66c', action: { kind: 'mic' }, confirm: false },
    { id: 'desktop-audio', label: 'Desktop sound', icon: '♪', color: '#7dd4e8', action: { kind: 'audio' }, confirm: false },
    { id: 'gamingon', label: 'Back live', icon: '02', color: '#4dd9b1', confirm: false,
      action: { kind: 'macro', steps: [{ kind: 'scene', scene: 'Gaming' }, { kind: 'wait', ms: 200 }, { kind: 'mic', muted: false }] } },
    { id: 'brbmute', label: 'BRB + mute', icon: '03', color: '#d3acff', confirm: false,
      action: { kind: 'macro', steps: [{ kind: 'scene', scene: 'BRB' }, { kind: 'mic', muted: true }] } }
  ]
};
const presses = [];
let brbAttempts = 0;
const fetch = async (url, opts = {}) => {
  if (url === '/api/events') return respond(200, {});
  if (url === '/api/state') return respond(200, state);
  if (url === '/api/press') {
    const body = JSON.parse(opts.body);
    presses.push(body);
    if (body.id === 'brb' && !brbAttempts++) return respond(409, { error: 'You are LIVE', code: 'confirm_live' });
    return respond(200, { ok: true, code: 'done', message: 'Done' });
  }
  return respond(404, {});
};

(async () => {
  const dom = load('index.html', {
    url: 'http://192.168.1.2:8765/', fetch,
    before: w => { w.localStorage.setItem('lanternDevice', 'device-token'); w.localStorage.setItem('lanternLang', 'en'); }
  });
  const d = dom.window.document;
  await wait(50);
  assert.equal(d.getElementById('pair').hidden, true);
  const keys = () => [...d.querySelectorAll('.key')];
  assert.equal(keys().length, 6);
  assert.ok(keys()[4].classList.contains('active'), 'multi-step button lit when its targets are reached');
  assert.ok(!keys()[5].classList.contains('active'));
  assert.match(d.getElementById('livePill').textContent, /LIVE · 1:02:0[56]/);
  assert.ok(keys()[0].classList.contains('active'), 'current scene lit');
  assert.ok(!keys()[1].classList.contains('active'));
  assert.ok(keys()[2].classList.contains('on'), 'mic on');
  assert.ok(keys()[3].classList.contains('muted'), 'desktop sound muted');
  assert.equal(d.getElementById('livePill').hidden, false);
  assert.match(d.getElementById('controlPill').textContent, /Live control ON/);

  keys()[5].click(); await wait(120);
  assert.deepEqual(presses.at(-1), { id: 'brbmute', confirmed: false }, 'multi-step buttons send no target');
  keys()[2].click(); await wait(50);
  assert.deepEqual(presses.at(-1), { id: 'microphone', confirmed: false, target: true });
  keys()[3].click(); await wait(50);
  assert.equal(presses.at(-1).target, false, 'unmute target comes from the displayed state');

  d.getElementById('confirmDialog').autoAnswer = 'ok';
  keys()[1].click(); await wait(120);
  assert.deepEqual(presses.slice(-2).map(p => p.confirmed), [false, true], 'LIVE confirmation resends as confirmed');
  assert.match(d.getElementById('lastAction').textContent, /Done: BRB/);

  d.getElementById('lang').click(); await wait(10);
  assert.match(d.getElementById('controlPill').textContent, /ACTIF/);
  dom.window.close();
  console.log('phone: live state, mute targets, LIVE confirmation and French passed');
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
