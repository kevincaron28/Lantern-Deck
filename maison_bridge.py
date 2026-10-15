"""Outbound authenticated bridge to the owner's Maison Panel. No LAN listener."""
import json
from pathlib import Path
import socket
import threading
import time
import urllib.request
from collections import deque

import websocket
from studio import StudioClient

ORIGIN = 'https://maison-panel.kcaron.workers.dev'


def enroll(path, code):
    if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdigit():
        raise ValueError('Enter the eight-digit code displayed in Maison > Deck.')
    request = urllib.request.Request(ORIGIN+'/api/deck/enroll',
        data=json.dumps({'code':code}).encode(), headers={'Content-Type':'application/json','User-Agent':'LanternDeck/2.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    token = data.get('token', '')
    if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Invalid pairing response')
    temp = Path(path).with_suffix('.tmp')
    temp.write_text(json.dumps({'token':token}), encoding='utf-8')
    temp.replace(path)


class MaisonBridge:
    def __init__(self, path, studio=None):
        self.path = Path(path)
        self.studio = studio or StudioClient()
        self.enabled = False
        self.stop_event = threading.Event()
        self.socket = None
        self.status = 'Connecting to Maison Panel…'
        self.seen = deque(maxlen=256)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def snapshot(self):
        return self.studio.snapshot() | {'enabled':self.enabled, 'computer':socket.gethostname()}

    def handle(self, message):
        if not isinstance(message, dict) or not isinstance(message.get('id'), str):
            raise ValueError('Invalid relay message')
        ident = message['id']
        if len(ident) > 80:
            raise ValueError('Invalid message ID')
        if message.get('type') == 'state':
            return {'id':ident, 'snapshot':self.snapshot()}
        if message.get('type') != 'action':
            raise ValueError('Unsupported relay message')
        if ident in self.seen:
            return {'id':ident, 'ok':False, 'error':'duplicate_command'}
        self.seen.append(ident)
        if not self.enabled:
            return {'id':ident, 'ok':False, 'error':'control_disabled'}
        expires = message.get('expires')
        if type(expires) not in (int, float) or not 0 < expires-time.time()*1000 <= 10000:
            return {'id':ident, 'ok':False, 'error':'command_expired'}
        try:
            self.studio.execute(message.get('command'))
            return {'id':ident, 'ok':True, 'snapshot':self.snapshot()}
        except (ValueError, RuntimeError, OSError, websocket.WebSocketException):
            return {'id':ident, 'ok':False, 'error':'action_unconfirmed'}

    def _run(self):
        while not self.stop_event.is_set():
            ws = None
            try:
                token = json.loads(self.path.read_text(encoding='utf-8'))['token']
                if not isinstance(token, str) or len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
                    raise ValueError('Invalid credential')
                ws = websocket.create_connection(ORIGIN.replace('https:', 'wss:')+'/api/deck/publisher',
                    header={'Authorization':'Bearer '+token,'User-Agent':'LanternDeck/2.0'}, timeout=15, suppress_origin=True)
                self.socket = ws
                ws.settimeout(1)
                self.status = 'Maison connected. Open its Deck tab.'
                last_ping = time.monotonic()
                while not self.stop_event.is_set():
                    if time.monotonic()-last_ping > 20:
                        ws.send('ping'); last_ping = time.monotonic()
                    try:
                        message = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not message:
                        raise RuntimeError('Disconnected')
                    if message == 'pong':
                        continue
                    if not isinstance(message, str) or len(message) > 4096:
                        continue
                    result = self.handle(json.loads(message))
                    ws.send(json.dumps(result))
            except (OSError, ValueError, KeyError, RuntimeError, websocket.WebSocketException):
                self.status = 'Maison disconnected. Check Internet or pair again in Maison > Deck.'
            finally:
                self.socket = None
                if ws:
                    ws.close()
            self.stop_event.wait(5)

    def close(self):
        self.enabled = False
        self.stop_event.set()
        if self.socket:
            self.socket.close()
        self.studio.close()
        self.thread.join(timeout=3)
