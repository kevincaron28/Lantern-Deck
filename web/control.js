/* PC control center: Live control, setup checklist, studio, Maison, phones, deck editor. */
'use strict';
const L = window.Lantern, t = (key, vars) => I18n.t(key, vars);
const $ = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
const ADMIN_KEY = 'lanternAdmin';
if (fragment.has('admin')) {
  try { sessionStorage.setItem(ADMIN_KEY, fragment.get('admin')); } catch { /* storage blocked */ }
  history.replaceState(null, '', '/control');
}
try { L.token = fragment.get('admin') || sessionStorage.getItem(ADMIN_KEY) || ''; } catch { L.token = fragment.get('admin') || ''; }

let state = null, online = false, selectedUrl = '', lastQr = '';

const run = async (work, success) => {
  try { const result = await work(); if (success) L.toast(success, 'ok'); return result; }
  catch (e) { L.toast(L.message(e.code, '', e.message), 'error'); return null; }
};
const time = epoch => new Date(epoch * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const pill = (node, text, cls) => { node.textContent = text; node.className = 'pill ' + (cls || ''); };
const sceneButtons = () => state.buttons.filter(b => b.action.kind === 'scene');

function renderHeader() {
  const s = state.studio, m = state.maison;
  $('version').textContent = 'v' + state.version;
  pill($('pillStudio'), s.connected ? t('studio.connected') : t('studio.offline'), s.connected ? 'ok' : 'warn');
  pill($('pillMaison'), m && m.paired ? (m.state === 'connected' ? t('maison.connected') : t('maison.offline')) : t('maison.unpaired'),
    m && m.state === 'connected' ? 'ok' : m && m.paired ? 'warn' : 'muted');
  const onlineCount = state.devices.filter(d => d.online).length;
  pill($('pillPhones'), t('phones.count', { n: state.devices.length, online: onlineCount }), onlineCount ? 'ok' : 'muted');
  const sw = $('controlSwitch');
  sw.setAttribute('aria-checked', String(state.control));
  sw.classList.toggle('on', state.control);
  $('heroTitle').textContent = state.control ? t('cc.heroOn') : t('cc.heroOff');
  $('heroText').textContent = state.control ? t('cc.heroOnText') : t('cc.heroOffText');
  $('liveWarn').hidden = !s.live;
  const update = state.update;
  $('updateBanner').hidden = !(update && update.available);
  if (update && update.available) {
    $('updateText').textContent = t('cc.update', { version: update.latest });
    $('updateLink').href = update.url;
  }
}

function renderChecklist() {
  const s = state.studio, scenes = sceneButtons();
  const scenesReady = scenes.every(b => b.action.scene && (!s.connected || s.scenes.includes(b.action.scene)));
  const steps = [
    ['studio', s.connected, null],
    ['surface', (state.maison && state.maison.paired) || state.devices.length > 0, null],
    ['scenes', scenes.length === 0 || scenesReady, ['deck.edit', openEditor]],
    ['test', !!(state.last_test && state.last_test.ok), s.connected && !s.live ? ['studio.runTest', runTest] : null],
    ['control', state.control, ['cc.turnOn', () => setControl(true)]]
  ];
  const list = $('checklist');
  list.replaceChildren();
  let current = false;
  for (const [key, done, action] of steps) {
    const item = L.el('li', done ? 'done' : current ? '' : 'current');
    if (!done) current = true;
    const text = L.el('div');
    text.append(L.el('strong', '', t('check.' + key)), L.el('span', 'hint', t('check.' + key + (done ? 'Done' : 'Todo'))));
    item.append(L.el('span', 'check-mark', done ? '✓' : ''), text);
    if (!done && action) {
      const button = L.el('button', 'secondary compact', t(action[0]));
      button.type = 'button'; button.onclick = action[1];
      item.append(button);
    }
    list.append(item);
  }
}

function renderStudio() {
  const s = state.studio;
  pill($('studioState'), s.connected ? t('studio.connected') : t('studio.offline'), s.connected ? 'ok' : 'warn');
  const yesNo = muted => muted === null || muted === undefined ? '—' : muted ? t('key.muted') : t('key.on');
  $('factScene').textContent = s.scene || '—';
  $('factMic').textContent = yesNo(s.mic_muted);
  $('factAudio').textContent = yesNo(s.audio_muted);
  tickLiveFact();
  $('studioMessage').textContent = s.connected ? '' : (s.message || '');
  const chips = $('sceneChips');
  chips.replaceChildren(...s.scenes.map(name => L.el('span', 'chip' + (name === s.scene ? ' active' : ''), name)));
  $('runTest').disabled = !s.connected || s.live;
  const results = $('testResults');
  results.replaceChildren();
  const test = state.last_test;
  if (test) {
    const head = L.el('li', test.ok ? 'ok' : 'fail', (test.ok ? t('studio.testPassed') : t('studio.testFailed')) + ' · ' + time(test.time));
    results.append(head, ...test.steps.map(step => L.el('li', step.ok ? 'ok' : 'fail',
      (step.ok ? '✓ ' : '✗ ') + step.step + (step.ok ? ` (${step.ms} ms)` : ' — ' + step.error))));
  }
  const list = $('sceneList');
  list.replaceChildren(...s.scenes.map(name => { const o = L.el('option'); o.value = name; return o; }));
}

function renderMaison() {
  const m = state.maison;
  if (!m) { $('maisonCard').hidden = true; return; }
  const labels = { connected: 'maison.connected', connecting: 'maison.connecting', offline: 'maison.offline',
    revoked: 'maison.revoked', unpaired: 'maison.unpaired' };
  pill($('maisonState'), t(labels[m.state] || 'maison.offline'), m.state === 'connected' ? 'ok' : m.paired ? 'warn' : 'muted');
  $('maisonMessage').textContent = m.paired ? t('maison.msg.' + m.state) : t('maison.msg.unpaired');
  $('maisonOpen').href = m.origin + '/deck.html';
  $('maisonForget').hidden = !m.paired;
}

function drawQr(rows) {
  const canvas = $('qr'), ctx = canvas.getContext && canvas.getContext('2d');
  if (!ctx) return;
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!rows) return;
  const scale = Math.floor(canvas.width / rows.length), offset = Math.floor((canvas.width - scale * rows.length) / 2);
  ctx.fillStyle = '#000';
  rows.forEach((row, y) => [...row].forEach((cell, x) => { if (cell === '1') ctx.fillRect(offset + x * scale, offset + y * scale, scale, scale); }));
}

