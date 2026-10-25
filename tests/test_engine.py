"""Studio adapter, action engine, studio self-test and Maison bridge."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from collections import namedtuple
from unittest import mock

import psutil

from lantern import bridge, storage
from lantern.deck import DeckStore, profile
from lantern.engine import ActionError, Engine, run_studio_test
from lantern.settings import Settings
from lantern.studio import KNOWN_PORTS, OfflineStudio, StudioError, action_for, is_live, listening_ports, normalize_state
from tests.helpers import RAW, fake_studio


class StudioTests(unittest.TestCase):
    def test_state_redaction_and_strict_types(self):
        state = normalize_state(json.dumps(RAW))
        self.assertNotIn('private_extra', state)
        self.assertEqual(state['scenes'], ['Starting', 'Gaming', 'BRB'])
        for key, value in [('mic_mute', 0), ('audio_mute', 'false'), ('stream_status', True), ('stream_status', 7),
                           ('scene_list', [{'name': 'x'}, {'name': 'x'}]), ('scene', None)]:
            with self.assertRaises(ValueError):
                normalize_state(RAW | {key: value})

    def test_allowlist_has_specific_codes(self):
        state = normalize_state(RAW)
        cases = [({'action': 'livestartend'}, 'unsupported'), ({'action': 'mic', 'muted': 'yes'}, 'unsupported'),
                 ({'action': 'scene', 'scene': 'unknown'}, 'scene_missing'), ('scene', 'unsupported')]
        for command, code in cases:
            with self.assertRaises(StudioError) as caught:
                action_for(command, state)
            self.assertEqual(caught.exception.code, code)

    def test_verified_mute_is_idempotent(self):
        client = fake_studio()
        result = client.execute({'action': 'mic', 'muted': True})
        self.assertTrue(result['state']['mic_mute'] and result['changed'])
        self.assertFalse(client.execute({'action': 'mic', 'muted': True})['changed'])
        self.assertEqual(sum(name == 'action_emit' for name, _ in client.sent), 1)
        self.assertFalse(client.data['audio_mute'])
        self.assertEqual(client.execute({'action': 'scene', 'scene': 'BRB'})['state']['scene'], 'BRB')

    def test_stale_or_rejected(self):
        client = fake_studio()
        client.updated -= 10
        self.assertFalse(client.snapshot()['connected'])
        self.assertIsNone(client.snapshot()['state'])
        client = fake_studio()
        original = client.emit

        def reject(name, payload=None):
            original(name, payload)
            if name == 'action_emit':
                client.results['stream_deck/' + payload['context']] = {'code': 5}
        client.emit = reject
        with self.assertRaises(StudioError) as caught:
            client.execute({'action': 'audio', 'muted': True})
        self.assertEqual(caught.exception.code, 'rejected')

    def test_busy_lock(self):
        client = fake_studio()
        client.command_lock.acquire()
        with self.assertRaises(StudioError) as caught:
            client.execute({'action': 'mic', 'muted': True})
        self.assertEqual(caught.exception.code, 'busy')

    def test_port_discovery_prefers_known_ports(self):
        Addr = namedtuple('Addr', 'ip port')
        Conn = namedtuple('Conn', 'status laddr')

        class Proc:
            def net_connections(self, kind):
                return [Conn(psutil.CONN_LISTEN, Addr('127.0.0.1', 50000)),
                        Conn(psutil.CONN_LISTEN, Addr('127.0.0.1', KNOWN_PORTS[1])),
                        Conn(psutil.CONN_LISTEN, Addr('192.168.1.5', 50001)),
                        Conn(psutil.CONN_ESTABLISHED, Addr('127.0.0.1', 50002))]

        class Denied:
            def net_connections(self, kind):
                raise psutil.AccessDenied()
        self.assertEqual(listening_ports([Proc(), Denied()]), [KNOWN_PORTS[1], 50000])

    def test_live_detection(self):
        self.assertFalse(is_live(None))
        self.assertFalse(is_live(normalize_state(RAW)))
        self.assertTrue(is_live(normalize_state(RAW | {'stream_status': 1})))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.sent = []
        self.studio = fake_studio()
        self.settings = Settings(self.dir / 'settings.json')
        self.store = DeckStore(self.dir / 'deck.json')
        config = profile('direct')
        for button, scene in zip(config['buttons'], ['Starting', 'Gaming', 'BRB', ''], strict=False):
            button['action']['scene'] = scene
        config['buttons'][3]['shortcut'] = 'CTRL+SHIFT+4'
        self.store.save(config)
        self.engine = Engine(self.store, self.studio, self.settings, self.sent.append)

    def tearDown(self):
        self.temp.cleanup()

    def press(self, ident, **kw):
        self.engine.last = 0
        return self.engine.press(ident, **kw)

    def test_rehearsal_never_touches_studio_or_keyboard(self):
        self.assertEqual(self.press('brb')['code'], 'rehearsed')
        self.assertEqual(self.press('microphone')['code'], 'rehearsed')
        self.assertEqual(self.studio.data['scene'], 'Gaming')
        self.assertFalse(any(name == 'action_emit' for name, _ in self.studio.sent))
        self.assertEqual(self.sent, [])

    def test_direct_scene_and_target_mute(self):
        self.engine.set_control(True)
        self.assertEqual(self.press('brb')['code'], 'done')
        self.assertEqual(self.studio.data['scene'], 'BRB')
        self.assertEqual(self.press('brb')['code'], 'already')
        self.assertEqual(self.press('microphone')['code'], 'done')
        self.assertTrue(self.studio.data['mic_mute'])
        # A phone that still shows "on" asks to mute again: no second toggle.
        self.assertEqual(self.press('microphone', target=True)['code'], 'already')
        self.assertTrue(self.studio.data['mic_mute'])
        with self.assertRaises(ActionError):
            self.press('microphone', target='on')

    def test_unassigned_unknown_and_cooldown(self):
        self.engine.set_control(True)
        with self.assertRaises(ActionError) as caught:
            self.press('nope')
        self.assertEqual(caught.exception.code, 'unknown_button')
        config = self.store.config
        config['buttons'][3]['shortcut'] = ''
        self.store.save(config)
        with self.assertRaises(ActionError) as caught:
            self.press('ending')
        self.assertEqual(caught.exception.code, 'unassigned')
        self.press('brb')
        with self.assertRaises(ActionError) as caught:
            self.engine.press('starting')
        self.assertEqual(caught.exception.code, 'cooldown')

    def test_live_guard_and_confirm(self):
        self.engine.set_control(True)
        self.studio.data['stream_status'] = 1
        with self.assertRaises(ActionError) as caught:
            self.press('brb')
        self.assertEqual((caught.exception.code, caught.exception.status), ('confirm_live', 409))
        self.assertEqual(self.press('brb', confirmed=True)['code'], 'done')
        self.assertEqual(self.press('microphone')['code'], 'done')  # Muting is never blocked while live.
        self.settings.update({'confirm_when_live': False})
        self.assertEqual(self.press('starting')['code'], 'done')
        config = self.store.config
        config['buttons'][0]['confirm'] = True
        self.store.save(config)
        with self.assertRaises(ActionError) as caught:
            self.press('starting')
        self.assertEqual(caught.exception.code, 'confirm')

    def test_offline_studio_and_hotkey_fallback(self):
        engine = Engine(self.store, OfflineStudio(), self.settings, self.sent.append)
        engine.set_control(True)
        with self.assertRaises(ActionError) as caught:
            engine.press('brb')
        self.assertEqual((caught.exception.code, caught.exception.status), ('studio_offline', 503))
        config = self.store.config
        config['buttons'][2]['fallback'] = True
        self.store.save(config)
        engine.last = 0
        self.assertEqual(engine.press('brb')['code'], 'keys_sent')
        self.assertEqual(self.sent, ['CTRL+SHIFT+3'])

    def test_hotkey_buttons(self):
        self.store.save(profile('hotkeys'))
        self.engine.set_control(True)
        self.assertEqual(self.press('brb')['code'], 'keys_sent')
        self.assertEqual(self.sent, ['CTRL+SHIFT+3'])

    def test_remember_control(self):
        self.settings.update({'remember_control': True})
        self.engine.set_control(True)
        self.assertTrue(Engine(self.store, self.studio, Settings(self.dir / 'settings.json')).control)
        self.settings.update({'remember_control': False})
        self.assertFalse(Engine(self.store, self.studio, Settings(self.dir / 'settings.json')).control)

    def test_history_and_maison_command(self):
        with self.assertRaises(ActionError) as caught:
            self.engine.command({'action': 'mic', 'muted': True})
        self.assertEqual(caught.exception.code, 'control_disabled')
        self.engine.set_control(True)
        self.engine.command({'action': 'audio', 'muted': True})
        self.assertTrue(self.studio.data['audio_mute'])
        self.press('brb', source='phone:Tablet')
        self.assertEqual(self.engine.history[0]['source'], 'phone:Tablet')
        self.assertEqual(self.engine.history[1]['source'], 'maison')

    def add_macro(self, steps, ident='macro'):
        config = self.store.config
        config['buttons'].append({'id': ident, 'label': 'BRB + mute', 'icon': '03', 'color': '#d3acff',
                                  'action': {'kind': 'macro', 'steps': steps}, 'shortcut': '', 'fallback': False,
                                  'confirm': False})
        self.store.save(config)

    def test_macro_runs_steps_in_order(self):
        waits = []
        self.engine.sleep = waits.append
        self.add_macro([{'kind': 'scene', 'scene': 'BRB'}, {'kind': 'wait', 'ms': 300}, {'kind': 'mic', 'muted': True}])
        self.assertEqual(self.press('macro')['code'], 'rehearsed')
        self.assertEqual(self.studio.data['scene'], 'Gaming')
        self.engine.set_control(True)
        self.assertEqual(self.press('macro')['code'], 'done')
        self.assertEqual((self.studio.data['scene'], self.studio.data['mic_mute']), ('BRB', True))
        self.assertEqual(waits, [.3])
        actions = [p['action'] for n, p in self.studio.sent if n == 'action_emit']
        self.assertEqual(actions, ['com.tiktok.livestudio.scene', 'com.tiktok.livestudio.mic'])
        self.assertEqual(self.press('macro')['code'], 'already')

    def test_macro_stops_at_first_failure(self):
        self.add_macro([{'kind': 'mic', 'muted': True}, {'kind': 'scene', 'scene': 'Deleted scene'},
                        {'kind': 'audio', 'muted': True}])
        self.engine.set_control(True)
        with self.assertRaises(ActionError) as caught:
            self.press('macro')
        self.assertEqual((caught.exception.code, caught.exception.status), ('macro_failed', 502))
        self.assertIn('step 2 of 3', str(caught.exception))
        self.assertTrue(self.studio.data['mic_mute'])
        self.assertFalse(self.studio.data['audio_mute'], 'later steps must not run')

    def test_macro_live_guard_and_offline(self):
        self.add_macro([{'kind': 'scene', 'scene': 'BRB'}, {'kind': 'mic', 'muted': True}])
        self.add_macro([{'kind': 'mic', 'muted': True}], 'muteonly')
        self.engine.set_control(True)
        self.studio.data['stream_status'] = 1
        with self.assertRaises(ActionError) as caught:
            self.press('macro')
        self.assertEqual(caught.exception.code, 'confirm_live')
        self.assertEqual(self.press('muteonly')['code'], 'done')
        offline = Engine(self.store, OfflineStudio(), self.settings, self.sent.append)
        offline.set_control(True)
        with self.assertRaises(ActionError) as caught:
            offline.press('macro')
        self.assertEqual(caught.exception.code, 'studio_offline')

    def test_live_timer_tracks_broadcast(self):
        self.assertIsNone(self.engine.studio_state()['live_since'])
        before = time.time()
        self.studio.data['stream_status'] = 1
        self.studio._notify()
        since = self.engine.studio_state()['live_since']
        self.assertGreaterEqual(since, before)
        self.assertEqual(self.engine.studio_state()['live_since'], since, 'start time is stable while LIVE')
        self.studio.data['stream_status'] = 0
        self.studio._notify()
        self.assertIsNone(self.engine.studio_state()['live_since'])

    def test_studio_test_restores_everything(self):
        report = run_studio_test(self.studio, ['BRB', 'Starting', 'Missing'])
        self.assertTrue(report['ok'])
        self.assertEqual(len(report['steps']), 7)
        self.assertEqual(self.studio.data['scene'], 'Gaming')
        self.assertFalse(self.studio.data['mic_mute'] or self.studio.data['audio_mute'])
        self.studio.data['stream_status'] = 1
        with self.assertRaises(ActionError):
            run_studio_test(self.studio)
        with self.assertRaises(ActionError):
            run_studio_test(OfflineStudio())


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.studio = fake_studio()
        self.engine = Engine(DeckStore(self.dir / 'deck.json'), self.studio, Settings(self.dir / 'settings.json'))
        self.bridge = bridge.MaisonBridge(self.dir / 'maison-connection.json', self.engine, start=False)

    def tearDown(self):
        self.temp.cleanup()

    def message(self, ident, **extra):
        return {'type': 'action', 'id': ident, 'command': {'action': 'audio', 'muted': True},
                'expires': time.time() * 1000 + 5000} | extra

    def test_rejects_disabled_expired_duplicate(self):
        self.assertEqual(self.bridge.handle(self.message('one'))['error'], 'control_disabled')
        self.engine.set_control(True)
        self.assertEqual(self.bridge.handle(self.message('one'))['error'], 'duplicate_command')
        self.assertEqual(self.bridge.handle(self.message('two', expires=0))['error'], 'command_expired')
        self.assertTrue(self.bridge.handle(self.message('three'))['ok'])
        self.assertTrue(self.studio.data['audio_mute'])
        self.assertFalse(self.studio.data['mic_mute'])

    def test_specific_reasons_keep_legacy_error(self):
        self.engine.set_control(True)
        reply = self.bridge.handle(self.message('x', command={'action': 'scene', 'scene': 'Nope'}))
        self.assertEqual((reply['error'], reply['reason']), ('action_unconfirmed', 'scene_missing'))
        state = self.bridge.handle({'type': 'state', 'id': 's'})
        self.assertTrue(state['snapshot']['enabled'] and state['snapshot']['connected'])
        for bad in ({'type': 'action'}, {'type': 'other', 'id': 'q'}, {'type': 'state', 'id': 'x' * 81}):
            with self.assertRaises(ValueError):
                self.bridge.handle(bad)

    def test_credentials_are_encrypted_and_migrated(self):
        path = self.dir / 'maison-connection.json'
        token = 'ab' * 32
        storage.write_json(path, {'token': token})  # Version 2.0 plaintext file.
        self.assertEqual(bridge.load_token(path), token)
        self.assertNotIn(token, path.read_text())
        self.assertEqual(bridge.load_token(path), token)
        with self.assertRaises(ValueError):
            bridge.save_token(path, 'short')

    def test_enroll_validates_code_and_response(self):
        path = self.dir / 'maison-connection.json'
        with self.assertRaises(ValueError):
            bridge.enroll(path, '1234')

        class Response:
            def __init__(self, data):
                self.data = json.dumps(data).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, *args):
                return self.data
        with self.assertRaises(ValueError):
            bridge.enroll(path, '12345678', opener=lambda *a, **k: Response({'token': 'nope'}))
        bridge.enroll(path, '12345678', opener=lambda *a, **k: Response({'token': 'cd' * 32}))
        self.assertEqual(bridge.load_token(path), 'cd' * 32)

    def test_link_pair_and_forget(self):
        made = []

        class FakeBridge:
            def __init__(self, path, engine, origin):
                self.state, self.message = 'connected', 'ok'
                made.append(self)

            def close(self):
                self.closed = True

        def fake_enroll(path, code, origin):
            if code != '12345678':
                raise OSError('refused')
            storage.write_json(path, {'v': 1})
        link = bridge.MaisonLink(self.dir, self.engine, enroll_fn=fake_enroll, bridge_factory=FakeBridge)
        self.assertFalse(link.status()['paired'])
        with self.assertRaises(ActionError):
            link.pair('00000000')
        link.pair('12345678')
        self.assertEqual(link.status()['state'], 'connected')
        link.forget()
        self.assertFalse(link.path.exists())
        self.assertTrue(made[0].closed)
        self.assertFalse(link.status()['paired'])

    def test_relay_refusal_marks_revoked(self):
        import websocket
        storage.write_json(self.dir / 'maison-connection.json', {'token': 'ef' * 32})

        def refuse(*args, **kwargs):
            raise websocket.WebSocketBadStatusException('refused', 401)
        live = bridge.MaisonBridge(self.dir / 'maison-connection.json', self.engine, connect=refuse, start=False)
        with mock.patch.object(live.stop_event, 'wait', side_effect=lambda _t: live.stop_event.set()):
            live._run()
        self.assertEqual(live.state, 'revoked')


if __name__ == '__main__':
    unittest.main()
