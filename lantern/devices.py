"""Paired phones and tablets. Only token hashes are stored, never the tokens."""
import hashlib
import secrets
import threading
import time

from lantern import storage

MAX_DEVICES = 16
SEEN_WRITE_INTERVAL = 60


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def clean_name(name):
    if not isinstance(name, str):
        return 'Phone'
    name = ' '.join(name.split())[:40]
    return name if name and name.isprintable() else 'Phone'


class Devices:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        raw = storage.read_json(path, [])
        self.items = [d for d in raw if isinstance(d, dict) and isinstance(d.get('hash'), str)] \
            if isinstance(raw, list) else []
        self.saved_at = time.time()

    def _save(self):
        storage.write_json(self.path, self.items)
        self.saved_at = time.time()

    def add(self, name):
        with self.lock:
            if len(self.items) >= MAX_DEVICES:
                raise OverflowError('Device limit reached; remove a device in the control center')
            token = secrets.token_urlsafe(32)
            now = time.time()
            self.items.append({'id': secrets.token_hex(6), 'name': clean_name(name), 'hash': _digest(token),
                               'created': now, 'last_seen': now})
            self._save()
            return token

    def find(self, token):
        if not token:
            return None
        digest = _digest(token)
        with self.lock:
            match = None
            for device in self.items:
                if secrets.compare_digest(device['hash'], digest):
                    match = device
            if match:
                match['last_seen'] = time.time()
                if time.time() - self.saved_at > SEEN_WRITE_INTERVAL:
                    self._save()
            return dict(match) if match else None

    def revoke(self, ident=None):
        """Revoke one device by id, or all of them when ident is None."""
        with self.lock:
            before = len(self.items)
            self.items = [] if ident is None else [d for d in self.items if d['id'] != ident]
            self._save()
            return before - len(self.items)

    def public(self):
        with self.lock:
            return [{k: d[k] for k in ('id', 'name', 'created', 'last_seen')} for d in self.items]