function renderPhones() {
  const select = $('address'), nets = state.network;
  const options = nets.map(n => n.url).join('|');
  if (select.dataset.options !== options) {
    select.replaceChildren(...nets.map(n => { const o = L.el('option', '', `${n.ip} · ${n.adapter}`); o.value = n.url; return o; }));
    select.dataset.options = options;
  }
  if (!nets.some(n => n.url === selectedUrl)) selectedUrl = nets.length ? nets[0].url : '';
  select.value = selectedUrl;
  const net = nets.find(n => n.url === selectedUrl);
  $('addressText').textContent = net ? net.url : t('phones.noNetwork');
  const key = net ? net.url : '';
  if (key !== lastQr) { drawQr(net && net.qr); lastQr = key; }
  $('pairCode').textContent = state.pairing.code ? state.pairing.code.replace(/(\d{4})(\d{4})/, '$1 $2') : t('phones.expired');
  tickExpiry();
  const list = $('devices');
  list.replaceChildren();
  if (!state.devices.length) list.append(L.el('li', 'hint', t('phones.none')));
  for (const d of state.devices) {
    const item = L.el('li');
    const info = L.el('div');
    info.append(L.el('strong', '', d.name),
      L.el('span', 'hint', d.online ? t('phones.online') : t('phones.lastSeen', { time: new Date(d.last_seen * 1000).toLocaleString() })));
    const remove = L.el('button', 'text-button danger', t('phones.remove'));
    remove.type = 'button';
    remove.onclick = () => run(() => L.api('devices/revoke', { id: d.id }), t('phones.removed', { name: d.name }));
    item.append(L.el('span', 'dot' + (d.online ? ' on' : '')), info, remove);
    list.append(item);
  }
  $('revokeAll').hidden = !state.devices.length;
}

function tickLiveFact() {
  if (!state) return;
  const s = state.studio;
  $('factStream').textContent = !s.connected ? '—' : !s.live ? t('studio.notLive')
    : t('live') + (s.live_since ? ' · ' + L.duration(Date.now() / 1000 - s.live_since) : '');
}

function tickExpiry() {
  if (!state) return;
  const left = Math.max(0, Math.round(state.pairing.expires_at - Date.now() / 1000));
  $('pairExpiry').textContent = state.pairing.code && left ? t('phones.expires', { time: `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}` }) : '';
  if (!left && state.pairing.code) $('pairCode').textContent = t('phones.expired');
}

