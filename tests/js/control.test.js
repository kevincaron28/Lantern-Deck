// Control center: token handling, checklist, scene auto-match, recorder, save and profiles.
const assert = require('node:assert/strict');
const { load, respond, wait } = require('./dom');

const button = (id, label, action, shortcut = '') => ({ id, label, icon: '01', color: '#80a7ff', action, shortcut, fallback: false, confirm: false });
const state = {
  version: '3.0.0', admin: true, device: null, control: false,
  studio: { connected: true, message: null, scene: 'Gaming', scenes: ['Starting soon', 'Gaming', 'BRB', 'Ending'], mic_muted: false, audio_muted: false, stream_status: 0, live: false },
  buttons: [button('starting', 'Starting', { kind: 'scene', scene: '' }), button('gaming', 'Main gaming', { kind: 'scene', scene: '' }),
    button('brb', 'BRB', { kind: 'scene', scene: '' }), button('ending', 'Ending', { kind: 'scene', scene: '' }),
    button('microphone', 'Microphone', { kind: 'mic' }), button('desktop-audio', 'Desktop sound', { kind: 'audio' })],
  pairing: { code: '12345678', expires_at: Date.now() / 1000 + 200 },
  devices: [{ id: 'd1', name: 'Tablet', created: 1, last_seen: Date.now() / 1000, online: true }],
  settings: { remember_control: false, confirm_when_live: true, check_updates: true },
  maison: { paired: false, state: 'unpaired', message: '', origin: 'https://maison.example' },
  network: [{ ip: '192.168.1.2', adapter: 'Ethernet', preferred: true, url: 'http://192.168.1.2:8765/', qr: ['101', '010', '101'] }],
  history: [{ time: 1, source: 'phone:Tablet', label: 'BRB', ok: true, message: 'Scene: BRB' }],
  autostart: { available: true, enabled: false },
  update: { available: true, latest: '9.0.0', url: 'https://github.com/kevincaron28/Lantern-Deck/releases' },
  last_test: null
};
const posts = {};
const fetch = async (url, opts = {}) => {
  assert.equal(opts.headers && opts.headers.Authorization, 'Bearer admin-token');
  if (url === '/api/events') return respond(200, {});
  if (url === '/api/state') return respond(200, state);
  if (opts.method === 'POST') { posts[url] = JSON.parse(opts.body); return respond(200, { ok: true }); }
  return respond(404, {});
};

(async () => {
  const dom = load('control.html', {
    url: 'http://127.0.0.1:8765/control#admin=admin-token', fetch,
    before: w => w.localStorage.setItem('lanternLang', 'en')
  });
  const w = dom.window, d = w.document;
  await wait(50);
  assert.equal(w.location.hash, '', 'admin token removed from the address bar');
  assert.equal(d.getElementById('pillStudio').textContent, 'Studio connected');
  assert.equal(d.getElementById('pillPhones').textContent, '1 phones · 1 online');
  assert.equal(d.getElementById('updateBanner').hidden, false);
  assert.deepEqual([...d.querySelectorAll('#checklist li')].map(li => li.className), ['done', 'done', 'current', '', '']);
  assert.equal(d.getElementById('pairCode').textContent, '1234 5678');

  d.getElementById('controlSwitch').click(); await wait(20);
  assert.deepEqual(posts['/api/control'], { enabled: true });

  d.getElementById('edit').click();
  assert.equal(d.querySelectorAll('.editrow').length, 6);
  d.getElementById('autoMatch').click();
  assert.deepEqual([...d.querySelectorAll('[name=scene]')].slice(0, 4).map(i => i.value), ['Starting soon', 'Gaming', 'BRB', 'Ending']);

  const row = d.querySelectorAll('.editrow')[5];
  const kind = row.querySelector('[name=kind]');
  kind.value = 'hotkey';
  kind.dispatchEvent(new w.Event('change'));
  const record = [...row.querySelectorAll('button')].find(b => b.textContent === 'Record shortcut');
  record.click();
  for (const type of ['keydown', 'keyup']) {
    d.dispatchEvent(new w.KeyboardEvent(type, { code: 'AltLeft', key: 'Alt', altKey: type === 'keydown', bubbles: true, cancelable: true }));
  }
  assert.equal(row.querySelector('[name=shortcut]').value, 'LeftAlt');
  record.click();
  d.dispatchEvent(new w.KeyboardEvent('keydown', { code: 'Escape', key: 'Escape', bubbles: true, cancelable: true }));
  assert.equal(record.textContent, 'Record shortcut', 'Escape cancels recording');

  d.getElementById('presetBrb').click();
  const macroRow = d.querySelector('#rows').lastElementChild;
  assert.equal(macroRow.querySelector('[name=kind]').value, 'macro');
  assert.equal(macroRow.querySelector('[name=stepScene]').value, 'BRB', 'preset picks the BRB scene by name');
  [...macroRow.querySelectorAll('button')].find(b => b.textContent === '+ Add step').click();
  const added = macroRow.querySelectorAll('.step-row')[2];
  const stepKind = added.querySelector('.step-kind');
  stepKind.value = 'wait';
  stepKind.dispatchEvent(new w.Event('change'));
  added.querySelector('[name=stepMs]').value = '700';

  d.getElementById('editForm').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await wait(20);
  const saved = posts['/api/config'].buttons;
  assert.equal(saved[1].action.scene, 'Gaming');
  assert.deepEqual(saved[5].action, { kind: 'hotkey' });
  assert.equal(saved[5].shortcut, 'LeftAlt');
  assert.deepEqual(saved[6].action, { kind: 'macro', steps: [{ kind: 'scene', scene: 'BRB' }, { kind: 'mic', muted: true }, { kind: 'wait', ms: 700 }] });
  assert.equal(d.getElementById('editor').open, false);

  d.getElementById('profile').value = 'hotkeys';
  d.getElementById('applyProfile').click(); await wait(20);
  assert.deepEqual(posts['/api/profile'], { name: 'hotkeys' });
  d.querySelector('[data-setting=remember_control]').click(); await wait(20);
  assert.deepEqual(posts['/api/settings'], { settings: { remember_control: true } });
  d.querySelector('#devices button').click(); await wait(20);
  assert.deepEqual(posts['/api/devices/revoke'], { id: 'd1' });
  dom.window.close();
  console.log('control: token handling, checklist, auto-match, recorder, save, profile, settings and devices passed');
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
