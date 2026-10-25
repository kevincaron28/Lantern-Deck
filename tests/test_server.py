"""HTTP API, authentication boundaries and the live event stream."""
import http.client
import unittest

from lantern.deck import profile
from lantern.devices import Devices
from tests.helpers import Harness, wait_for


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def test_static_assets_and_routing(self):
        for path in ('/', '/control', '/app.js', '/control.js', '/client.js', '/i18n.js', '/shortcuts.js',
                     '/style.css', '/control.css', '/icon.svg'):
            self.assertEqual(self.h.request(path)[0], 200, path)
        self.assertEqual(self.h.request('/../lantern/server.py')[0], 401)
        self.assertEqual(self.h.request('/api/state')[0], 401)

    def test_host_and_origin_checks(self):
        self.assertEqual(self.h.request('/', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.h.admin('/api/state')[0], 200)
        status, _ = self.h.request('/api/state', token=self.h.ctx.admin, headers={'Origin': 'http://evil.example'})
        self.assertEqual(status, 403)
        self.assertEqual(self.h.request('/', headers={'Host': f'192.168.50.2:{self.h.port}'})[0], 200)

    def test_pairing_is_single_use_rate_limited_and_persistent(self):
        code = self.h.ctx.pairing.code
        token = self.h.pair('Kitchen tablet')
        self.assertEqual(self.h.request('/api/pair', {'code': code})[0], 403)
        status, data = self.h.request('/api/state', token=token)
        self.assertEqual(status, 200)
        self.assertFalse(data['admin'])
        self.assertEqual(data['device'], 'Kitchen tablet')
        self.assertNotIn('pairing', data)
        self.assertNotIn('devices', data)
        self.assertTrue(Devices(self.h.dir / 'devices.json').find(token))
        for _ in range(9):
            self.h.request('/api/pair', {'code': 'wrong'})
        self.assertEqual(self.h.request('/api/pair', {'code': self.h.ctx.pairing.code})[0], 429)

    def test_expired_code(self):
        self.h.ctx.pairing.until = 0
        self.assertEqual(self.h.request('/api/pair', {'code': self.h.ctx.pairing.code})[0], 403)

    def test_phones_cannot_manage(self):
        token = self.h.pair()
        for path, body in (('/api/config', profile('hotkeys')), ('/api/control', {'enabled': True}),
                           ('/api/pair-code', {}), ('/api/devices/revoke', {'all': True}),
                           ('/api/settings', {'settings': {'remember_control': True}}), ('/api/studio-test', {})):
            self.assertEqual(self.h.request(path, body, token)[0], 403, path)
        self.assertEqual(self.h.request('/api/export', token=token)[0], 404)
        self.assertEqual(self.h.request('/api/diagnostics', token=token)[0], 404)
        self.assertFalse(self.h.engine.control)

    def test_phone_sees_only_usable_buttons_without_shortcuts(self):
        token = self.h.pair()
        data = self.h.request('/api/state', token=token)[1]
        self.assertEqual([b['id'] for b in data['buttons']], ['microphone', 'desktop-audio'])
        self.assertNotIn('shortcut', data['buttons'][0])
        self.assertEqual(len(self.h.admin('/api/state')[1]['buttons']), 6)

    def test_press_rehearsal_then_live(self):
        token = self.h.pair()
        self.h.admin('/api/profile', {'name': 'hotkeys'})
        status, data = self.h.request('/api/press', {'id': 'brb', 'shortcut': 'Alt+F4'}, token)
        self.assertEqual((status, data['code']), (200, 'rehearsed'))
        self.assertEqual(self.h.sent, [])
        self.h.admin('/api/control', {'enabled': True})
        self.h.engine.last = 0
        self.assertEqual(self.h.request('/api/press', {'id': 'brb'}, token)[1]['code'], 'keys_sent')
        self.assertEqual(self.h.sent, ['CTRL+SHIFT+3'])
        self.assertEqual(self.h.request('/api/press', {'id': 'unknown', 'command': 'whoami'}, token)[0], 400)

    def test_live_confirmation_round_trip(self):
        config = profile('direct')
        config['buttons'][2]['action']['scene'] = 'BRB'
        self.h.admin('/api/config', config)
        self.h.admin('/api/control', {'enabled': True})
        self.h.studio.data['stream_status'] = 1
        token = self.h.pair()
        status, data = self.h.request('/api/press', {'id': 'brb'}, token)
        self.assertEqual((status, data['code']), (409, 'confirm_live'))
        self.h.engine.last = 0
        status, data = self.h.request('/api/press', {'id': 'brb', 'confirmed': True}, token)
        self.assertEqual((status, data['code']), (200, 'done'))
        self.assertEqual(self.h.studio.data['scene'], 'BRB')

    def test_profiles_backup_turn_control_off(self):
        self.h.admin('/api/control', {'enabled': True})
        self.assertEqual(self.h.admin('/api/profile', {'name': 'audio'})[0], 200)
        self.assertFalse(self.h.engine.control)
        self.assertEqual(len(self.h.admin('/api/export')[1]['buttons']), 2)
        self.assertEqual(self.h.admin('/api/profile', {'name': 'bad'})[0], 400)
        self.assertEqual(self.h.admin('/api/import', {'config': {'buttons': 'x'}})[0], 400)
        self.assertEqual(self.h.admin('/api/import', {'config': profile('hotkeys')})[0], 200)
        # The first save had no deck file to back up; the import backed up the audio deck.
        self.assertEqual(len(list(self.h.dir.glob('deck-backup-*.json'))), 1)

    def test_device_revocation_and_forget_me(self):
        first, second = self.h.pair('A'), self.h.pair('B')
        devices = self.h.admin('/api/state')[1]['devices']
        self.assertEqual([d['name'] for d in devices], ['A', 'B'])
        self.h.admin('/api/devices/revoke', {'id': devices[0]['id']})
        self.assertEqual(self.h.request('/api/state', token=first)[0], 401)
        self.assertEqual(self.h.request('/api/state', token=second)[0], 200)
        self.assertEqual(self.h.request('/api/forget-me', {}, second)[0], 200)
        self.assertEqual(self.h.request('/api/state', token=second)[0], 401)

    def test_settings_validation(self):
        self.assertEqual(self.h.admin('/api/settings', {'settings': {'remember_control': True}})[0], 200)
        self.assertEqual(self.h.admin('/api/settings', {'settings': {'control_enabled': True}})[0], 400)
        self.assertEqual(self.h.admin('/api/settings', {'settings': {'remember_control': 1}})[0], 400)
        self.assertEqual(self.h.admin('/api/control', {'enabled': 'yes'})[0], 400)
        self.assertEqual(self.h.admin('/api/autostart', {'enabled': True})[0], 500)

    def test_admin_state_and_diagnostics_have_no_secrets(self):
        token = self.h.pair()
        state = self.h.admin('/api/state')[1]
        self.assertEqual(state['network'][0]['url'], f'http://192.168.50.2:{self.h.port}/')
        self.assertTrue(state['network'][0]['qr'][0])
        report = self.h.admin('/api/diagnostics')[1]
        text = str(report)
        for secret in (self.h.ctx.admin, token, self.h.ctx.pairing.code):
            self.assertNotIn(secret, text)
        self.assertTrue(report['studio']['connected'])

    def test_studio_test_endpoint(self):
        status, report = self.h.admin('/api/studio-test', {})
        self.assertEqual(status, 200)
        self.assertTrue(report['ok'])
        self.assertTrue((self.h.dir / 'studio-test-latest.json').exists())
        self.assertTrue(self.h.admin('/api/state')[1]['last_test']['ok'])

    def test_local_show_is_loopback_only(self):
        shown = []
        self.h.ctx.show_window = lambda: shown.append(1)
        self.assertEqual(self.h.request('/api/local/show', {})[0], 200)
        self.assertEqual(shown, [1])
        status, _ = self.h.request('/api/local/show', {}, headers={'Host': f'192.168.50.2:{self.h.port}'})
        self.assertEqual(status, 403)

    def test_request_limits(self):
        status, _ = self.h.request('/api/pair', None)
        self.assertEqual(status, 401)
        conn = http.client.HTTPConnection('127.0.0.1', self.h.port, timeout=5)
        conn.request('POST', '/api/pair', '{"code":"1"}', {'Content-Type': 'text/plain'})
        self.assertEqual(conn.getresponse().status, 400)
        conn.close()

    def test_event_stream_pushes_changes_and_revocation(self):
        token = self.h.pair()
        conn = http.client.HTTPConnection('127.0.0.1', self.h.port, timeout=5)
        conn.request('GET', '/api/events', headers={'Authorization': 'Bearer ' + token})
        response = conn.getresponse()
        self.assertEqual(response.getheader('Content-Type'), 'text/event-stream; charset=utf-8')
        first = response.readline()
        self.assertTrue(first.startswith(b'data: {'))
        self.assertIn(b'"control": false', first)
        response.readline()
        self.h.admin('/api/control', {'enabled': True})
        self.assertIn(b'"control": true', response.readline())
        response.readline()
        self.h.admin('/api/devices/revoke', {'all': True})
        lines = [response.readline() for _ in range(2)]
        self.assertIn(b'event: revoked\n', lines)
        conn.close()
        self.assertTrue(wait_for(lambda: True))


if __name__ == '__main__':
    unittest.main()