function describeAction(b) {
  const kind = b.action.kind;
  if (kind === 'scene') return b.action.scene ? t('kind.sceneNamed', { scene: b.action.scene }) : t('kind.sceneMissing');
  if (kind === 'hotkey') return b.shortcut || t('kind.hotkeyMissing');
  if (kind === 'macro') return t('kind.macroSteps', { n: b.action.steps.length });
  return t('kind.' + kind);
}

function renderDeck() {
  const preview = $('preview');
  preview.replaceChildren();
  for (const b of state.buttons) {
    const key = L.el('div', 'mini-key');
    key.style.setProperty('--accent', b.color);
    key.append(L.iconNode(b.icon), L.el('strong', '', b.label), L.el('small', '', describeAction(b)));
    preview.append(key);
  }
}

function renderSettings() {
  for (const box of document.querySelectorAll('[data-setting]')) box.checked = !!state.settings[box.dataset.setting];
  const auto = $('autostart');
  auto.checked = state.autostart.enabled;
  auto.disabled = !state.autostart.available;
}

function renderHistory() {
  const list = $('history');
  list.replaceChildren();
  if (!state.history.length) list.append(L.el('li', 'hint', t('activity.none')));
  for (const entry of state.history) {
    const item = L.el('li', entry.ok ? '' : 'fail');
    item.append(L.el('time', '', time(entry.time)), L.el('span', 'source', entry.source.replace(/^phone:/, '📱 ')),
      L.el('span', '', entry.message));
    list.append(item);
  }
}

function render() {
  $('offline').hidden = online || !state;
  document.body.classList.toggle('disconnected', !online);
  if (!state) return;
  renderHeader(); renderChecklist(); renderStudio(); renderMaison(); renderPhones(); renderDeck(); renderSettings(); renderHistory();
}

async function setControl(enabled) {
  await run(() => L.api('control', { enabled }), enabled ? t('cc.toastOn') : t('cc.toastOff'));
}

async function runTest() {
  if (!confirm(t('studio.testConfirm'))) return;
  $('runTest').disabled = true;
  $('runTest').textContent = t('studio.testRunning');
  const result = await run(() => L.api('studio-test', {}));
  $('runTest').textContent = t('studio.runTest');
  if (result) L.toast(result.ok ? t('studio.testPassed') : t('studio.testFailed'), result.ok ? 'ok' : 'error');
}

/* ---------- Deck editor ---------- */
let recording = null;
function stopRecording(message) {
  if (recording) {
    clearTimeout(recording.timer);
    document.removeEventListener('keydown', recording.down, true);
    document.removeEventListener('keyup', recording.up, true);
    window.removeEventListener('blur', recording.blur);
    recording.button.textContent = t('editor.record');
    recording = null;
  }
  if (message) $('recordStatus').textContent = message;
}
function startRecording(input, recordButton) {
  if (recording && recording.button === recordButton) { stopRecording(t('editor.recordCancelled')); return; }
  stopRecording();
  const held = new Set();
  let candidate = '', modifierOnly = '';
  recordButton.textContent = t('editor.recordCancel');
  $('recordStatus').textContent = t('editor.recordHelp');
  const down = e => {
    e.preventDefault(); e.stopPropagation();
    if (e.key === 'Escape') { stopRecording(t('editor.recordCancelled')); return; }
    if (e.repeat) return;
    held.add(e.code);
    if (ShortcutInput.modifiers[e.code]) { modifierOnly = held.size === 1 ? ShortcutInput.modifiers[e.code] : ''; return; }
    candidate = ShortcutInput.chord(e, held) || '';
    if (!candidate) { modifierOnly = ''; $('recordStatus').textContent = t('editor.recordInvalid'); }
  };
  const up = e => {
    e.preventDefault(); e.stopPropagation();
    held.delete(e.code);
    if (!held.size && (candidate || modifierOnly)) {
      input.value = candidate || modifierOnly;
      stopRecording(t('editor.recorded', { keys: input.value }));
    }
  };
  const blur = () => stopRecording(t('editor.recordBlur'));
  recording = { button: recordButton, down, up, blur, timer: setTimeout(() => stopRecording(t('editor.recordTimeout')), 15000) };
  document.addEventListener('keydown', down, true);
  document.addEventListener('keyup', up, true);
  window.addEventListener('blur', blur);
}

