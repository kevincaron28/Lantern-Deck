"""Independent, version-sensitive adapter to LIVE Studio's local controller channel.

Only scene selection and the two audio controls are exposed. No broadcast start/stop,
recording, shell, arbitrary plugin action or keyboard input is available here.
"""
import json
import logging
import secrets
import threading
import time

import psutil
import websocket

log = logging.getLogger(__name__)

PROCESS_PREFIX = 'tiktok live studio'
SUBPROTOCOL = 'streamdeck_ttls_v1'
# Ports observed in earlier LIVE Studio releases are tried first; any other port the
# studio process listens on locally is probed afterwards, so an update that moves the
# controller does not silently break the connection.
KNOWN_PORTS = (28189, 39728, 34246, 42205, 38534, 40825, 40622)
LOCAL_BINDS = ('127.0.0.1', '0.0.0.0', '::1', '::')
MAX_PROBE_PORTS = 24
STALE_AFTER = 6
SYNC_EVERY = 2
RECONNECT_DELAY = 3

ERROR_MESSAGES = {
    'studio_offline': 'LIVE Studio is not connected. Open its main studio screen on this PC.',
    'state_unverified': 'Could not read LIVE Studio state. No action was sent.',
    'scene_missing': 'That scene does not exist in LIVE Studio. Choose a scene in the deck editor.',
    'unsupported': 'Only scene, microphone and desktop-sound controls are supported.',
    'busy': 'Another studio action is still running.',
    'rejected': 'LIVE Studio refused this action.',
    'unconfirmed': 'LIVE Studio did not confirm the action. Check the studio; nothing was retried.',
}


class StudioError(RuntimeError):
    def __init__(self, code, message=None):
        super().__init__(message or ERROR_MESSAGES.get(code, code))
        self.code = code


def studio_processes():
    found = []
    for proc in psutil.process_iter(['name']):
        if (proc.info.get('name') or '').lower().startswith(PROCESS_PREFIX):
            found.append(proc)
    return found


def listening_ports(processes=None):
    """Local TCP ports the LIVE Studio processes listen on, known controller ports first."""
    known, other = set(), set()
    for proc in studio_processes() if processes is None else processes:
        try:
            connections = proc.net_connections(kind='tcp')
        except psutil.Error:
            continue
        for conn in connections:
            if conn.status == psutil.CONN_LISTEN and conn.laddr.ip in LOCAL_BINDS:
                (known if conn.laddr.port in KNOWN_PORTS else other).add(conn.laddr.port)
    return sorted(known) + sorted(other - known)[:MAX_PROBE_PORTS]


def normalize_state(raw):
    """Keep only the typed fields we understand; reject anything ambiguous."""
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError('Studio state is not an object')
    for key in ('mic_mute', 'audio_mute'):
        if type(data.get(key)) is not bool:
            raise ValueError(f'Unsupported audio state field {key}')
    if type(data.get('stream_status')) is not int or data['stream_status'] not in (0, 1, 2):
        raise ValueError('Unsupported stream_status value')
    scene, rows = data.get('scene'), data.get('scene_list')
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
    return {'mic_mute': data['mic_mute'], 'audio_mute': data['audio_mute'],
            'stream_status': data['stream_status'], 'scene': scene, 'scenes': names}


def action_for(command, state):
    """Translate an allowlisted command into (studio action, settings, state field, target)."""
    if not isinstance(command, dict):
        raise StudioError('unsupported')
    kind = command.get('action')
    if kind == 'scene':
        scene = command.get('scene')
        if scene not in state['scenes']:
            raise StudioError('scene_missing')
        return 'scene', {'scene': scene}, 'scene', scene
    if kind in ('mic', 'audio') and type(command.get('muted')) is bool:
        return kind, {}, kind + '_mute', command['muted']
    raise StudioError('unsupported')


def is_live(state):
    # Assumption to confirm with the in-app studio test: 0 = not broadcasting.
    return bool(state) and state['stream_status'] != 0


