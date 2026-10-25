"""Local HTTP server for phones/tablets and the PC control center.

Phones authenticate with a device token from one-time pairing. The control center
additionally needs a per-launch admin token and a loopback connection.
"""
import functools
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import logging
import secrets
import threading
import time

import qrcode

from lantern import VERSION, network, storage
from lantern.deck import PROFILES, profile, usable
from lantern.engine import ActionError, run_studio_test
from lantern.studio import StudioError

log = logging.getLogger(__name__)
STATIC = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/control': ('control.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/control.js': ('control.js', 'text/javascript; charset=utf-8'),
    '/client.js': ('client.js', 'text/javascript; charset=utf-8'),
    '/shortcuts.js': ('shortcuts.js', 'text/javascript; charset=utf-8'),
    '/i18n.js': ('i18n.js', 'text/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
    '/control.css': ('control.css', 'text/css; charset=utf-8'),
    '/icon.svg': ('icon.svg', 'image/svg+xml'),
}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
STREAM_PING = 15
ONLINE_WINDOW = 6


class Pairing:
    LIFETIME = 300

    def __init__(self):
        self.lock = threading.Lock()
        self.attempts = []
        self.rotate()

    def rotate(self):
        self.code = f'{secrets.randbelow(10 ** 8):08d}'
        self.until = time.monotonic() + self.LIFETIME
        self.expires_at = time.time() + self.LIFETIME

    def active(self):
        return time.monotonic() < self.until

    def consume(self, code):
        with self.lock:
            now = time.monotonic()
            self.attempts = [t for t in self.attempts if now - t < 60]
            if len(self.attempts) >= 10:
                raise ActionError('rate_limited', 'Too many attempts. Wait one minute.', 429)
            self.attempts.append(now)
            if now >= self.until or not secrets.compare_digest(str(code), self.code):
                raise ActionError('bad_code', 'Incorrect or expired code. Use the code shown on the PC.', 403)
            self.rotate()  # Single-use codes.


@functools.lru_cache(maxsize=16)
def qr_rows(url):
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)  # Only the device address: never a token or pairing code.
    qr.make(fit=True)
    return [''.join('1' if cell else '0' for cell in row) for row in qr.get_matrix()]


class Context:
    """Everything the request handler needs; built by lantern.app or by tests."""

    def __init__(self, data_dir, store, engine, devices, settings, *, maison=None, autostart=None,
                 updates=None, show_window=None, open_logs=None, addresses=network.addresses, web_dir=None):
        self.data_dir, self.store, self.engine = data_dir, store, engine
        self.devices, self.settings, self.maison = devices, settings, maison
        self.autostart, self.updates = autostart, updates
        self.show_window, self.open_logs = show_window, open_logs
        self.addresses = addresses
        self.web_dir = web_dir or (storage.resource_dir() / 'web')
        self.admin = secrets.token_urlsafe(32)
        self.pairing = Pairing()
        self.stopping = threading.Event()
        self.port = 0
        self.last_test = storage.read_json(data_dir / 'studio-test-latest.json')
        self._hosts = (0.0, frozenset())

    def allowed_hosts(self, refresh=False):
        stamp, hosts = self._hosts
        if refresh or time.monotonic() - stamp > 10 or not hosts:
            names = ['localhost', '127.0.0.1'] + [a['ip'] for a in self.addresses()]
            hosts = frozenset(f'{name}:{self.port}' for name in names)
            self._hosts = (time.monotonic(), hosts)
        return hosts

    def state(self, admin, device):
        buttons = self.store.config['buttons']
        shown = buttons if admin else [
            {k: b[k] for k in ('id', 'label', 'icon', 'color', 'action', 'confirm')} for b in buttons if usable(b)]
        data = {'version': VERSION, 'admin': admin, 'device': device['name'] if device else None,
                'buttons': shown, **self.engine.public_state()}
        if not admin:
            return data
        now = time.time()
        data.update(
            pairing={'code': self.pairing.code if self.pairing.active() else None,
                     'expires_at': self.pairing.expires_at},
            devices=[d | {'online': now - d['last_seen'] < ONLINE_WINDOW} for d in self.devices.public()],
            settings=self.settings.public(),
            maison=self.maison.status() if self.maison else None,
            network=[a | {'url': f'http://{a["ip"]}:{self.port}/', 'qr': qr_rows(f'http://{a["ip"]}:{self.port}/')}
                     for a in self.addresses()],
            history=list(self.engine.history),
            autostart={'available': self.autostart is not None,
                       'enabled': bool(self.autostart and self.autostart.enabled())},
            update=self.updates.result if self.updates else None,
            last_test=self.last_test)
        return data


