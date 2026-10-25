"""Hotkey grammar, deck validation, settings, devices, storage, logging, updates and autostart."""
import json
import logging
from pathlib import Path
import tempfile
import unittest

from lantern import VERSION, dpapi, storage
from lantern.deck import DeckStore, defaults, profile, usable, validate
from lantern.desktop import RUN_VALUE, Autostart, tray_image
from lantern.devices import MAX_DEVICES, Devices, clean_name
from lantern.hotkeys import key_events, shortcut
from lantern.log import RedactingFilter, redact
from lantern.settings import Settings
from lantern.updates import compare, parse_version


class TempDir(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()


class HotkeyTests(unittest.TestCase):
    def test_rejects_unsafe_or_ambiguous_shortcuts(self):
        for bad in ('Win+R', 'Ctrl+A+B', 'Ctrl+Ctrl+A', 'A', 'Ctrl+;whoami', 'Alt+$(calc)', 42,
                    'Ctrl+LeftCtrl+A', 'LeftAlt+RightAlt+A', 'F25'):
            with self.assertRaises(ValueError):
                shortcut(bad)

    def test_normalizes_aliases_and_sides(self):
        self.assertEqual(shortcut(' ctrl + shift + f12 '), 'CTRL+SHIFT+F12')
        for typed in ('Left Alt', 'LAlt', 'left-alt', 'left_alt'):
            self.assertEqual(shortcut(typed), 'LEFTALT')
        self.assertEqual(shortcut('Right Control+F24'), 'RIGHTCTRL+F24')
        self.assertEqual(shortcut(''), '')

    def test_scan_codes_and_release_order(self):
        self.assertEqual(key_events('LeftAlt')[1], [(0, 0x38, 8), (0, 0x38, 10)])
        self.assertEqual(key_events('RightAlt+M')[1], [(0, 0x38, 9), (77, 0, 0), (77, 0, 2), (0, 0x38, 11)])
        self.assertEqual(key_events('Ctrl+Up')[1][1], (0x26, 0, 1))


class DeckTests(TempDir):
    def test_v2_configs_still_load_as_hotkeys(self):
        old = {'buttons': [{'id': 'b0', 'label': 'Mic', 'icon': '♫', 'color': '#ffffff', 'shortcut': 'ctrl+m'}]}
        button = validate(old)['buttons'][0]
        self.assertEqual(button['action'], {'kind': 'hotkey'})
        self.assertEqual(button['shortcut'], 'CTRL+M')
        self.assertFalse(button['fallback'])

    def test_actions_are_allowlisted(self):
        base = defaults()
        for action in ({'kind': 'shell'}, {'kind': 'scene', 'scene': 'x' * 201}, 'scene'):
            config = json.loads(json.dumps(base))
            config['buttons'][0]['action'] = action
            with self.assertRaises(ValueError):
                validate(config)

    def test_multi_step_validation(self):
        config = defaults()
        steps = [{'kind': 'scene', 'scene': ' BRB '}, {'kind': 'wait', 'ms': 500}, {'kind': 'mic', 'muted': True}]
        config['buttons'][0]['action'] = {'kind': 'macro', 'steps': steps}
        action = validate(config)['buttons'][0]['action']
        self.assertEqual(action['steps'][0], {'kind': 'scene', 'scene': 'BRB'})
        self.assertTrue(usable(validate(config)['buttons'][0]))
        bad_steps = [[], [{'kind': 'wait', 'ms': 500}], [{'kind': 'scene', 'scene': ''}], [{'kind': 'mic', 'muted': 'yes'}],
                     [{'kind': 'mic', 'muted': True}, {'kind': 'wait', 'ms': 50}], [{'kind': 'hotkey', 'shortcut': 'Alt+F4'}],
                     [{'kind': 'mic', 'muted': True}] * 9, [{'kind': 'mic', 'muted': True}] + [{'kind': 'wait', 'ms': 5000}] * 3]
        for bad in bad_steps:
            config['buttons'][0]['action'] = {'kind': 'macro', 'steps': bad}
            with self.assertRaises(ValueError, msg=bad):
                validate(config)

    def test_invalid_buttons_rejected(self):
        for change in ({'id': 'gaming'}, {'color': 'red'}, {'label': ''}, {'icon': 'x' * 13}):
            config = defaults()
            config['buttons'][0].update(change)
            with self.assertRaises(ValueError):
                validate(config)
        with self.assertRaises(ValueError):
            validate({'buttons': []})

    def test_profiles_and_usability(self):
        direct = profile('direct')['buttons']
        self.assertEqual([b['action']['kind'] for b in direct], ['scene'] * 4 + ['mic', 'audio'])
        self.assertFalse(usable(direct[0]))  # Scene not chosen yet.
        self.assertTrue(usable(direct[4]))
        self.assertTrue(all(b['action']['kind'] == 'hotkey' for b in profile('hotkeys')['buttons']))
        self.assertEqual(len(profile('audio')['buttons']), 2)
        with self.assertRaises(ValueError):
            profile('nope')

    def test_store_persists_atomically_with_backups(self):
        store = DeckStore(self.dir / 'deck.json')
        store.save(profile('hotkeys'))
        store.save(profile('direct'), make_backup=True)
        self.assertEqual(DeckStore(self.dir / 'deck.json').config, profile('direct'))
        self.assertEqual(len(list(self.dir.glob('deck-backup-*.json'))), 1)
        with self.assertRaises(ValueError):
            store.save({'buttons': 'x'})
        self.assertEqual(store.config, profile('direct'))
        self.assertFalse(list(self.dir.glob('*.tmp')))

    def test_backups_are_pruned(self):
        path = self.dir / 'deck.json'
        storage.write_json(path, {'a': 1})
        for _ in range(storage.MAX_BACKUPS + 3):
            storage.backup(path)
        self.assertEqual(len(list(self.dir.glob('deck-backup-*.json'))), storage.MAX_BACKUPS)


class SettingsAndDevicesTests(TempDir):
    def test_settings_types_and_persistence(self):
        settings = Settings(self.dir / 'settings.json')
        self.assertFalse(settings['remember_control'])
        settings.update({'remember_control': True})
        self.assertTrue(Settings(self.dir / 'settings.json')['remember_control'])
        for bad in ({'remember_control': 'yes'}, {'unknown': True}, {}, None):
            with self.assertRaises(ValueError):
                settings.update(bad)
        storage.write_json(self.dir / 'settings.json', {'check_updates': 'no', 'extra': 1})
        self.assertTrue(Settings(self.dir / 'settings.json')['check_updates'])

    def test_devices_store_hashes_and_survive_restart(self):
        devices = Devices(self.dir / 'devices.json')
        token = devices.add('  Kitchen   tablet ')
        self.assertNotIn(token, (self.dir / 'devices.json').read_text())
        reopened = Devices(self.dir / 'devices.json')
        found = reopened.find(token)
        self.assertEqual(found['name'], 'Kitchen tablet')
        self.assertIsNone(reopened.find('wrong'))
        self.assertIsNone(reopened.find(''))
        reopened.revoke(found['id'])
        self.assertIsNone(Devices(self.dir / 'devices.json').find(token))

    def test_device_limit_and_names(self):
        devices = Devices(self.dir / 'devices.json')
        for _ in range(MAX_DEVICES):
            devices.add('x')
        with self.assertRaises(OverflowError):
            devices.add('x')
        self.assertEqual(devices.revoke(), MAX_DEVICES)
        self.assertEqual(clean_name('\x00bad'), 'Phone')
        self.assertEqual(clean_name(None), 'Phone')
        self.assertEqual(len(clean_name('n' * 90)), 40)


class SecurityTests(unittest.TestCase):
    def test_dpapi_round_trip_and_tamper(self):
        sealed = dpapi.protect(b'secret')
        self.assertNotIn(b'secret', sealed)
        self.assertEqual(dpapi.unprotect(sealed), b'secret')
        with self.assertRaises(OSError):
            dpapi.unprotect(sealed[:-4] + b'xxxx')

    def test_log_redaction(self):
        token = 'a' * 64
        text = redact(f'Bearer abc.def admin=xyz {token} "token": "q" ' + 'Z' * 45)
        for secret in ('abc.def', 'xyz', token, 'Z' * 45):
            self.assertNotIn(secret, text)
        record = logging.LogRecord('x', logging.INFO, '', 0, 'pair %s', (token,), None)
        RedactingFilter().filter(record)
        self.assertNotIn(token, record.getMessage())


class UpdateTests(unittest.TestCase):
    def test_single_version_source(self):
        package = json.loads((Path(__file__).resolve().parent.parent / 'package.json').read_text(encoding='utf-8'))
        self.assertEqual(package['version'], VERSION)

    def test_version_comparison(self):
        self.assertEqual(parse_version('v3.10.2'), (3, 10, 2))
        self.assertEqual(parse_version('Release 4.1'), (4, 1, 0))
        self.assertIsNone(parse_version('latest'))
        newer = compare({'tag_name': 'v99.0.0', 'html_url': 'https://github.com/kevincaron28/Lantern-Deck/releases/tag/v99.0.0'})
        self.assertTrue(newer['available'])
        self.assertFalse(compare({'tag_name': 'v' + VERSION})['available'])
        self.assertTrue(compare({'tag_name': 'v99', 'html_url': 'https://evil.example'})['url'].startswith('https://github.com/'))


class FakeRegistry:
    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = 'HKCU', 2, 1

    def __init__(self):
        self.values = {}

    def OpenKey(self, *args):  # noqa: N802 - mirrors winreg
        registry = self

        class Key:
            def __enter__(self):
                return registry

            def __exit__(self, *exc):
                return False
        return Key()

    def QueryValueEx(self, _key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], 1

    def SetValueEx(self, _key, name, _reserved, _kind, value):  # noqa: N802
        self.values[name] = value

    def DeleteValue(self, _key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class DesktopTests(unittest.TestCase):
    def test_autostart_round_trip(self):
        registry = FakeRegistry()
        autostart = Autostart('"Lantern Deck.exe" --background', registry)
        self.assertFalse(autostart.enabled())
        self.assertTrue(autostart.set(True))
        self.assertEqual(registry.values[RUN_VALUE], '"Lantern Deck.exe" --background')
        self.assertFalse(autostart.set(False))
        self.assertFalse(autostart.set(False))

    def test_tray_image(self):
        on, off = tray_image(True), tray_image(False)
        self.assertEqual(on.size, (64, 64))
        self.assertNotEqual(on.tobytes(), off.tobytes())


if __name__ == '__main__':
    unittest.main()
