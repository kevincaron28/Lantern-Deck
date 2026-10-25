"""Deck configuration: validation, ready-made profiles and the saved deck file."""
import re
import threading

from lantern import storage
from lantern.hotkeys import shortcut

MAX_BUTTONS = 32
# hotkey = send a keyboard shortcut; the others talk to LIVE Studio directly.
ACTION_KINDS = ('hotkey', 'scene', 'mic', 'audio')
DIRECT_KINDS = ('scene', 'mic', 'audio')


def validate_action(raw):
    if raw is None:
        return {'kind': 'hotkey'}  # Configurations from versions 1 and 2.
    if not isinstance(raw, dict) or raw.get('kind', 'hotkey') not in ACTION_KINDS:
        raise ValueError('Unknown button action')
    kind = raw.get('kind', 'hotkey')
    if kind == 'scene':
        scene = raw.get('scene', '')
        if not isinstance(scene, str) or len(scene.strip()) > 200:
            raise ValueError('Scene names are limited to 200 characters')
        return {'kind': 'scene', 'scene': scene.strip()}
    return {'kind': kind}


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get('buttons'), list) \
            or not 1 <= len(data['buttons']) <= MAX_BUTTONS:
        raise ValueError(f'Use 1–{MAX_BUTTONS} buttons')
    buttons, ids = [], set()
    for b in data['buttons']:
        if not isinstance(b, dict):
            raise ValueError('Invalid button')
        ident = b.get('id', '')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', ident) or ident in ids:
            raise ValueError('Button IDs must be unique')
        ids.add(ident)
        label, icon, color = b.get('label'), b.get('icon'), b.get('color')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 40 \
                or not isinstance(icon, str) or len(icon) > 12:
            raise ValueError('Use a label of 1–40 characters and a short icon')
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Invalid color')
        buttons.append({'id': ident, 'label': label.strip(), 'icon': icon, 'color': color,
                        'action': validate_action(b.get('action')),
                        'shortcut': shortcut(b.get('shortcut', '')),
                        'fallback': b.get('fallback') is True,
                        'confirm': b.get('confirm') is True})
    return {'buttons': buttons}


def usable(button):
    """Whether a button can do anything; phones only show usable buttons."""
    action = button['action']
    if action['kind'] == 'hotkey':
        return bool(button['shortcut'])
    if action['kind'] == 'scene':
        return bool(action['scene']) or (button['fallback'] and bool(button['shortcut']))
    return True


STUDIO_ROWS = [
    ('starting', 'Starting', '01', '#80a7ff', {'kind': 'scene', 'scene': ''}, '1'),
    ('gaming', 'Main gaming', '02', '#4dd9b1', {'kind': 'scene', 'scene': ''}, '2'),
    ('brb', 'BRB', '03', '#d3acff', {'kind': 'scene', 'scene': ''}, '3'),
    ('ending', 'Ending', '04', '#ff8f9e', {'kind': 'scene', 'scene': ''}, '4'),
    ('microphone', 'Microphone', '♫', '#f4b66c', {'kind': 'mic'}, 'M'),
    ('desktop-audio', 'Desktop sound', '♪', '#7dd4e8', {'kind': 'audio'}, 'D'),
]
PROFILES = ('direct', 'hotkeys', 'audio')


def profile(name='direct'):
    """direct: talks to LIVE Studio; hotkeys: matching Ctrl+Shift shortcuts; audio: two hotkeys."""
    if name not in PROFILES:
        raise ValueError('Unknown profile')
    rows = STUDIO_ROWS[-2:] if name == 'audio' else STUDIO_ROWS
    buttons = []
    for ident, label, icon, color, action, key in rows:
        buttons.append({'id': ident, 'label': label, 'icon': icon, 'color': color,
                        'action': action if name == 'direct' else {'kind': 'hotkey'},
                        'shortcut': 'CTRL+SHIFT+' + key, 'fallback': False, 'confirm': False})
    return validate({'buttons': buttons})


def defaults():
    return profile('direct')


class DeckStore:
    """The saved deck (deck.json) with a lock; every save is validated and atomic."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        raw = storage.read_json(path)
        self.config = validate(raw) if raw is not None else defaults()
        self.listeners = []

    def save(self, config, make_backup=False):
        config = validate(config)
        with self.lock:
            if make_backup:
                storage.backup(self.path)
            storage.write_json(self.path, config)
            self.config = config
        for listener in self.listeners:
            listener()
        return config

    def button(self, ident):
        return next((b for b in self.config['buttons'] if b['id'] == ident), None)