class Handler(BaseHTTPRequestHandler):
    server_version = f'LanternDeck/{VERSION}'
    sys_version = ''

    def log_message(self, *_):
        pass  # Never log request lines: URLs can carry the admin token fragment's page.

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    @property
    def ctx(self):
        return self.server.ctx

    def headers_for(self, status, mime, length=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        if length is not None:
            self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', CSP)
        self.end_headers()

    def reply(self, status, data, mime='application/json'):
        raw = json.dumps(data).encode() if mime == 'application/json' else data
        self.headers_for(status, mime, len(raw))
        self.wfile.write(raw)

    def guard(self):
        host = self.headers.get('Host', '')
        if host not in self.ctx.allowed_hosts() and host not in self.ctx.allowed_hosts(refresh=True):
            self.reply(403, {'error': 'Unrecognized host; use an address shown in the control center'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + host:
            self.reply(403, {'error': 'Cross-origin request blocked'})
            return False
        return True

    def loopback(self):
        return ipaddress.ip_address(self.client_address[0]).is_loopback

    def identity(self):
        """Return (admin, device). Admin requires loopback and the per-launch token."""
        token = self.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        if not token:
            return False, None
        if self.loopback() and secrets.compare_digest(token, self.ctx.admin):
            return True, None
        return False, self.ctx.devices.find(token)

    def do_GET(self):
        if not self.guard():
            return
        path = self.path.split('?', 1)[0]
        if path in STATIC:
            name, mime = STATIC[path]
            return self.reply(200, (self.ctx.web_dir / name).read_bytes(), mime)
        admin, device = self.identity()
        if not (admin or device):
            return self.reply(401, {'error': 'Pair this device first', 'code': 'unpaired'})
        if path == '/api/state':
            return self.reply(200, self.ctx.state(admin, device))
        if path == '/api/events':
            return self.stream(admin, device)
        if admin and path == '/api/export':
            return self.reply(200, self.ctx.store.config)
        if admin and path == '/api/diagnostics':
            from lantern.diagnostics import report
            return self.reply(200, report(self.ctx))
        self.reply(404, {'error': 'Not found'})

    def stream(self, admin, device):
        """Server-sent events over a fetch() stream (the token stays in a header, not the URL)."""
        self.headers_for(200, 'text/event-stream; charset=utf-8')
        token = self.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        last, last_write, version = None, 0.0, -1
        try:
            while not self.ctx.stopping.is_set():
                if device is not None and self.ctx.devices.find(token) is None:
                    self.wfile.write(b'event: revoked\ndata: {}\n\n')
                    self.wfile.flush()
                    return
                payload = json.dumps(self.ctx.state(admin, device), sort_keys=True)
                now = time.monotonic()
                if payload != last:
                    self.wfile.write(b'data: ' + payload.encode() + b'\n\n')
                    last, last_write = payload, now
                elif now - last_write > STREAM_PING:
                    self.wfile.write(b': ping\n\n')
                    last_write = now
                self.wfile.flush()
                version = self.ctx.engine.bus.wait(version, 1.0)
        except OSError:
            pass  # The browser went away.

    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 65536 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ValueError('Expected a small JSON request')
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError('Expected an object')
        return body

    def do_POST(self):
        if not self.guard():
            return
        try:
            body = self.body()
            path = self.path
            ctx = self.ctx
            if path == '/api/local/show':
                if not self.loopback() or not self.headers.get('Host', '').startswith(('127.0.0.1:', 'localhost:')):
                    return self.reply(403, {'error': 'Local only'})
                if ctx.show_window:
                    ctx.show_window()
                return self.reply(200, {'ok': True})
            if path == '/api/pair':
                ctx.pairing.consume(body.get('code', ''))
                token = ctx.devices.add(body.get('name'))
                log.info('Paired a new device')
                ctx.engine.bus.notify()
                return self.reply(200, {'token': token})
            admin, device = self.identity()
            if not (admin or device):
                return self.reply(401, {'error': 'Pair this device first', 'code': 'unpaired'})
            if path == '/api/press':
                source = 'pc' if admin else 'phone:' + device['name']
                return self.reply(200, ctx.engine.press(body.get('id'), source, body.get('confirmed') is True,
                                                        body.get('target')))
            if path == '/api/forget-me' and device:
                ctx.devices.revoke(device['id'])
                return self.reply(200, {'ok': True})
            if not admin:
                return self.reply(403, {'error': 'Use the control center on the PC for this'})
            return self.reply(200, self.admin_post(path, body))
        except ActionError as exc:
            self.reply(exc.status, {'error': str(exc), 'code': exc.code})
        except StudioError as exc:
            self.reply(502, {'error': str(exc), 'code': exc.code})
        except OverflowError as exc:
            self.reply(409, {'error': str(exc), 'code': 'limit'})
        except (ValueError, TypeError) as exc:
            self.reply(400, {'error': str(exc) or 'Invalid data', 'code': 'invalid'})
        except (OSError, RuntimeError) as exc:
            log.warning('Request %s failed: %s', self.path, exc)
            self.reply(500, {'error': 'Operation failed: ' + str(exc), 'code': 'failed'})

    def admin_post(self, path, body):
        ctx = self.ctx
        if path == '/api/config':
            ctx.store.save(body)
        elif path == '/api/profile':
            if body.get('name') not in PROFILES:
                raise ValueError('Unknown profile')
            ctx.engine.set_control(False)
            ctx.store.save(profile(body['name']), make_backup=True)
        elif path == '/api/import':
            ctx.engine.set_control(False)
            ctx.store.save(body.get('config'), make_backup=True)
        elif path == '/api/pair-code':
            ctx.pairing.rotate()
            ctx.engine.bus.notify()
        elif path == '/api/devices/revoke':
            ident = body.get('id')
            ctx.devices.revoke(None if body.get('all') is True else str(ident))
            ctx.pairing.rotate()
            ctx.engine.bus.notify()
        elif path == '/api/control':
            if type(body.get('enabled')) is not bool:
                raise ValueError('Expected enabled')
            ctx.engine.set_control(body['enabled'])
        elif path == '/api/settings':
            changes = body.get('settings')
            if isinstance(changes, dict) and 'control_enabled' in changes:
                raise ValueError('Use the Live control switch')
            ctx.settings.update(changes)
            if 'remember_control' in changes:
                ctx.settings.update({'control_enabled': ctx.engine.control})
            ctx.engine.bus.notify()
        elif path == '/api/autostart':
            if ctx.autostart is None:
                raise OSError('Start with Windows is not available')
            ctx.autostart.set(body.get('enabled') is True)
            ctx.engine.bus.notify()
        elif path == '/api/maison/pair':
            if ctx.maison is None:
                raise OSError('Maison is not available')
            ctx.maison.pair(str(body.get('code', '')).strip())
        elif path == '/api/maison/forget':
            if ctx.maison:
                ctx.maison.forget()
        elif path == '/api/studio-test':
            scenes = [b['action']['scene'] for b in ctx.store.config['buttons']
                      if b['action']['kind'] == 'scene' and b['action']['scene']]
            with ctx.engine.lock:
                result = run_studio_test(ctx.engine.studio, scenes or None)
            storage.write_json(ctx.data_dir / 'studio-test-latest.json', result)
            ctx.last_test = result
            log.info('Studio test finished: %s', 'passed' if result['ok'] else 'failed')
            ctx.engine.bus.notify()
            return result
        elif path == '/api/open-logs':
            if ctx.open_logs:
                ctx.open_logs()
        else:
            raise ActionError('not_found', 'Not found', 404)
        return {'ok': True}


def serve(ctx, host='0.0.0.0', port=8765):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.ctx = ctx
    ctx.port = server.server_port
    thread = threading.Thread(target=server.serve_forever, name='http', daemon=True)
    thread.start()
    return server, thread


def stop(ctx, server):
    ctx.stopping.set()
    ctx.engine.bus.notify()
    server.shutdown()
    server.server_close()
