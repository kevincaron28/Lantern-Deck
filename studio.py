"""Independent, version-sensitive adapter to LIVE Studio's local control channel.

Only scene selection and the two audio controls are exposed. No broadcast,
recording, shell, arbitrary plugin action, or keyboard fallback is available.
"""
import json
import secrets
import threading
import time

import psutil
import websocket

PORTS = {28189, 39728, 34246, 42205, 38534, 40825, 40622}


def studio_ports():
    ports = set()
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] != 'TikTok LIVE Studio.exe':
            continue
        try:
            for conn in proc.net_connections(kind='tcp'):
                if conn.status == 'LISTEN' and conn.laddr.port in PORTS:
                    ports.add(conn.laddr.port)
        except psutil.Error:
            continue
    return sorted(ports)


def normalize_state(raw):
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError('Invalid studio state')
    for key in ('mic_mute', 'audio_mute'):
        if type(data.get(key)) is not bool:
            raise ValueError('Unsupported audio state')
    if type(data.get('stream_status')) is not int or data['stream_status'] not in (0, 1, 2):
        raise ValueError('Unsupported stream state')
    scene = data.get('scene')
    rows = data.get('scene_list')
    if not isinstance(scene, str) or not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('Unsupported scene state')
    names = []
    for row in rows:
        name = row.get('name') if isinstance(row, dict) else None
        if not isinstance(name, str) or not 1 <= len(name) <= 200:
            raise ValueError('Unsupported scene name')
        if name in names:
            raise ValueError('Duplicate scene names are ambiguous')
        names.append(name)
    return {key: data[key] for key in ('mic_mute', 'audio_mute', 'stream_status')} | {'scene': scene, 'scenes': names}


def action_for(command, state):
    if not isinstance(command, dict):
        raise ValueError('Invalid command')
    kind = command.get('action')
    if kind == 'scene':
        scene = command.get('scene')
        if scene not in state['scenes']:
            raise ValueError('Select an available LIVE Studio scene')
        return 'scene', {'scene': scene}, 'scene', scene
    if kind in ('mic', 'audio') and type(command.get('muted')) is bool:
        return kind, {}, kind + '_mute', command['muted']
    raise ValueError('Only scene and audio controls are supported')


class StudioClient:
    def __init__(self, port_provider=studio_ports):
        self.port_provider = port_provider
        self.stop_event = threading.Event()
        self.changed = threading.Condition()
        self.command_lock = threading.Lock()
        self.socket = None
        self.data = None
        self.updated = 0
        self.sequence = 0
        self.results = {}
        self.error = 'Open LIVE Studio on this PC.'
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def snapshot(self):
        with self.changed:
            ready = self.data is not None and time.monotonic() - self.updated < 6 and self.socket is not None
            return {'connected': ready, 'error': None if ready else self.error,
                    'state': dict(self.data) if ready else None}

    def emit(self, name, payload=None):
        packet = [f'stream_deck/{name}']
        if payload is not None:
            packet.append(json.dumps(payload))
        sock = self.socket
        if sock is None:
            raise RuntimeError('LIVE Studio is disconnected')
        sock.send('42' + json.dumps(packet))

    def _run(self):
        while not self.stop_event.is_set():
            sock = None
            try:
                for port in self.port_provider():
                    try:
                        sock = websocket.create_connection(
                            f'ws://127.0.0.1:{port}/socket.io/?EIO=4&transport=websocket',
                            timeout=2, subprotocols=['streamdeck_ttls_v1'], suppress_origin=True)
                        if not sock.recv().startswith('0'):
                            raise ValueError('Unsupported handshake')
                        sock.send('40')
                        if not sock.recv().startswith('40'):
                            raise ValueError('Studio rejected connection')
                        break
                    except (OSError, ValueError, websocket.WebSocketException):
                        if sock:
                            sock.close()
                        sock = None
                if sock is None:
                    raise RuntimeError('Open LIVE Studio on this PC. Its local controller is unavailable.')
                self.socket = sock
                sock.settimeout(.5)
                self.emit('join_room')  # Once per connection: repeated joins duplicate handlers.
                last_sync = 0
                while not self.stop_event.is_set():
                    if time.monotonic() - last_sync >= 2:
                        self.emit('sync_settings')
                        last_sync = time.monotonic()
                    try:
                        packet = sock.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not packet:
                        raise RuntimeError('LIVE Studio disconnected')
                    if packet == '2':
                        sock.send('3')
                    elif packet.startswith('42'):
                        event = json.loads(packet[2:])
                        if not isinstance(event, list) or len(event) < 2:
                            continue
                        with self.changed:
                            if event[0] == 'stream_deck/sync_settings':
                                self.data = normalize_state(event[1])
                                self.updated = time.monotonic()
                                self.sequence += 1
                                self.error = 'Studio state is stale; waiting for LIVE Studio.'
                            elif event[0] in self.results:
                                self.results[event[0]] = json.loads(event[1]) if isinstance(event[1], str) else event[1]
                            self.changed.notify_all()
            except (OSError, ValueError, RuntimeError, websocket.WebSocketException):
                self.error = 'LIVE Studio unavailable. Open its main studio screen; this version may not expose controls.'
            finally:
                with self.changed:
                    self.socket = None
                    self.data = None
                    self.updated = 0
                    self.changed.notify_all()
                if sock:
                    sock.close()
            self.stop_event.wait(3)

    def execute(self, command):
        if not self.command_lock.acquire(blocking=False):
            raise RuntimeError('Another studio action is pending')
        context = 'lantern_' + secrets.token_hex(12)
        event = 'stream_deck/' + context
        try:
            # Require a fresh round trip immediately before a toggle.
            with self.changed:
                version = self.sequence
                self.emit('sync_settings')
                if not self.changed.wait_for(lambda: self.sequence > version or self.socket is None, timeout=3):
                    raise RuntimeError('Cannot verify studio state')
                snap = self.snapshot()
                if not snap['connected']:
                    raise RuntimeError('LIVE Studio disconnected')
                kind, settings, field, expected = action_for(command, snap['state'])
                if snap['state'][field] == expected:
                    return snap  # Idempotent target already reached; do not toggle again.
                self.results[event] = None
                version = self.sequence
                self.emit('action_emit', {'action': 'com.tiktok.livestudio.'+kind,
                                         'context': context, 'payload': {'settings': settings}})
                if not self.changed.wait_for(lambda: self.results.get(event) is not None or self.socket is None, timeout=3):
                    raise RuntimeError('Delivery unconfirmed. Check LIVE Studio; no retry was sent.')
                result = self.results.get(event)
                if not isinstance(result, dict) or result.get('code') != 0:
                    raise RuntimeError('LIVE Studio did not accept this action')
                self.emit('sync_settings')
                verified = self.changed.wait_for(lambda: self.socket is None or
                    (self.sequence > version and self.data is not None and self.data[field] == expected), timeout=3)
                if not verified or self.socket is None:
                    raise RuntimeError('Action accepted but state unconfirmed. Check LIVE Studio.')
                return self.snapshot()
        finally:
            with self.changed:
                self.results.pop(event, None)
            self.command_lock.release()

    def close(self):
        self.stop_event.set()
        if self.socket:
            self.socket.close()
        self.thread.join(timeout=3)
