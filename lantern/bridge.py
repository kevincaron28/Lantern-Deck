"""Outbound authenticated bridge to the owner's Maison Panel. No LAN listener."""
import base64
from collections import deque
import json
import logging
import os
from pathlib import Path
import socket
import threading
import time
import urllib.request

import websocket

from lantern import VERSION, dpapi, storage
from lantern.deck import usable
from lantern.engine import ActionError
from lantern.studio import StudioError

log = logging.getLogger(__name__)
ORIGIN = os.environ.get('LANTERN_MAISON_ORIGIN', 'https://maison-panel.kcaron.workers.dev')
USER_AGENT = f'LanternDeck/{VERSION}'
TOKEN_CHARS = set('0123456789abcdef')


def valid_token(token):
    return isinstance(token, str) and len(token) == 64 and set(token) <= TOKEN_CHARS


def save_token(path, token, protect=dpapi.protect):
    if not valid_token(token):
        raise ValueError('Invalid pairing response')
    sealed = base64.b64encode(protect(token.encode())).decode()
    storage.write_json(path, {'version': 2, 'dpapi': sealed})


def load_token(path, protect=dpapi.protect, unprotect=dpapi.unprotect):
    """Read the credential; a version 2.0 plaintext file is re-saved encrypted."""
    data = storage.read_json(path)
    if not isinstance(data, dict):
        raise ValueError('Not paired')
    if 'dpapi' in data:
        token = unprotect(base64.b64decode(data['dpapi'])).decode()
    else:
        token = data.get('token')
        if valid_token(token):
            save_token(path, token, protect)
            log.info('Upgraded the Maison credential to DPAPI encryption')
    if not valid_token(token):
        raise ValueError('Invalid credential')
    return token


def enroll(path, code, origin=ORIGIN, opener=urllib.request.urlopen):
    if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdigit():
        raise ValueError('Enter the eight-digit code displayed in Maison > Deck.')
    request = urllib.request.Request(origin + '/api/deck/enroll', data=json.dumps({'code': code}).encode(),
                                     headers={'Content-Type': 'application/json', 'User-Agent': USER_AGENT})
    with opener(request, timeout=15) as response:
        data = json.load(response)
    save_token(path, data.get('token', ''))


def reason_for(exc):
    return getattr(exc, 'code', 'error')


