import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from server import Handler, State, shortcut, validate, defaults, key_events

class DeckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sent = []
        self.state = State(Path(self.temp.name) / 'deck.json', sender=self.sent.append)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_port
        self.server.state = self.state
        self.server.allowed_hosts = {f'127.0.0.1:{self.port}'}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, token='', extra=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer '+token}
        headers.update(extra or {})
        c.request('GET' if body is None else 'POST', path, None if body is None else json.dumps(body), headers)
        r = c.getresponse(); raw = r.read(); status = r.status; c.close()
        return status, json.loads(raw) if raw.startswith(b'{') else raw

    def pair(self):
        status, data = self.request('/api/pair', {'code': self.state.code})
        self.assertEqual(status, 200)
        return data['token']

    def configure(self):
        cfg = defaults(); cfg['buttons'][0]['shortcut'] = 'Ctrl+Shift+1'
        self.assertEqual(self.request('/api/config', cfg, self.state.admin)[0], 200)
        return cfg

    def test_auth_pair_and_revoke(self):
        self.assertEqual(self.request('/api/state')[0], 401)
        code = self.state.code; token = self.pair()
        self.assertEqual(self.request('/api/pair', {'code': code})[0], 403)
        status, data = self.request('/api/state', token=token)
        self.assertEqual(status, 200); self.assertFalse(data['admin']); self.assertIsNone(data['pairing'])
        self.assertEqual(self.request('/api/config', defaults(), token)[0], 403)
        self.request('/api/revoke', {}, self.state.admin)
        self.assertEqual(self.request('/api/state', token=token)[0], 401)

    def test_expiry_and_rate_limit(self):
        self.state.code_until = 0
        self.assertEqual(self.request('/api/pair', {'code':self.state.code})[0], 403)
        for _ in range(9): self.request('/api/pair', {'code':'wrong'})
        self.assertEqual(self.request('/api/pair', {'code':self.state.code})[0], 429)

    def test_origin_and_host(self):
        self.assertEqual(self.request('/api/state', token=self.state.admin, extra={'Origin':'http://evil.example'})[0], 403)
        self.assertEqual(self.request('/', extra={'Host':'evil.example'})[0], 403)
        self.assertEqual(self.request('/')[0], 200)
        self.assertEqual(self.request('/../server.py')[0], 401)

    def test_rehearsal_and_allowlist(self):
        token = self.pair(); self.configure()
        self.assertEqual(self.request('/api/trigger', {'id':'b0','shortcut':'Alt+F4'}, token)[0], 200)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.request('/api/trigger', {'id':'unknown','command':'whoami'}, token)[0], 400)
        self.assertEqual(self.request('/api/trigger', {'id':'b1'}, token)[0], 400)

    def test_execution_confirmation_and_cooldown(self):
        cfg = self.configure(); cfg['buttons'][0]['confirm'] = True
        self.request('/api/config', cfg, self.state.admin)
        self.state.execute = True
        self.assertEqual(self.request('/api/trigger', {'id':'b0'}, self.state.admin)[0], 400)
        self.assertEqual(self.request('/api/trigger', {'id':'b0','confirmed':True,'shortcut':'Alt+F4'}, self.state.admin)[0], 200)
        self.assertEqual(self.sent, ['CTRL+SHIFT+1'])
        self.assertEqual(self.request('/api/trigger', {'id':'b0','confirmed':True}, self.state.admin)[0], 429)

    def test_persistence_and_invalid_config(self):
        self.configure()
        reopened = State(self.state.path)
        self.assertEqual(reopened.config['buttons'][0]['shortcut'], 'CTRL+SHIFT+1')
        self.assertNotEqual(reopened.admin, self.state.admin)
        cfg = defaults(); cfg['buttons'][1]['id'] = 'b0'
        self.assertEqual(self.request('/api/config', cfg, self.state.admin)[0], 400)
        self.assertEqual(self.state.config['buttons'][0]['shortcut'], 'CTRL+SHIFT+1')

    def test_shortcut_validation(self):
        for bad in ('Win+R', 'Ctrl+A+B', 'Ctrl+Ctrl+A', 'A', 'Ctrl+;whoami', 'Alt+$(calc)', 42):
            with self.assertRaises(ValueError): shortcut(bad)
        self.assertEqual(shortcut(' ctrl + shift + f12 '), 'CTRL+SHIFT+F12')

    def test_sided_modifiers(self):
        for typed in ('Left Alt', 'LAlt', 'left-alt', 'left_alt'):
            self.assertEqual(shortcut(typed), 'LEFTALT')
        self.assertEqual(shortcut('Left Alt + M'), 'LEFTALT+M')
        self.assertEqual(shortcut('Right Control+F24'), 'RIGHTCTRL+F24')
        for bad in ('Ctrl+LeftCtrl+A', 'LeftAlt+RightAlt+A', 'F25'):
            with self.assertRaises(ValueError): shortcut(bad)
        self.assertEqual(key_events('LeftAlt')[1], [(0, 0x38, 8), (0, 0x38, 10)])
        self.assertEqual(key_events('RightAlt+M')[1], [(0, 0x38, 9), (77, 0, 0), (77, 0, 2), (0, 0x38, 11)])

    def test_left_alt_round_trip(self):
        cfg = defaults(); cfg['buttons'][0]['shortcut'] = 'Left Alt+M'
        self.assertEqual(self.request('/api/config', cfg, self.state.admin)[0], 200)
        self.assertEqual(State(self.state.path).config['buttons'][0]['shortcut'], 'LEFTALT+M')
        self.state.execute = True
        token = self.pair()
        self.assertEqual(self.request('/api/trigger', {'id':'b0'}, token)[0], 200)
        self.assertEqual(self.sent, ['LEFTALT+M'])
        self.assertEqual(self.request('/shortcuts.js')[0], 200)

if __name__ == '__main__': unittest.main()
