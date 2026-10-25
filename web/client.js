/* Shared browser helpers: API calls, the live event stream, icons and toasts. */
'use strict';
(function (root) {
  const Lantern = { token: '' };

  class ApiError extends Error {
    constructor(message, code, status) { super(message); this.code = code; this.status = status; }
  }
  Lantern.ApiError = ApiError;

  Lantern.api = async function (path, body) {
    const response = await fetch('/api/' + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Authorization': 'Bearer ' + Lantern.token, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(path === 'studio-test' || path === 'maison/pair' ? 60000 : 8000)
    });
    let data = {};
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) throw new ApiError(data.error || 'Request failed', data.code || 'failed', response.status);
    return data;
  };

  /* Server-sent events read through fetch so the token stays in a header.
     Falls back to polling when the browser cannot stream a response body. */
  Lantern.stream = function ({ onState, onOnline, onRevoked }) {
    let stopped = false, controller = null, delay = 1000;
    const poll = async () => {
      while (!stopped) {
        try { onState(await Lantern.api('state')); onOnline(true); }
        catch (e) { onOnline(false); if (e.status === 401) { onRevoked(); return; } }
        await new Promise(r => setTimeout(r, 2500));
      }
    };
    const run = async () => {
      while (!stopped) {
        controller = new AbortController();
        try {
          const response = await fetch('/api/events', { headers: { 'Authorization': 'Bearer ' + Lantern.token }, signal: controller.signal });
          if (response.status === 401) { onRevoked(); return; }
          if (!response.ok) throw new Error('stream');
          if (!response.body || !response.body.getReader) { poll(); return; }
          onOnline(true); delay = 1000;
          const reader = response.body.getReader(), decoder = new TextDecoder();
          let buffer = '';
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let cut;
            while ((cut = buffer.indexOf('\n\n')) >= 0) {
              const block = buffer.slice(0, cut); buffer = buffer.slice(cut + 2);
              let event = 'message', data = '';
              for (const line of block.split('\n')) {
                if (line.startsWith('event: ')) event = line.slice(7);
                else if (line.startsWith('data: ')) data += line.slice(6);
              }
              if (event === 'revoked') { onRevoked(); return; }
              if (data) onState(JSON.parse(data));
            }
          }
        } catch (e) {
          if (stopped) return;
        }
        onOnline(false);
        await new Promise(r => setTimeout(r, delay));
        delay = Math.min(delay * 2, 10000);
      }
    };
    run();
    return { stop() { stopped = true; if (controller) controller.abort(); } };
  };

  const iconPaths = {
    '01': 'M3 4h18v13H3z M8 21h8 M12 17v4 M9 8l6 3-6 3z',
    '02': 'M3 6h12v12H3z M15 10l6-4v12l-6-4',
    '03': 'M9 4v7H4 M4 10a8 8 0 1 1 1 8 M12 8v5l3 2',
    '04': 'M5 21V4 M5 4h11l-2 4 2 4H5',
    '♫': 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0z M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M8 22h8',
    '♪': 'M4 9h4l5-4v14l-5-4H4z M16 9a4 4 0 0 1 0 6 M18.5 6.5a8 8 0 0 1 0 11',
    '▧': 'M3 4h18v14H3z M3 8h18 M7 12h5v3H7z M16 12h2 M16 15h2',
    '✦': 'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z'
  };
  Lantern.iconNode = function (value) {
    const el = document.createElement('span'); el.className = 'icon';
    if (iconPaths[value]) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', iconPaths[value]); svg.append(path); el.append(svg);
    } else el.textContent = value;
    return el;
  };

  let toastTimer;
  Lantern.toast = function (text, kind) {
    const box = document.getElementById('toast');
    if (!box) return;
    box.textContent = text; box.className = kind || ''; box.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { box.hidden = true; }, 4200);
  };

  /* 3725 -> "1:02:05": elapsed broadcast time. */
  Lantern.duration = function (seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), r = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : String(m)) + ':' + String(r).padStart(2, '0');
  };

  Lantern.el = function (tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  /* Localized message for an action result or error code, falling back to the server text. */
  Lantern.message = function (code, label, fallback) {
    const key = 'msg.' + code;
    return root.I18n && root.I18n.has(key) ? root.I18n.t(key, { label }) : fallback;
  };

  root.Lantern = Lantern;
})(window);
