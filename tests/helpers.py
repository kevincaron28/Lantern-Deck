"""Shared fakes: a scriptable studio and an in-memory runtime on a free port."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time

from lantern.deck import DeckStore
from lantern.devices import Devices
from lantern.engine import Engine
from lantern.server import Context, serve, stop
from lantern.settings import Settings
from lantern.studio import StudioClient, normalize_state

RAW = {'mic_mute': False, 'audio_mute': False, 'stream_status': 0, 'scene': 'Gaming',
       'scene_list': [{'name': 'Starting'}, {'name': 'Gaming'}, {'name': 'BRB'}], 'private_extra': 'never forward'}


def fake_studio(raw=None):
    """A StudioClient whose transport is replaced by an in-process studio."""
    client = StudioClient(start=False)
    client.data = normalize_state(raw or RAW)
    client.updated = time.monotonic()
    client.sequence = 1
    client.socket = object()
    client.sent = []

    def emit(name, payload=None):
        client.sent.append((name, payload))
        with client.changed:
            if name == 'sync_settings':
                client.sequence += 1
                client.updated = time.monotonic()
            if name == 'action_emit':
                action = payload['action'].split('.')[-1]
                if action == 'scene':
                    client.data['scene'] = payload['payload']['settings']['scene']
                else:
                    client.data[action + '_mute'] = not client.data[action + '_mute']
                client.results['stream_deck/' + payload['context']] = {'code': 0}
            client.changed.notify_all()
    client.emit = emit
    return client


class Harness:
    def __init__(self, studio=None):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.sent = []
        self.studio = studio or fake_studio()
        self.settings = Settings(self.dir / 'settings.json')
        self.store = DeckStore(self.dir / 'deck.json')
        self.engine = Engine(self.store, self.studio, self.settings, self.sent.append)
        self.devices = Devices(self.dir / 'devices.json')
        self.ctx = Context(self.dir, self.store, self.engine, self.devices, self.settings,
                           addresses=lambda: [{'ip': '192.168.50.2', 'adapter': 'Test', 'preferred': True}])
        self.server, self.thread = serve(self.ctx, '127.0.0.1', 0)
        self.port = self.ctx.port

    def close(self):
        stop(self.ctx, self.server)
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, path, body=None, token='', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        sent = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}
        sent.update(headers or {})
        conn.request('GET' if body is None else 'POST', path, None if body is None else json.dumps(body), sent)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, json.loads(raw) if raw.startswith(b'{') or raw.startswith(b'[') else raw

    def admin(self, path, body=None):
        return self.request(path, body, self.ctx.admin)

    def pair(self, name='Phone'):
        status, data = self.request('/api/pair', {'code': self.ctx.pairing.code, 'name': name})
        assert status == 200, data
        return data['token']


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.02)
    return False


__all__ = ['RAW', 'fake_studio', 'Harness', 'wait_for', 'threading']
