/* Phone and tablet control surface. */
'use strict';
const L = window.Lantern, t = (key, vars) => I18n.t(key, vars);
const $ = id => document.getElementById(id);
const TOKEN_KEY = 'lanternDevice';
let state = null, online = false, pending = null, stream = null, deckSignature = '';

function readToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; } }
function writeToken(value) {
  try { if (value) localStorage.setItem(TOKEN_KEY, value); else localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
}
L.token = readToken();

function keyState(b, studio) {
  const kind = b.action.kind;
  if (!studio.connected || kind === 'hotkey') return null;
  if (kind === 'scene') return studio.scene === b.action.scene ? { cls: 'active', text: t('key.current') } : null;
  const muted = studio[kind + '_muted'];
  return muted ? { cls: 'muted', text: t('key.muted') } : { cls: 'on', text: t('key.on') };
}

function render() {
  const paired = !!L.token;
  $('pair').hidden = paired;
  $('controls').hidden = !paired;
  $('status').textContent = !paired ? t('status.unpaired') : online ? t('status.connected') : t('status.reconnecting');
  $('status').className = 'pill ' + (online ? 'ok' : paired ? 'warn' : '');
  if (!state || !paired) return;
  const studio = state.studio;
  $('studioPill').textContent = studio.connected ? t('studio.connected') : t('studio.offline');
  $('studioPill').className = 'pill ' + (studio.connected ? 'ok' : 'warn');
  $('controlPill').textContent = state.control ? t('control.on') : t('control.off');
  $('controlPill').className = 'pill ' + (state.control ? 'ok strong' : 'muted');
  $('livePill').hidden = !studio.live;
  $('emptyDeck').hidden = state.buttons.length > 0;
  $('deckNote').textContent = state.buttons.some(b => b.action.kind !== 'hotkey')
    ? (studio.connected ? t('deck.noteDirect') : t('deck.noteOffline')) : t('deck.noteHotkey');
  const signature = JSON.stringify([state.buttons, studio, state.control, online, pending, I18n.lang]);
  if (signature === deckSignature) return;
  deckSignature = signature;
  const deck = $('deck');
  deck.replaceChildren();
  for (const b of state.buttons) {
    const el = L.el('button', 'key kind-' + b.action.kind);
    el.type = 'button';
    el.style.setProperty('--accent', b.color);
    const status = keyState(b, studio);
    if (status) el.classList.add(status.cls);
    if (pending === b.id) el.classList.add('pending');
    el.disabled = !online || pending !== null;
    el.setAttribute('aria-label', b.label + (status ? ', ' + status.text : ''));
    el.append(L.iconNode(b.icon), L.el('span', 'label', b.label));
    if (status) el.append(L.el('span', 'key-state', status.text));
    el.onclick = () => press(b);
    deck.append(el);
  }
}

function ask(text) {
  return new Promise(resolve => {
    const dialog = $('confirmDialog');
    $('confirmText').textContent = text;
    dialog.returnValue = '';
    dialog.onclose = () => resolve(dialog.returnValue === 'ok');
    dialog.showModal();
  });
}

function flash(id, cls) {
  const key = [...$('deck').children][state.buttons.findIndex(b => b.id === id)];
  if (!key) return;
  key.classList.add(cls);
  setTimeout(() => key.classList.remove(cls), 600);
}

async function press(b, confirmed = false) {
  if (pending || !online) return;
  if (b.confirm && !confirmed && !await ask(t('confirm.action', { label: b.label }))) return;
  const studio = state.studio, kind = b.action.kind;
  const body = { id: b.id, confirmed: confirmed || b.confirm };
  if ((kind === 'mic' || kind === 'audio') && studio.connected) body.target = !studio[kind + '_muted'];
  if (navigator.vibrate) navigator.vibrate(12);
  pending = b.id; deckSignature = ''; render();
  try {
    const result = await L.api('press', body);
    const text = L.message(result.code, b.label, result.message);
    L.toast(text, 'ok');
    $('lastAction').textContent = text;
    $('actionTime').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    pending = null; deckSignature = ''; render(); flash(b.id, 'flash');
  } catch (e) {
    pending = null; deckSignature = ''; render();
    if (e.code === 'confirm_live' || e.code === 'confirm') {
      if (await ask(t(e.code === 'confirm_live' ? 'confirm.live' : 'confirm.action', { label: b.label }))) press(b, true);
      return;
    }
    if (e.status === 401) { forget(); return; }
    const text = L.message(e.code, b.label, e.message);
    L.toast(text, 'error'); flash(b.id, 'shake');
    $('lastAction').textContent = t('last.failed', { label: b.label }) + ' ' + text;
    if (navigator.vibrate) navigator.vibrate([30, 40, 30]);
  }
}

function connect() {
  if (stream) stream.stop();
  if (!L.token) { online = false; render(); return; }
  stream = L.stream({
    onState: s => { state = s; online = true; render(); },
    onOnline: value => { if (online !== value) { online = value; deckSignature = ''; render(); } },
    onRevoked: forget
  });
}

function forget() {
  if (stream) stream.stop();
  stream = null; L.token = ''; state = null; online = false; deckSignature = '';
  writeToken('');
  render();
}

$('pairForm').onsubmit = async e => {
  e.preventDefault();
  try {
    const name = $('deviceName').value.trim() || t('pair.namePlaceholder');
    const result = await L.api('pair', { code: $('code').value.replace(/\D/g, ''), name });
    L.token = result.token; writeToken(result.token);
    $('code').value = '';
    connect(); render();
  } catch (err) { L.toast(L.message(err.code, '', err.message), 'error'); }
};
$('disconnect').onclick = async () => {
  try { await L.api('forget-me', {}); } catch { /* already gone */ }
  forget();
};
$('fullscreen').onclick = async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch { L.toast(t('fullscreenUnavailable'), 'error'); }
};
$('lang').onclick = () => { I18n.toggle(); deckSignature = ''; render(); };
document.addEventListener('i18n', () => { $('lang').textContent = I18n.lang === 'fr' ? 'EN' : 'FR'; });
document.addEventListener('visibilitychange', () => { if (!document.hidden && L.token && !online) connect(); });

I18n.apply();
connect();
render();
