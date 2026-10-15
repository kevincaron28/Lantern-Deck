"""Lantern Deck: dependency-free local shortcut companion (Python 3.10+)."""
import argparse
import ctypes
from ctypes import wintypes
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
MODS = {'CTRL': 0x11, 'ALT': 0x12, 'SHIFT': 0x10,
        'LEFTCTRL': 0xA2, 'RIGHTCTRL': 0xA3, 'LEFTALT': 0xA4, 'RIGHTALT': 0xA5,
        'LEFTSHIFT': 0xA0, 'RIGHTSHIFT': 0xA1}
MOD_SCANS = {0x11: (0x1D, False), 0xA2: (0x1D, False), 0xA3: (0x1D, True),
             0x12: (0x38, False), 0xA4: (0x38, False), 0xA5: (0x38, True),
             0x10: (0x2A, False), 0xA0: (0x2A, False), 0xA1: (0x36, False)}

def modifier_family(part):
    return part.removeprefix('LEFT').removeprefix('RIGHT')

def key_events(combo):
    """Return (virtual key, scan code, flags); side-specific modifiers use physical scans."""
    parts = shortcut(combo).split('+')
    codes = [MODS[p] if p in MODS else KEYS[p] for p in parts]
    def event(k, up=False):
        if k in MOD_SCANS:
            scan, extended = MOD_SCANS[k]
            return (0, scan, 8 | int(extended) | (2 if up else 0))
        return (k, 0, int(k in (0x25, 0x26, 0x27, 0x28)) | (2 if up else 0))
    return codes, [event(k) for k in codes] + [event(k, True) for k in reversed(codes)]
KEYS = {**{chr(n): n for n in range(65, 91)}, **{str(n): 48+n for n in range(10)},
        **{'F'+str(n): 0x6F+n for n in range(1, 25)},
        'SPACE': 0x20, 'ENTER': 0x0D, 'TAB': 9, 'ESC': 0x1B,
        'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27}

def shortcut(value):
    if not isinstance(value, str):
        raise ValueError('Shortcut must be text')
    if not value.strip():
        return ''
    aliases = {'LALT':'LEFTALT','RALT':'RIGHTALT','LCTRL':'LEFTCTRL','RCTRL':'RIGHTCTRL',
               'LSHIFT':'LEFTSHIFT','RSHIFT':'RIGHTSHIFT','CONTROL':'CTRL',
               'LEFTCONTROL':'LEFTCTRL','RIGHTCONTROL':'RIGHTCTRL'}
    parts = [re.sub(r'[ _-]', '', p).upper() for p in value.split('+')]
    parts = [aliases.get(p, p) for p in parts]
    single = len(parts) == 1 and (parts[0] in MODS or re.fullmatch(r'F(?:[1-9]|1[0-9]|2[0-4])', parts[0]))
    families = [modifier_family(p) for p in parts[:-1]]
    chord = len(parts) >= 2 and parts[-1] in KEYS and all(p in MODS for p in parts[:-1]) and len(set(families)) == len(families)
    if not (single or chord):
        raise ValueError('Use a modifier plus a key, one modifier, or F1–F24')
    return '+'.join(parts)

def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get('buttons'), list) or not 1 <= len(data['buttons']) <= 32:
        raise ValueError('Use 1–32 buttons')
    buttons, ids = [], set()
    for b in data['buttons']:
        if not isinstance(b, dict):
            raise ValueError('Invalid button')
        ident = b.get('id', '')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', ident) or ident in ids:
            raise ValueError('Button IDs must be unique')
        ids.add(ident)
        label, icon, color = b.get('label'), b.get('icon'), b.get('color')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 40 or not isinstance(icon, str) or len(icon) > 12:
            raise ValueError('Use a label of 1–40 characters and a short icon')
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Invalid color')
        buttons.append(dict(id=ident, label=label.strip(), icon=icon, color=color,
                            shortcut=shortcut(b.get('shortcut', '')), confirm=b.get('confirm') is True))
    return {'buttons': buttons}