class OfflineStudio:
    """Stand-in used by tests and the packaged self-test; never connects to anything."""

    def __init__(self):
        self.listeners = []

    def snapshot(self):
        return {'connected': False, 'error': ERROR_MESSAGES['studio_offline'], 'state': None, 'port': None}

    def diagnostics(self):
        return {'running': False, 'ports': [], 'port': None, 'detail': 'Offline stand-in'}

    def add_listener(self, listener):
        self.listeners.append(listener)

    def execute(self, command):
        raise StudioError('studio_offline')

    def close(self):
        pass


class StudioClient:
    def __init__(self, port_provider=listening_ports, connect=websocket.create_connection, start=True):
        self.port_provider = port_provider
        self.connect = connect
        self.stop_event = threading.Event()
        self.changed = threading.Condition()
        self.command_lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.socket = None
        self.data = None
        self.updated = 0
        self.sequence = 0
        self.results = {}
        self.port = None
        self.preferred = None
        self.ports_seen = []
        self.detail = 'Not started'
        self.error = ERROR_MESSAGES['studio_offline']
        self.listeners = []
        self.thread = threading.Thread(target=self._run, name='studio', daemon=True)
        if start:
            self.thread.start()

    def add_listener(self, listener):
        self.listeners.append(listener)

    def _notify(self):
        for listener in list(self.listeners):
            try:
                listener()
            except Exception:  # A broken listener must not stop the studio connection.
                log.exception('Studio listener failed')

    def snapshot(self):
        with self.changed:
            ready = self.data is not None and self.socket is not None \
                and time.monotonic() - self.updated < STALE_AFTER
            return {'connected': ready, 'error': None if ready else self.error,
                    'state': dict(self.data) if ready else None, 'port': self.port if ready else None}

    def diagnostics(self):
        return {'running': bool(studio_processes()), 'ports': list(self.ports_seen),
                'port': self.port, 'detail': self.detail}

    def emit(self, name, payload=None):
        packet = [f'stream_deck/{name}']
        if payload is not None:
            packet.append(json.dumps(payload))
        sock = self.socket
        if sock is None:
            raise StudioError('studio_offline')
        with self.send_lock:
            sock.send('42' + json.dumps(packet))

    def _open(self):
        ports = self.port_provider()
        self.ports_seen = ports
        if self.preferred in ports:
            ports = [self.preferred] + [p for p in ports if p != self.preferred]
        if not ports:
            self.detail = 'No LIVE Studio process with a local listener was found'
            return None, None
        failures = []
        for port in ports:
            sock = None
            try:
                sock = self.connect(f'ws://127.0.0.1:{port}/socket.io/?EIO=4&transport=websocket',
                                    timeout=2, subprotocols=[SUBPROTOCOL], suppress_origin=True)
                if not sock.recv().startswith('0'):
                    raise ValueError('unexpected Engine.IO handshake')
                sock.send('40')
                if not sock.recv().startswith('40'):
                    raise ValueError('controller namespace rejected')
                return sock, port
            except (OSError, ValueError, websocket.WebSocketException) as exc:
                failures.append(f'{port}: {type(exc).__name__}')
                if sock:
                    sock.close()
        self.detail = 'Controller handshake failed on ' + ', '.join(failures)
        return None, None

    def _run(self):
        while not self.stop_event.is_set():
            sock = None
            try:
                sock, port = self._open()
                if sock is None:
                    raise StudioError('studio_offline')
                with self.changed:
                    self.socket, self.port, self.preferred = sock, port, port
                self.detail = f'Connected on port {port}'
                log.info('LIVE Studio controller connected on port %s', port)
                sock.settimeout(.5)
                self.emit('join_room')  # Once per connection: repeated joins duplicate handlers.
                last_sync = 0
                while not self.stop_event.is_set():
                    if time.monotonic() - last_sync >= SYNC_EVERY:
                        self.emit('sync_settings')
                        last_sync = time.monotonic()
                    try:
                        packet = sock.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not packet:
                        raise StudioError('studio_offline', 'LIVE Studio closed the connection')
                    if packet == '2':
                        with self.send_lock:
                            sock.send('3')
                    elif packet.startswith('42'):
                        self._handle(json.loads(packet[2:]))
            except (OSError, ValueError, StudioError, websocket.WebSocketException) as exc:
                if self.socket is not None:
                    log.warning('LIVE Studio controller lost: %s', exc)
                    self.detail = f'Disconnected: {exc}'
                self.error = 'LIVE Studio unavailable. Open its main studio screen; this version may not expose controls.'
            finally:
                with self.changed:
                    was_connected = self.data is not None
                    self.socket, self.data, self.updated, self.port = None, None, 0, None
                    self.changed.notify_all()
                if sock:
                    sock.close()
                if was_connected:
                    self._notify()
            self.stop_event.wait(RECONNECT_DELAY)

    def _handle(self, event):
        if not isinstance(event, list) or len(event) < 2:
            return
        changed = False
        with self.changed:
            if event[0] == 'stream_deck/sync_settings':
                data = normalize_state(event[1])
                changed = data != self.data
                if self.data is None or data['stream_status'] != self.data['stream_status']:
                    # Recorded so the meaning of stream_status can be checked from the log.
                    log.info('Studio state: %d scenes, stream_status=%s', len(data['scenes']), data['stream_status'])
                self.data = data
                self.updated = time.monotonic()
                self.sequence += 1
                self.error = 'Studio state is stale; waiting for LIVE Studio.'
            elif event[0] in self.results:
                self.results[event[0]] = json.loads(event[1]) if isinstance(event[1], str) else event[1]
            self.changed.notify_all()
        if changed:
            self._notify()

    def execute(self, command):
        """Run one command with a fresh state read before and a verified state after.

        Returns the new snapshot plus 'changed'. A target that is already reached is
        not sent again, so a toggle can never flip twice. Nothing is ever retried.
        """
        if not self.command_lock.acquire(blocking=False):
            raise StudioError('busy')
        context = 'lantern_' + secrets.token_hex(12)
        event = 'stream_deck/' + context
        try:
            with self.changed:
                version = self.sequence
                self.emit('sync_settings')
                if not self.changed.wait_for(lambda: self.sequence > version or self.socket is None, timeout=3):
                    raise StudioError('state_unverified')
                snap = self.snapshot()
                if not snap['connected']:
                    raise StudioError('studio_offline')
                kind, settings, field, expected = action_for(command, snap['state'])
                if snap['state'][field] == expected:
                    return snap | {'changed': False}
                self.results[event] = None
                version = self.sequence
                self.emit('action_emit', {'action': 'com.tiktok.livestudio.' + kind,
                                          'context': context, 'payload': {'settings': settings}})
                if not self.changed.wait_for(lambda: self.results.get(event) is not None or self.socket is None,
                                             timeout=3):
                    raise StudioError('unconfirmed')
                result = self.results.get(event)
                if not isinstance(result, dict) or result.get('code') != 0:
                    raise StudioError('rejected')
                self.emit('sync_settings')
                verified = self.changed.wait_for(
                    lambda: self.socket is None or (self.sequence > version and self.data is not None
                                                    and self.data[field] == expected), timeout=3)
                if not verified or self.socket is None:
                    raise StudioError('unconfirmed', 'Action accepted but the new state was not confirmed. Check LIVE Studio.')
            log.info('Studio action %s -> %r confirmed', kind, expected)
            self._notify()
            return self.snapshot() | {'changed': True}
        finally:
            with self.changed:
                self.results.pop(event, None)
            self.command_lock.release()

    def close(self):
        self.stop_event.set()
        if self.socket:
            self.socket.close()
        if self.thread.is_alive():
            self.thread.join(timeout=3)