class MaisonBridge:
    def __init__(self, path, engine, origin=ORIGIN, connect=websocket.create_connection, start=True):
        self.path = Path(path)
        self.engine = engine
        self.origin = origin
        self.connect = connect
        self.stop_event = threading.Event()
        self.socket = None
        self.state = 'connecting'
        self.message = 'Connecting to Maison Panel…'
        self.seen = deque(maxlen=256)
        self.send_lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name='maison', daemon=True)
        if start:
            self.thread.start()

    def snapshot(self):
        # `deck` lets Maison show the buttons configured in Lantern Deck (3.1+), including multi-step ones.
        deck = [{k: b[k] for k in ('id', 'label', 'icon', 'color', 'action', 'confirm')}
                for b in self.engine.store.config['buttons'] if usable(b)]
        return self.engine.studio.snapshot() | {'enabled': self.engine.control, 'computer': socket.gethostname(),
                                                'deck': deck}

    def handle(self, message):
        """Answer one relay message. 'error' keeps the 2.0 codes; 'reason' adds the specific cause."""
        if not isinstance(message, dict) or not isinstance(message.get('id'), str):
            raise ValueError('Invalid relay message')
        ident = message['id']
        if len(ident) > 80:
            raise ValueError('Invalid message ID')
        if message.get('type') == 'state':
            return {'id': ident, 'snapshot': self.snapshot()}
        if message.get('type') != 'action':
            raise ValueError('Unsupported relay message')
        if ident in self.seen:
            return {'id': ident, 'ok': False, 'error': 'duplicate_command', 'reason': 'duplicate_command'}
        self.seen.append(ident)
        if not self.engine.control:
            return {'id': ident, 'ok': False, 'error': 'control_disabled', 'reason': 'control_disabled',
                    'message': 'Live control is OFF on the PC'}
        expires = message.get('expires')
        if type(expires) not in (int, float) or not 0 < expires - time.time() * 1000 <= 10000:
            return {'id': ident, 'ok': False, 'error': 'command_expired', 'reason': 'command_expired'}
        command = message.get('command')
        try:
            if isinstance(command, dict) and command.get('action') == 'press':
                # A saved Lantern button, run exactly like a phone press (multi-step, LIVE confirmation...).
                target = command.get('target')
                result = self.engine.press(str(command.get('button', ''))[:40], 'maison', command.get('confirmed') is True,
                                           target if type(target) is bool else None)
                return {'id': ident, 'ok': True, 'result': {'code': result['code'], 'message': result['message']},
                        'snapshot': self.snapshot()}
            self.engine.command(command)
            return {'id': ident, 'ok': True, 'snapshot': self.snapshot()}
        except (ActionError, StudioError, ValueError, RuntimeError, OSError, websocket.WebSocketException) as exc:
            return {'id': ident, 'ok': False, 'error': 'action_unconfirmed', 'reason': reason_for(exc),
                    'message': str(exc)}

    def _send(self, ws, reply):
        with self.send_lock:
            ws.send(json.dumps(reply))

    def _answer(self, ws, request):
        try:
            reply = self.handle(request)
        except ValueError:
            return
        try:
            self._send(ws, reply)
        except (OSError, websocket.WebSocketException):
            log.warning('Could not deliver an action reply to Maison')

    def _run(self):
        while not self.stop_event.is_set():
            ws = None
            try:
                token = load_token(self.path)
                ws = self.connect(self.origin.replace('https:', 'wss:') + '/api/deck/publisher',
                                  header={'Authorization': 'Bearer ' + token, 'User-Agent': USER_AGENT},
                                  timeout=15, suppress_origin=True)
                self.socket = ws
                ws.settimeout(1)
                self.state, self.message = 'connected', 'Maison connected.'
                log.info('Maison relay connected')
                self.engine.bus.notify()
                last_ping = time.monotonic()
                while not self.stop_event.is_set():
                    if time.monotonic() - last_ping > 20:
                        with self.send_lock:
                            ws.send('ping')
                        last_ping = time.monotonic()
                    try:
                        message = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not message:
                        raise RuntimeError('Disconnected')
                    if message == 'pong' or not isinstance(message, str) or len(message) > 4096:
                        continue
                    request = json.loads(message)
                    if isinstance(request, dict) and request.get('type') == 'action':
                        # Actions (multi-step ones can take seconds) run aside so state polls keep answering.
                        threading.Thread(target=self._answer, args=(ws, request), name='maison-action', daemon=True).start()
                    else:
                        self._send(ws, self.handle(request))
            except websocket.WebSocketBadStatusException as exc:
                code = getattr(exc, 'status_code', None)
                if code in (401, 403):
                    self.state, self.message = 'revoked', 'Maison no longer accepts this PC. Pair again from Maison > Deck.'
                else:
                    self.state, self.message = 'offline', 'Maison is unreachable. Check the Internet connection.'
                log.warning('Maison relay refused the connection (HTTP %s)', code)
            except (OSError, ValueError, KeyError, RuntimeError, websocket.WebSocketException) as exc:
                if self.state == 'connected':
                    log.warning('Maison relay disconnected: %s', type(exc).__name__)
                self.state, self.message = 'offline', 'Maison disconnected. Check the Internet connection.'
            finally:
                self.socket = None
                if ws:
                    ws.close()
                self.engine.bus.notify()
            self.stop_event.wait(5)

    def close(self):
        self.stop_event.set()
        if self.socket:
            self.socket.close()
        if self.thread.is_alive():
            self.thread.join(timeout=3)


class MaisonLink:
    """Pairing, forgetting and status for the one Maison connection of this PC."""

    def __init__(self, data_dir, engine, origin=ORIGIN, enroll_fn=enroll, bridge_factory=MaisonBridge):
        self.path = Path(data_dir) / 'maison-connection.json'
        self.engine, self.origin = engine, origin
        self.enroll_fn, self.bridge_factory = enroll_fn, bridge_factory
        self.bridge = None
        self.lock = threading.Lock()
        self.pairing = False

    def start(self):
        if self.path.exists() and self.bridge is None:
            self.bridge = self.bridge_factory(self.path, self.engine, self.origin)

    def pair(self, code):
        with self.lock:
            if self.pairing:
                raise ActionError('busy', 'Pairing is already in progress', 409)
            self.pairing = True
        try:
            self.enroll_fn(self.path, code, self.origin)
        except ValueError:
            raise
        except OSError as exc:
            log.warning('Maison pairing failed: %s', type(exc).__name__)
            raise ActionError('pair_failed', 'Pairing failed. Generate a new code in Maison > Deck and try again.', 502) from exc
        finally:
            self.pairing = False
        self._restart()

    def _restart(self):
        if self.bridge:
            self.bridge.close()
        self.bridge = None
        self.start()
        self.engine.bus.notify()

    def forget(self):
        if self.bridge:
            self.bridge.close()
        self.bridge = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        self.engine.bus.notify()

    def status(self):
        if self.bridge is None:
            return {'paired': False, 'state': 'unpaired', 'message': 'Not connected to Maison.', 'origin': self.origin}
        return {'paired': True, 'state': self.bridge.state, 'message': self.bridge.message, 'origin': self.origin}

    def close(self):
        if self.bridge:
            self.bridge.close()