def defaults():
    names = [('Main scene', '01', '#4dd9b1'), ('Close-up', '02', '#80a7ff'), ('Be right back', '03', '#d3acff'),
             ('Microphone', '♫', '#f4b66c'), ('Overlay', '▧', '#ff8f9e'), ('Your shortcut', '✦', '#7dd4e8')]
    return {'buttons': [dict(id='b'+str(i), label=n, icon=ic, color=c, shortcut='', confirm=False) for i, (n, ic, c) in enumerate(names)]}

def studio_profile(audio_only=False):
    rows = [('starting', 'Starting', '01', '#80a7ff', '1'),
            ('gaming', 'Main gaming', '02', '#4dd9b1', '2'),
            ('brb', 'BRB', '03', '#d3acff', '3'),
            ('ending', 'Ending', '04', '#ff8f9e', '4'),
            ('microphone', 'Microphone', '♫', '#f4b66c', 'M'),
            ('desktop-audio', 'Desktop sound', '♪', '#7dd4e8', 'D')]
    return validate({'buttons': [dict(id=i, label=n, icon=ic, color=c,
                    shortcut='CTRL+SHIFT+'+k, confirm=False)
                    for i,n,ic,c,k in (rows[-2:] if audio_only else rows)]})

def send_keys(combo):
    if os.name != 'nt':
        raise RuntimeError('Keyboard output requires Windows')
    # Full INPUT union is required for the correct Windows ABI on both 32/64 bit.
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                    ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]
    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]
    class UNION(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('hi', HARDWAREINPUT)]
    class INPUT(ctypes.Structure):
        _anonymous_ = ('u',)
        _fields_ = [('type', wintypes.DWORD), ('u', UNION)]
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    api.SendInput.restype = wintypes.UINT
    api.GetAsyncKeyState.argtypes = [ctypes.c_int]
    api.GetAsyncKeyState.restype = wintypes.SHORT
    codes, events = key_events(combo)
    if any(api.GetAsyncKeyState(k) & 0x8000 for k in set(codes + list(MODS.values()) + [0x5B, 0x5C])):
        raise RuntimeError('Release keyboard modifiers and shortcut keys, then retry')
    def event(vk, scan, flags):
        return INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags))
    batch = (INPUT * len(events))(*[event(*e) for e in events])
    if api.SendInput(len(batch), batch, ctypes.sizeof(INPUT)) != len(batch):
        release = (INPUT * len(codes))(*[event(*e) for e in events[len(codes):]])
        api.SendInput(len(release), release, ctypes.sizeof(INPUT))
        raise RuntimeError('Windows did not accept all keys; check application privilege levels')

class State:
    def __init__(self, path, execute=False, sender=send_keys):
        self.path, self.execute, self.sender = path, execute, sender
        self.config = validate(json.loads(path.read_text('utf-8'))) if path.exists() else defaults()
        self.admin = secrets.token_urlsafe(32)
        self.sessions = set()
        self.lock = threading.Lock()
        self.last = 0
        self.attempts = []
        self.rotate()

    def rotate(self):
        self.code = str(secrets.randbelow(100000000)).zfill(8)
        self.code_until = time.monotonic() + 300

