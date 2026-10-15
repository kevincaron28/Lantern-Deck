'use strict';
const $ = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
let token = fragment.get('admin') || sessionStorage.getItem('lanternToken') || '';
if (fragment.has('admin')) { sessionStorage.setItem('lanternToken', token); history.replaceState(null, '', '/'); }
let state = null, busy = false, online = false, toastTimer, deckSignature = '';
const iconPaths = {
  '01':'M3 4h18v13H3z M8 21h8 M12 17v4 M9 8l6 3-6 3z',
  '02':'M3 6h12v12H3z M15 10l6-4v12l-6-4',
  '03':'M9 4v7H4 M4 10a8 8 0 1 1 1 8 M12 8v5l3 2',
  '♫':'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0z M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M8 22h8',
  '▧':'M3 4h18v14H3z M3 8h18 M7 12h5v3H7z M16 12h2 M16 15h2',
  '✦':'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z'
};
function iconNode(value) {
  const el = document.createElement('span'); el.className = 'icon';
  if (iconPaths[value]) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg','svg'); svg.setAttribute('viewBox','0 0 24 24'); svg.setAttribute('aria-hidden','true');
    const path = document.createElementNS('http://www.w3.org/2000/svg','path'); path.setAttribute('d',iconPaths[value]); svg.append(path); el.append(svg);
  } else el.textContent = value;
  return el;
}
async function api(path, body) {
  const response = await fetch('/api/' + path, {method: body === undefined ? 'GET' : 'POST', headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(5000)});
  const data = await response.json();
  if (!response.ok) { if (response.status === 401) { token = ''; sessionStorage.removeItem('lanternToken'); } throw new Error(data.error || 'Request failed'); }
  return data;
}
function toast(text) { $('toast').textContent = text; $('toast').style.display = 'block'; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').style.display = 'none', 4500); }
function render() {
  document.body.classList.toggle('paired-view', !!token);
  document.body.classList.toggle('remote-view', !!state && !state.admin);
  $('pair').hidden = !!token; $('controls').hidden = !token;
  $('adminPanel').hidden = !(state && state.admin && online);
  $('edit').hidden = !(state && state.admin); $('edit').disabled = !online;
  $('status').textContent = online ? '● Connected to PC' : token ? '○ PC unavailable' : '○ Not paired';
  $('status').className = online ? 'online' : '';
  if (!state) return;
  $('mode').textContent = state.mode === 'rehearsal' ? 'Rehearsal · no keys sent' : 'Keyboard output enabled';
  const visibleButtons = state.admin ? state.buttons : state.buttons.filter(b => b.shortcut);
  $('buttonCount').textContent = visibleButtons.length + ' KEYS';
  $('emptyDeck').hidden = visibleButtons.length > 0;
  $('deckHint').textContent = state.buttons.some(b => b.shortcut) ? 'Tap a key to send its shortcut' : 'Customize your keys to get started';
  $('pairCode').textContent = state.pairing || 'Code expired';
  const signature = JSON.stringify([visibleButtons, state.admin, online, busy]);
  if (signature === deckSignature) return;
  deckSignature = signature;
  $('deck').replaceChildren();
  for (const [index, b] of visibleButtons.entries()) {
    const el = document.createElement('button'); el.className = 'key' + (!b.shortcut ? ' unassigned' : ''); el.style.setProperty('--accent', b.color);
    el.disabled = !online || !b.shortcut || busy;
    el.setAttribute('aria-label', b.label + ', ' + (b.shortcut || 'Unassigned shortcut'));
    el.title = b.shortcut || 'Assign a shortcut using Customize deck on the PC';
    const number = document.createElement('span'); number.className = 'slot-number'; number.textContent = String(index + 1).padStart(2,'0'); number.setAttribute('aria-hidden','true');
    const dot = document.createElement('span'); dot.className = 'key-indicator'; dot.setAttribute('aria-hidden','true');
    el.append(number, dot, iconNode(b.icon));
    for (const [tag, cls, text] of [['span','label',b.label],['small','',b.shortcut || 'UNASSIGNED']]) {
      const child = document.createElement(tag); child.className = cls; child.textContent = text; el.append(child);
    }
    el.onclick = async () => {
      if (busy || !online) return;
      if (b.confirm && !confirm('Send shortcut for “' + b.label + '”? Check your PC before continuing.')) return;
      busy = true; render();
      try { const result = await api('trigger', {id:b.id, confirmed:b.confirm}); toast(result.message + (state.mode === 'rehearsal' ? '' : ' — application state unverified')); $('lastAction').textContent = result.message; $('actionTime').textContent = new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
      catch (e) { toast(e.message + ' No automatic retry.'); $('lastAction').textContent = 'Delivery unconfirmed: ' + b.label; $('actionTime').textContent = new Date().toLocaleTimeString(); }
      finally { busy = false; await refresh(); }
    };
    $('deck').append(el);
  }
}
async function refresh() {
  if (!token) { online = false; render(); return; }
  try { state = await api('state'); online = true; } catch { online = false; }
  render();
}
$('pairForm').onsubmit = async e => { e.preventDefault(); try { const result = await api('pair', {code:$('code').value}); token = result.token; sessionStorage.setItem('lanternToken', token); $('code').value = ''; await refresh(); } catch (e) { toast(e.message); } };
$('disconnect').onclick = () => { token = ''; state = null; deckSignature = ''; sessionStorage.removeItem('lanternToken'); document.body.classList.remove('focus-view'); $('focus').textContent = 'Focus view'; refresh(); };
$('showShortcuts').onchange = e => document.body.classList.toggle('hide-shortcuts', !e.target.checked);
$('focus').onclick = () => { const focused = document.body.classList.toggle('focus-view'); $('focus').textContent = focused ? 'Exit focus' : 'Focus view'; $('focus').setAttribute('aria-pressed', String(focused)); };
$('fullscreen').onclick = async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen(); } catch { toast('Full screen is unavailable in this browser.'); } };
for (const [id, route] of [['newCode','pair-code'],['revoke','revoke']]) $(id).onclick = async () => { try { await api(route, {}); await refresh(); if (id === 'revoke') toast('All tablets revoked'); } catch(e) { toast(e.message); } };
function addRow(b) {
  const row = document.createElement('div'); row.className = 'editrow'; row.dataset.id = b.id;
  const heading = document.createElement('div'); heading.className = 'card-heading';
  heading.append(iconNode(b.icon)); row.append(heading);
  const appearance = document.createElement('details'); appearance.className = 'appearance';
  const summary = document.createElement('summary'); summary.textContent = 'Appearance and confirmation'; appearance.append(summary);
  let shortcutField;
  for (const [name, label, type, max] of [['label','Button name','text',40],['shortcut','Shortcut','text',80],['icon','Icon / emoji','text',12],['color','Color','color',7]]) {
    const wrap = document.createElement('label'); wrap.textContent = label;
    const input = document.createElement('input'); input.name = name; input.type = type; input.value = b[name]; input.maxLength = max; if (name === 'label') input.required = true;
    input.autocomplete = 'off';
    wrap.append(input);
    if (name === 'label') heading.append(wrap);
    else if (name === 'shortcut') { shortcutField = input; row.append(wrap); }
    else appearance.append(wrap);
  }
  const tools = document.createElement('div'); tools.className = 'shortcut-tools';
  const record = button('Record shortcut', () => startRecording(shortcutField, record));
  const clear = button('Clear', () => { stopRecording(); shortcutField.value = ''; });
  const suggested = presets.find(p=>p.label === b.label);
  if (suggested) tools.append(button('Use ' + suggested.shortcut, () => { stopRecording(); shortcutField.value=suggested.shortcut; }));
  tools.append(record, clear); row.append(tools);
  const picker = document.createElement('details'); picker.className = 'key-picker';
  const pickerTitle = document.createElement('summary'); pickerTitle.textContent = 'Choose keys instead'; picker.append(pickerTitle);
  const picks = [];
  for (const family of ['Ctrl','Alt','Shift','Key']) {
    const label = document.createElement('label'); label.textContent = family;
    const select = document.createElement('select');
    const options = family === 'Key' ? ['', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ', ...'0123456789', ...Array.from({length:24},(_,i)=>'F'+(i+1)), 'Space','Enter','Tab','Esc','Up','Down','Left','Right'] : ['', family, 'Left'+family, 'Right'+family];
    for (const value of options) { const opt = document.createElement('option'); opt.value=value; opt.textContent = value ? value.replace(/^(Left|Right)/,'$1 ') : 'None'; select.append(opt); }
    label.append(select); picker.append(label); picks.push(select);
  }
  picker.append(button('Use these keys', () => { stopRecording(); shortcutField.value=picks.map(s=>s.value).filter(Boolean).join('+'); })); row.append(picker);
  const label = document.createElement('label'); label.className = 'confirm';
  const check = document.createElement('input'); check.type = 'checkbox'; check.name = 'confirm'; check.checked = b.confirm;
  label.append(check, document.createTextNode('Ask before sending this shortcut')); appearance.append(label);
  appearance.append(button('Remove button', () => { stopRecording(); row.remove(); })); row.append(appearance); $('rows').append(row);
}
const presets = [
  {label:'Starting',icon:'01',color:'#80a7ff',shortcut:'Ctrl+Shift+1'},
  {label:'Main gaming',icon:'02',color:'#4dd9b1',shortcut:'Ctrl+Shift+2'},
  {label:'BRB',icon:'03',color:'#d3acff',shortcut:'Ctrl+Shift+3'},
  {label:'Ending',icon:'04',color:'#ff8f9e',shortcut:'Ctrl+Shift+4'},
  {label:'Microphone',icon:'♫',color:'#f4b66c',shortcut:'Ctrl+Shift+M'},
  {label:'Desktop sound',icon:'♪',color:'#7dd4e8',shortcut:'Ctrl+Shift+D'}
];
function button(text, action) { const b = document.createElement('button'); b.type='button'; b.className='secondary'; b.textContent=text; b.onclick=action; return b; }
function addPreset(p) {
  stopRecording();
  const existing = [...$('rows').children].find(row=>row.querySelector('[name=label]').value.trim().toLowerCase()===p.label.toLowerCase());
  if (existing) {
    const shortcut = existing.querySelector('[name=shortcut]');
    if (!shortcut.value.trim()) shortcut.value=p.shortcut;
    existing.scrollIntoView({block:'nearest'});
  } else if ($('rows').children.length < 32) addRow({...p,id:'b'+Date.now().toString(36)+Math.random().toString(36).slice(2,7),confirm:false});
  else { $('saveError').textContent='Remove a button first (32 maximum).'; return; }
  $('recordStatus').textContent = 'Ready to save. Assign the displayed shortcuts in LIVE Studio too. Existing shortcuts were kept.';
}
for (const p of presets) $('presets').append(button('+ '+p.label,()=>addPreset(p)));
$('starter').onclick=()=>presets.forEach(addPreset);
let recording = null;
function stopRecording(message) {
  if (recording) {
    clearTimeout(recording.timer); document.removeEventListener('keydown',recording.down,true); document.removeEventListener('keyup',recording.up,true); window.removeEventListener('blur',recording.blur);
    recording.button.textContent='Record shortcut'; recording=null;
  }
  if (message) $('recordStatus').textContent=message;
}
function startRecording(input, recordButton) {
  if (recording && recording.button===recordButton) { stopRecording('Recording cancelled.'); return; }
  stopRecording();
  const held = new Set(); let candidate = '', modifierOnly = '';
  recordButton.textContent='Cancel recording';
  $('recordStatus').textContent='Press and release your shortcut on the PC. Esc cancels. Browser-reserved keys: use Choose keys instead. Test offline; other apps may react to your physical keys.';
  const down = e => {
    e.preventDefault(); e.stopPropagation();
    if (e.key==='Escape') { stopRecording('Recording cancelled.'); return; }
    if (e.repeat) return;
    held.add(e.code);
    if (ShortcutInput.modifiers[e.code]) { modifierOnly=held.size===1 ? ShortcutInput.modifiers[e.code] : ''; return; }
    candidate=ShortcutInput.chord(e,held) || '';
    if (!candidate) { modifierOnly=''; $('recordStatus').textContent='Use Ctrl, Alt or Shift with a letter/key, a single modifier, or F1–F24. For other combinations use Choose keys.'; }
  };
  const up = e => {
    e.preventDefault(); e.stopPropagation(); held.delete(e.code);
    if (!held.size && (candidate || modifierOnly)) { input.value=candidate || modifierOnly; stopRecording('Recorded '+input.value+'. Save changes when ready.'); }
  };
  const blur = () => stopRecording('Recording cancelled because this window lost focus.');
  recording={button:recordButton,down,up,blur,timer:setTimeout(()=>stopRecording('Recording timed out. Try again or choose keys from the dropdowns.'),15000)};
  document.addEventListener('keydown',down,true); document.addEventListener('keyup',up,true); window.addEventListener('blur',blur);
}
function openEditor() { stopRecording(); $('rows').replaceChildren(); state.buttons.forEach(addRow); $('saveError').textContent = ''; $('editor').showModal(); }
$('edit').onclick = openEditor;
$('close').onclick = () => { stopRecording(); $('editor').close(); };
$('editor').addEventListener('close',()=>stopRecording());
$('add').onclick = () => { if ($('rows').children.length >= 32) return; addRow({id:'b'+Date.now().toString(36)+Math.random().toString(36).slice(2,7), label:'New shortcut',icon:'✦',color:'#c5f8a9',shortcut:'',confirm:false}); };
$('editForm').onsubmit = async e => {
  e.preventDefault();
  stopRecording();
  const buttons = [...$('rows').children].map(row => { const b = {id:row.dataset.id}; for (const input of row.querySelectorAll('input')) b[input.name] = input.type === 'checkbox' ? input.checked : input.value; return b; });
  try { await api('config', {buttons}); $('editor').close(); await refresh(); toast('Deck saved'); } catch(e) { $('saveError').textContent = e.message; }
};
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
refresh(); setInterval(refresh, 3000);