function button(text, action, cls) {
  const b = L.el('button', cls || 'secondary', text);
  b.type = 'button'; b.onclick = action;
  return b;
}
function field(labelText, input) {
  const wrap = L.el('label');
  wrap.append(L.el('span', '', labelText), input);
  return wrap;
}
function input(name, value, type = 'text', max = 40) {
  const node = L.el('input');
  node.name = name; node.type = type; node.value = value; node.autocomplete = 'off';
  if (type !== 'color') node.maxLength = max;
  return node;
}

function addRow(b) {
  const row = L.el('div', 'editrow');
  row.dataset.id = b.id;
  const heading = L.el('div', 'card-heading');
  const label = input('label', b.label); label.required = true;
  heading.append(L.iconNode(b.icon), field(t('editor.name'), label));
  row.append(heading);

  const kind = L.el('select'); kind.name = 'kind';
  for (const k of ['scene', 'mic', 'audio', 'macro', 'hotkey']) { const o = L.el('option', '', t('kind.option.' + k)); o.value = k; kind.append(o); }
  kind.value = b.action.kind;
  const scene = input('scene', b.action.scene || '', 'text', 200);
  scene.setAttribute('list', 'sceneList');
  scene.placeholder = t('editor.scenePlaceholder');
  const sceneField = field(t('editor.scene'), scene);
  const stepsBox = L.el('div', 'steps'), stepList = L.el('div', 'step-list');
  (b.action.steps || []).forEach(step => stepList.append(stepRow(step)));
  stepsBox.append(L.el('span', 'tiny', t('editor.steps')), stepList,
    button(t('editor.addStep'), () => { if (stepList.children.length < 8) stepList.append(stepRow({ kind: 'scene' })); }));
  row.append(field(t('editor.action'), kind), sceneField, stepsBox);

  const shortcutField = input('shortcut', b.shortcut || '', 'text', 80);
  const shortcutWrap = field(t('editor.shortcut'), shortcutField);
  const tools = L.el('div', 'shortcut-tools');
  const record = button(t('editor.record'), () => startRecording(shortcutField, record));
  tools.append(record, button(t('editor.clear'), () => { stopRecording(); shortcutField.value = ''; }));
  const picker = L.el('details', 'key-picker');
  picker.append(L.el('summary', '', t('editor.choose')));
  const picks = [];
  for (const family of ['Ctrl', 'Alt', 'Shift', 'Key']) {
    const select = L.el('select');
    const options = family === 'Key'
      ? ['', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ', ...'0123456789', ...Array.from({ length: 24 }, (_, i) => 'F' + (i + 1)), 'Space', 'Enter', 'Tab', 'Esc', 'Up', 'Down', 'Left', 'Right']
      : ['', family, 'Left' + family, 'Right' + family];
    for (const value of options) { const o = L.el('option', '', value ? value.replace(/^(Left|Right)/, '$1 ') : t('editor.none')); o.value = value; select.append(o); }
    picker.append(field(family === 'Key' ? t('editor.key') : family, select));
    picks.push(select);
  }
  picker.append(button(t('editor.useKeys'), () => { stopRecording(); shortcutField.value = picks.map(s => s.value).filter(Boolean).join('+'); }));
  const shortcutBox = L.el('div', 'shortcut-box');
  shortcutBox.append(shortcutWrap, tools, picker);
  row.append(shortcutBox);

  const more = L.el('details', 'appearance');
  more.append(L.el('summary', '', t('editor.more')));
  more.append(field(t('editor.icon'), input('icon', b.icon, 'text', 12)), field(t('editor.color'), input('color', b.color, 'color')));
  const check = (name, checked, text) => {
    const wrap = L.el('label', 'toggle'), box = L.el('input');
    box.type = 'checkbox'; box.name = name; box.checked = checked;
    wrap.append(box, L.el('span', '', text));
    return wrap;
  };
  const fallback = check('fallback', b.fallback, t('editor.fallback'));
  more.append(check('confirm', b.confirm, t('editor.confirm')), fallback);
  more.append(button(t('editor.remove'), () => { stopRecording(); row.remove(); }, 'text-button danger'));
  row.append(more);

  const sync = () => {
    const k = kind.value;
    sceneField.hidden = k !== 'scene';
    stepsBox.hidden = k !== 'macro';
    shortcutBox.hidden = k === 'macro';
    fallback.hidden = k === 'hotkey' || k === 'macro';
    if (k === 'macro' && !stepList.children.length) stepList.append(stepRow({ kind: 'scene' }));
    shortcutWrap.querySelector('span').textContent = k === 'hotkey' ? t('editor.shortcut') : t('editor.fallbackShortcut');
  };
  kind.onchange = sync; sync();
  $('rows').append(row);
}

function stepRow(step) {
  const row = L.el('div', 'step-row');
  const kind = L.el('select', 'step-kind');
  for (const k of ['scene', 'mic', 'audio', 'wait']) { const o = L.el('option', '', t('editor.step.' + k)); o.value = k; kind.append(o); }
  kind.value = step.kind;
  const value = L.el('span', 'step-value');
  const build = () => {
    value.replaceChildren();
    if (kind.value === 'scene') {
      const scene = input('stepScene', step.scene || '', 'text', 200);
      scene.setAttribute('list', 'sceneList');
      scene.placeholder = t('editor.scenePlaceholder');
      value.append(scene);
    } else if (kind.value === 'wait') {
      const ms = input('stepMs', String(step.ms || 1000), 'number');
      ms.min = '100'; ms.max = '5000'; ms.step = '100';
      value.append(ms);
    } else {
      const muted = L.el('select');
      muted.name = 'stepMuted';
      for (const [v, label] of [['true', t('editor.mute')], ['false', t('editor.unmute')]]) { const o = L.el('option', '', label); o.value = v; muted.append(o); }
      muted.value = String(step.muted ?? true);
      value.append(muted);
    }
  };
  kind.onchange = build;
  build();
  row.append(kind, value, button('✕', () => row.remove(), 'text-button danger'));
  return row;
}

function readSteps(row) {
  return [...row.querySelectorAll('.step-row')].map(stepNode => {
    const kind = stepNode.querySelector('.step-kind').value;
    if (kind === 'scene') return { kind, scene: stepNode.querySelector('[name=stepScene]').value };
    if (kind === 'wait') return { kind, ms: parseInt(stepNode.querySelector('[name=stepMs]').value, 10) || 0 };
    return { kind, muted: stepNode.querySelector('[name=stepMuted]').value === 'true' };
  });
}

function collect() {
  return [...$('rows').children].map(row => {
    const get = name => row.querySelector(`[name=${name}]`);
    const kind = get('kind').value;
    return {
      id: row.dataset.id, label: get('label').value, icon: get('icon').value, color: get('color').value,
      action: kind === 'scene' ? { kind, scene: get('scene').value } : kind === 'macro' ? { kind, steps: readSteps(row) } : { kind },
      shortcut: get('shortcut').value, fallback: get('fallback').checked, confirm: get('confirm').checked
    };
  });
}

const SCENE_WORDS = {
  starting: ['start', 'début', 'debut', 'intro', 'bienvenue', 'welcome', 'opening'],
  gaming: ['gaming', 'game', 'jeu', 'main', 'principal', 'play'],
  brb: ['brb', 'pause', 'break', 'back', 'retour', 'away'],
  ending: ['ending', 'end', 'fin', 'outro', 'merci', 'bye']
};
function autoMatch() {
  const scenes = state.studio.scenes;
  if (!scenes.length) { $('recordStatus').textContent = t('editor.matchNoStudio'); return; }
  let matched = 0;
  for (const row of $('rows').children) {
    const kind = row.querySelector('[name=kind]').value, sceneInput = row.querySelector('[name=scene]');
    if (kind !== 'scene' || sceneInput.value) continue;
    const label = row.querySelector('[name=label]').value.toLowerCase();
    const words = SCENE_WORDS[row.dataset.id] || [label];
    const found = scenes.find(s => s.toLowerCase() === label) || scenes.find(s => words.some(w => s.toLowerCase().includes(w)));
    if (found) { sceneInput.value = found; matched++; }
  }
  $('recordStatus').textContent = t('editor.matched', { n: matched });
}

function sceneFor(id) {
  const words = SCENE_WORDS[id];
  return state.studio.scenes.find(s => words.some(w => s.toLowerCase().includes(w))) || '';
}
function addPreset(brb) {
  if ($('rows').children.length >= 32) { $('saveError').textContent = t('editor.max'); return; }
  addRow({
    id: 'm' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    label: t(brb ? 'editor.presetBrbLabel' : 'editor.presetBackLabel'), icon: brb ? '03' : '02',
    color: brb ? '#d3acff' : '#4dd9b1', shortcut: '', fallback: false, confirm: false,
    action: { kind: 'macro', steps: [{ kind: 'scene', scene: sceneFor(brb ? 'brb' : 'gaming') }, { kind: 'mic', muted: brb }] }
  });
  $('rows').lastElementChild.scrollIntoView({ block: 'nearest' });
  $('recordStatus').textContent = t('editor.presetAdded');
}

function openEditor() {
  stopRecording();
  $('rows').replaceChildren();
  state.buttons.forEach(addRow);
  $('saveError').textContent = '';
  $('recordStatus').textContent = t('editor.status');
  $('editor').showModal();
}

/* ---------- Wiring ---------- */
$('controlSwitch').onclick = () => state && setControl(!state.control);
$('runTest').onclick = runTest;
$('maisonForm').onsubmit = async e => {
  e.preventDefault();
  const code = $('maisonCode').value.replace(/\D/g, '');
  const button = e.target.querySelector('button');
  button.disabled = true;
  if (await run(() => L.api('maison/pair', { code }), t('maison.paired'))) $('maisonCode').value = '';
  button.disabled = false;
};
$('maisonForget').onclick = () => confirm(t('maison.forgetConfirm')) && run(() => L.api('maison/forget', {}), t('maison.forgotten'));
$('address').onchange = e => { selectedUrl = e.target.value; render(); };
$('newCode').onclick = () => run(() => L.api('pair-code', {}));
$('revokeAll').onclick = () => confirm(t('phones.revokeConfirm')) && run(() => L.api('devices/revoke', { all: true }), t('phones.revokedAll'));
$('edit').onclick = openEditor;
$('applyProfile').onclick = () => confirm(t('deck.applyConfirm')) && run(() => L.api('profile', { name: $('profile').value }), t('deck.applied'));
$('exportDeck').onclick = () => run(async () => {
  const config = await L.api('export');
  const link = L.el('a');
  link.href = URL.createObjectURL(new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' }));
  link.download = 'Lantern-deck.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
});
$('importDeck').onclick = () => $('importFile').click();
$('importFile').onchange = async e => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file || !confirm(t('deck.importConfirm'))) return;
  await run(async () => L.api('import', { config: JSON.parse(await file.text()) }), t('deck.imported'));
};
for (const box of document.querySelectorAll('[data-setting]')) {
  box.onchange = () => run(() => L.api('settings', { settings: { [box.dataset.setting]: box.checked } }), t('settings.saved'));
}
$('autostart').onchange = e => run(() => L.api('autostart', { enabled: e.target.checked }), t('settings.saved'));
let diagText = '';
$('showDiag').onclick = () => run(async () => {
  diagText = JSON.stringify(await L.api('diagnostics'), null, 2);
  $('diagOutput').textContent = diagText; $('diagOutput').hidden = false;
});
$('copyDiag').onclick = () => run(async () => {
  diagText = JSON.stringify(await L.api('diagnostics'), null, 2);
  await navigator.clipboard.writeText(diagText);
}, t('diag.copied'));
$('openLogs').onclick = () => run(() => L.api('open-logs', {}));
$('close').onclick = () => { stopRecording(); $('editor').close(); };
$('editor').addEventListener('close', () => stopRecording());
$('autoMatch').onclick = autoMatch;
$('presetBrb').onclick = () => addPreset(true);
$('presetBack').onclick = () => addPreset(false);
$('add').onclick = () => {
  if ($('rows').children.length >= 32) { $('saveError').textContent = t('editor.max'); return; }
  addRow({ id: 'b' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7), label: t('editor.newLabel'), icon: '✦',
    color: '#c5f8a9', action: { kind: 'scene', scene: '' }, shortcut: '', fallback: false, confirm: false });
};
$('editForm').onsubmit = async e => {
  e.preventDefault();
  stopRecording();
  try {
    await L.api('config', { buttons: collect() });
    $('editor').close();
    L.toast(t('editor.saved'), 'ok');
  } catch (err) { $('saveError').textContent = err.message; }
};
$('lang').onclick = () => { I18n.toggle(); render(); };
document.addEventListener('i18n', () => { $('lang').textContent = I18n.lang === 'fr' ? 'EN' : 'FR'; });
setInterval(() => { tickExpiry(); tickLiveFact(); }, 1000);

I18n.apply();
if (!L.token) {
  $('offline').hidden = false;
} else {
  L.stream({
    onState: s => { state = s; online = true; render(); },
    onOnline: value => { online = value; render(); },
    onRevoked: () => { online = false; $('offline').hidden = false; }
  });
}