class Handler(BaseHTTPRequestHandler):
    server_version = 'LanternDeck/1.0'
    def log_message(self, *_):
        pass  # Do not log pairing credentials or tokens.

    def reply(self, status, data, mime='application/json'):
        raw = json.dumps(data).encode() if mime == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(raw)

    def guard(self):
        host = self.headers.get('Host', '')
        if host not in self.server.allowed_hosts:
            self.reply(403, {'error': 'Unrecognized host; use an address printed by the server'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + host:
            self.reply(403, {'error': 'Cross-origin request blocked'})
            return False
        return True

    def identity(self):
        token = self.headers.get('Authorization', '').removeprefix('Bearer ')
        s = self.server.state
        admin = ipaddress.ip_address(self.client_address[0]).is_loopback and secrets.compare_digest(token, s.admin)
        return admin, admin or token in s.sessions

    def do_GET(self):
        if not self.guard(): return
        if self.path in ('/', '/app.js', '/shortcuts.js', '/style.css'):
            name, mime = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript'), '/shortcuts.js': ('shortcuts.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}[self.path]
            return self.reply(200, (ROOT / 'web' / name).read_bytes(), mime)
        with self.server.state.lock:
            admin, authed = self.identity()
            if not authed: return self.reply(401, {'error': 'Pair this device first'})
            if self.path == '/api/state':
                s = self.server.state
                return self.reply(200, dict(**s.config, admin=admin, mode='keys enabled' if s.execute else 'rehearsal',
                                           pairing=s.code if admin and time.monotonic() < s.code_until else None))
        self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.guard(): return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32768 or self.headers.get('Content-Type') != 'application/json':
                return self.reply(400, {'error': 'Expected small JSON request'})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError('Expected object')
            with self.server.state.lock:
                s = self.server.state
                admin, authed = self.identity()
                now = time.monotonic()
                if self.path == '/api/pair':
                    s.attempts = [t for t in s.attempts if now-t < 60]
                    if len(s.attempts) >= 10: return self.reply(429, {'error': 'Too many attempts. Wait one minute.'})
                    s.attempts.append(now)
                    if now >= s.code_until or not secrets.compare_digest(str(body.get('code', '')), s.code):
                        return self.reply(403, {'error': 'Incorrect or expired code. Generate a code on the PC.'})
                    if len(s.sessions) >= 16: return self.reply(409, {'error': 'Device limit reached; revoke devices on PC'})
                    token = secrets.token_urlsafe(32)
                    s.sessions.add(token)
                    s.rotate()  # Single-use pairing codes.
                    return self.reply(200, {'token': token})
                if not authed: return self.reply(401, {'error': 'Pair this device first'})
                if self.path in ('/api/config', '/api/pair-code', '/api/revoke'):
                    if not admin: return self.reply(403, {'error': 'Use the PC editor to manage the deck'})
                    if self.path == '/api/config':
                        config = validate(body)
                        temp = s.path.with_suffix('.tmp')
                        temp.write_text(json.dumps(config, indent=2, ensure_ascii=False), 'utf-8')
                        temp.replace(s.path)
                        s.config = config
                    elif self.path == '/api/revoke':
                        s.sessions.clear()
                        s.rotate()
                    else: s.rotate()
                    return self.reply(200, {'ok': True})
                if self.path == '/api/trigger':
                    b = next((b for b in s.config['buttons'] if b['id'] == body.get('id')), None)
                    if b is None or not b['shortcut']: return self.reply(400, {'error': 'Button has no configured shortcut'})
                    if b['confirm'] and body.get('confirmed') is not True: return self.reply(400, {'error': 'Confirmation required'})
                    if now-s.last < .35: return self.reply(429, {'error': 'Please wait before pressing again'})
                    s.last = now
                    if s.execute: s.sender(b['shortcut'])
                    return self.reply(200, {'message': ('Keys sent: ' if s.execute else 'Rehearsed: ') + b['label']})
                self.reply(404, {'error': 'Not found'})
        except (ValueError, TypeError): self.reply(400, {'error': 'Invalid data. Check labels, colors and shortcut format.'})
        except (OSError, RuntimeError): self.reply(500, {'error': 'Operation failed. Check file permissions or release held keys and check Windows privilege levels.'})

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--bind', default='0.0.0.0')
    p.add_argument('--enable-keys', action='store_true', help='Actually send keys; default is rehearsal')
    p.add_argument('--config', type=Path, default=ROOT / 'deck.json')
    args = p.parse_args()
    if args.enable_keys and os.name != 'nt': p.error('Key output requires Windows')
    state = State(args.config, args.enable_keys)
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.daemon_threads = True
    server.state = state
    addresses = {'127.0.0.1', 'localhost'}
    addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    if args.bind != '0.0.0.0': addresses.add(args.bind)
    server.allowed_hosts = {f'{ip}:{args.port}' for ip in addresses}
    print('\nLANTERN DECK • ' + ('KEY OUTPUT ENABLED' if args.enable_keys else 'REHEARSAL — no keys sent'))
    print(f'PC editor: http://localhost:{args.port}/#admin={state.admin}')
    for ip in sorted(addresses - {'localhost', '127.0.0.1'}): print(f'Tablet: http://{ip}:{args.port}/')
    print(f'Pairing code (5 minutes, one use): {state.code}')
    print('Trusted private LAN only. HTTP is not encrypted. Do not port-forward. Ctrl+C stops the server.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__ == '__main__': main()
