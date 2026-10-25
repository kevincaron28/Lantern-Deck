"""User preferences saved in settings.json."""
import threading

from lantern import storage

DEFAULTS = {
    'remember_control': False,   # Restore Live control after a restart instead of starting OFF.
    'control_enabled': False,    # Last Live control state; only used when remember_control is on.
    'confirm_when_live': True,   # Phones must confirm scene changes while broadcasting.
    'check_updates': True,       # Ask GitHub once per launch whether a newer release exists.
}


class Settings:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        raw = storage.read_json(path, {})
        self.values = dict(DEFAULTS)
        if isinstance(raw, dict):
            self.values.update({k: v for k, v in raw.items() if k in DEFAULTS and type(v) is bool})

    def __getitem__(self, key):
        return self.values[key]

    def update(self, changes):
        if not isinstance(changes, dict) or not changes:
            raise ValueError('Expected settings')
        for key, value in changes.items():
            if key not in DEFAULTS or type(value) is not bool:
                raise ValueError('Unknown setting: ' + str(key))
        with self.lock:
            self.values.update(changes)
            storage.write_json(self.path, self.values)
        return dict(self.values)

    def public(self):
        return {k: v for k, v in self.values.items() if k != 'control_enabled'}
