"""Real Socket.IO wire test against the fake LIVE Studio fixture (needs Node and npm ci)."""
from pathlib import Path
import shutil
import subprocess
import unittest

from lantern.engine import run_studio_test
from lantern.studio import StudioClient
from tests.helpers import wait_for

ROOT = Path(__file__).resolve().parent.parent
AVAILABLE = shutil.which('node') and (ROOT / 'node_modules' / 'socket.io').exists()


@unittest.skipUnless(AVAILABLE, 'Node.js and npm dependencies are required')
class TransportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = subprocess.Popen(['node', str(ROOT / 'tests' / 'studio-fixture.cjs')], stdout=subprocess.PIPE,
                                        stdin=subprocess.PIPE, text=True)
        port = int(self.fixture.stdout.readline().strip())
        # An unrelated port first proves discovery skips listeners that fail the handshake.
        self.client = StudioClient(lambda: [1, port])

    def tearDown(self):
        self.client.close()
        if self.fixture.poll() is None:
            self.fixture.terminate()
            self.fixture.wait()

    def test_full_wire_protocol(self):
        self.assertTrue(wait_for(lambda: self.client.snapshot()['connected'], 10), self.client.detail)
        self.assertTrue(self.client.execute({'action': 'mic', 'muted': True})['state']['mic_mute'])
        self.assertFalse(self.client.execute({'action': 'mic', 'muted': True})['changed'])
        self.assertFalse(self.client.execute({'action': 'mic', 'muted': False})['state']['mic_mute'])
        self.assertEqual(self.client.execute({'action': 'scene', 'scene': 'BRB'})['state']['scene'], 'BRB')
        report = run_studio_test(self.client)
        self.assertTrue(report['ok'], report)
        self.assertEqual(self.client.snapshot()['state']['scene'], 'BRB')
        self.fixture.stdin.write('live\n')
        self.fixture.stdin.flush()
        self.assertTrue(wait_for(lambda: (self.client.snapshot()['state'] or {}).get('stream_status') == 1, 5))
        self.fixture.terminate()
        self.fixture.wait()
        self.assertTrue(wait_for(lambda: not self.client.snapshot()['connected'], 5))


if __name__ == '__main__':
    unittest.main()
