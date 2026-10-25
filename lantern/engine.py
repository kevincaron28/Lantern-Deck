"""One action engine for every surface: phones, the control center and Maison Panel."""
from collections import deque
import logging
import threading
import time

from lantern.hotkeys import send_keys
from lantern.studio import StudioError, is_live

log = logging.getLogger(__name__)
COOLDOWN = .35


class ActionError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


class Bus:
    """Wakes event streams when something visible changes."""

    def __init__(self):
        self.condition = threading.Condition()
        self.version = 0
        self.listeners = []

    def notify(self):
        with self.condition:
            self.version += 1
            self.condition.notify_all()
        for listener in list(self.listeners):
            try:
                listener()
            except Exception:  # The tray must never break an action.
                log.exception('Bus listener failed')

    def wait(self, version, timeout):
        with self.condition:
            self.condition.wait_for(lambda: self.version != version, timeout=timeout)
            return self.version


class Engine:
    def __init__(self, store, studio, settings, sender=send_keys):
        self.store, self.studio, self.settings, self.sender = store, studio, settings, sender
        self.bus = Bus()
        self.bus_listeners = self.bus.listeners
        self.lock = threading.Lock()
        self.last = 0
        self.history = deque(maxlen=25)
        self._control = bool(settings['remember_control'] and settings['control_enabled'])
        self.live_since = None
        self.sleep = time.sleep
        studio.add_listener(self._studio_changed)
        store.listeners.append(self.bus.notify)

    @property
    def control(self):
        return self._control

    def set_control(self, enabled):
        self._control = bool(enabled)
        if self.settings['remember_control']:
            self.settings.update({'control_enabled': self._control})
        log.info('Live control %s', 'ON' if self._control else 'OFF')
        self.bus.notify()

    def _track_live(self, live):
        """Remember when the broadcast started so surfaces can show a LIVE timer."""
        if live and self.live_since is None:
            self.live_since = time.time()
            log.info('Broadcast detected as LIVE')
        elif not live and self.live_since is not None:
            self.live_since = None
            log.info('Broadcast no longer LIVE')

    def _studio_changed(self):
        self._track_live(is_live(self.studio.snapshot()['state']))
        self.bus.notify()

    def studio_state(self):
        snap = self.studio.snapshot()
        state = snap['state'] or {}
        live = is_live(snap['state'])
        self._track_live(live)
        return {'connected': snap['connected'], 'message': snap['error'],
                'scene': state.get('scene'), 'scenes': state.get('scenes', []),
                'mic_muted': state.get('mic_mute'), 'audio_muted': state.get('audio_mute'),
                'stream_status': state.get('stream_status'), 'live': live, 'live_since': self.live_since}

    def public_state(self):
        return {'control': self.control, 'studio': self.studio_state()}

    def _record(self, source, label, ok, message):
        self.history.appendleft({'time': time.time(), 'source': source, 'label': label, 'ok': ok, 'message': message})
        self.bus.notify()

    def _cooldown(self):
        now = time.monotonic()
        if now - self.last < COOLDOWN:
            raise ActionError('cooldown', 'Please wait before pressing again', 429)
        self.last = now

    def press(self, ident, source='pc', confirmed=False, target=None):
        """Run a saved button. Requests can only name a button; they never supply actions."""
        button = self.store.button(ident)
        if button is None:
            raise ActionError('unknown_button', 'This button no longer exists. Refresh the deck.')
        with self.lock:
            try:
                result = self._press(button, confirmed, target)
            except (ActionError, StudioError, RuntimeError, OSError) as exc:
                self._record(source, button['label'], False, str(exc))
                raise
            self._record(source, button['label'], True, result['message'])
            return result

    def _press(self, button, confirmed, target):
        action, kind = button['action'], button['action']['kind']
        if button['confirm'] and not confirmed:
            raise ActionError('confirm', 'Confirm this action first', 409)
        if kind == 'hotkey':
            if not button['shortcut']:
                raise ActionError('unassigned', 'Assign a shortcut to this button in the control center')
            self._cooldown()
            if not self.control:
                return {'ok': True, 'code': 'rehearsed', 'message': 'Rehearsed: ' + button['label']}
            self.sender(button['shortcut'])
            return {'ok': True, 'code': 'keys_sent', 'message': 'Keys sent: ' + button['label']}
        if kind == 'scene' and not action['scene'] and not (button['fallback'] and button['shortcut']):
            raise ActionError('unassigned', 'Choose a LIVE Studio scene for this button in the control center')
        if target is not None and type(target) is not bool:
            raise ActionError('invalid', 'Invalid target state')
        self._cooldown()
        studio = self.studio.snapshot()
        changes_scene = kind == 'scene' or (kind == 'macro' and any(s['kind'] == 'scene' for s in action['steps']))
        if self.control and changes_scene and studio['connected'] and is_live(studio['state']) \
                and self.settings['confirm_when_live'] and not confirmed:
            raise ActionError('confirm_live', 'You are LIVE. Confirm this scene change.', 409)
        if not self.control:
            return {'ok': True, 'code': 'rehearsed', 'message': 'Rehearsed: ' + button['label']}
        if not studio['connected']:
            if kind != 'macro' and button['fallback'] and button['shortcut']:
                self.sender(button['shortcut'])
                return {'ok': True, 'code': 'keys_sent',
                        'message': 'Studio offline · shortcut sent: ' + button['label']}
            raise ActionError('studio_offline', studio['error'] or 'LIVE Studio is not connected', 503)
        if kind == 'macro':
            return self._macro(button)
        if kind == 'scene':
            command = {'action': 'scene', 'scene': action['scene']}
        else:
            current = studio['state'][kind + '_mute']
            command = {'action': kind, 'muted': (not current) if target is None else target}
        snap = self.studio.execute(command)
        return {'ok': True, 'code': 'done' if snap['changed'] else 'already',
                'message': describe(button['label'], command, snap['changed'])}

    def _macro(self, button):
        """Run steps in order. Stops at the first failure; earlier steps stay applied."""
        steps = button['action']['steps']
        changed = False
        for number, step in enumerate(steps, 1):
            if step['kind'] == 'wait':
                self.sleep(step['ms'] / 1000)
                continue
            command = {'action': step['kind']} | ({'scene': step['scene']} if step['kind'] == 'scene'
                                                    else {'muted': step['muted']})
            try:
                changed = self.studio.execute(command)['changed'] or changed
            except StudioError as exc:
                raise ActionError('macro_failed', f'{button["label"]}: step {number} of {len(steps)} failed ({exc}). '
                                  'Earlier steps stayed applied.', 502) from exc
        return {'ok': True, 'code': 'done' if changed else 'already',
                'message': f'{button["label"]}: {len(steps)} steps done' + ('' if changed else ' (already)')}

    def command(self, command, source='maison'):
        """Allowlisted command from Maison Panel (scene / mic / audio)."""
        label = 'Maison ' + str(command.get('action') if isinstance(command, dict) else '?')
        if not self.control:
            raise ActionError('control_disabled', 'Live control is OFF on the PC', 403)
        with self.lock:
            try:
                snap = self.studio.execute(command)
            except (StudioError, RuntimeError, OSError) as exc:
                self._record(source, label, False, str(exc))
                raise
            self._record(source, label, True, describe(label, command, snap['changed']))
            return snap


def describe(label, command, changed):
    if command['action'] == 'scene':
        text = f'Scene: {command["scene"]}'
    else:
        text = f'{label}: {"muted" if command["muted"] else "unmuted"}'
    return text if changed else text + ' (already)'


def run_studio_test(studio, settings_scenes=None):
    """Guided, reversible check against the real LIVE Studio (Phase 0 verification).

    Switches to each scene, toggles mic and desktop sound, verifies each step and
    restores the original scene and mute states. Refuses to run while broadcasting.
    """
    steps = []

    def step(name, command):
        started = time.monotonic()
        try:
            snap = studio.execute(command)
            steps.append({'step': name, 'ok': True, 'ms': round((time.monotonic() - started) * 1000)})
            return snap
        except (StudioError, RuntimeError, OSError) as exc:
            steps.append({'step': name, 'ok': False, 'error': str(exc),
                          'code': getattr(exc, 'code', 'error')})
            return None

    snap = studio.snapshot()
    if not snap['connected']:
        raise ActionError('studio_offline', snap['error'] or 'LIVE Studio is not connected', 503)
    original = snap['state']
    if is_live(original):
        raise ActionError('live', 'Stop broadcasting before running the studio test.', 409)
    scenes = [s for s in (settings_scenes or original['scenes']) if s in original['scenes']][:6]
    for scene in scenes:
        step(f'Switch to scene "{scene}"', {'action': 'scene', 'scene': scene})
    for kind, name in (('mic', 'Microphone'), ('audio', 'Desktop sound')):
        step(f'{name} {"unmute" if original[kind + "_mute"] else "mute"}',
             {'action': kind, 'muted': not original[kind + '_mute']})
        step(f'{name} restore', {'action': kind, 'muted': original[kind + '_mute']})
    if scenes:
        step(f'Restore scene "{original["scene"]}"', {'action': 'scene', 'scene': original['scene']})
    return {'ok': all(s['ok'] for s in steps) and bool(steps), 'time': time.time(),
            'port': snap.get('port'), 'scenes': original['scenes'], 'steps': steps}
