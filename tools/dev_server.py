"""Run Lantern Deck against the fake LIVE Studio fixture for UI development.

    python tools/dev_server.py [--port 8790]

Uses work/dev-data as its data folder, sends no keys and never contacts Maison.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lantern import log as logsetup  # noqa: E402
from lantern.app import Runtime  # noqa: E402
from lantern.studio import StudioClient  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8790)
    args = parser.parse_args()
    data = ROOT / 'work' / 'dev-data'
    data.mkdir(parents=True, exist_ok=True)
    logsetup.setup(data)
    fixture = subprocess.Popen(['node', str(ROOT / 'tests' / 'studio-fixture.cjs')], stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE, text=True)
    studio_port = int(fixture.stdout.readline().strip())
    runtime = Runtime(data, '0.0.0.0', args.port, studio=StudioClient(lambda: [studio_port]),
                      sender=lambda keys: print('[dev] would send', keys), maison=False)
    print('Control center:', runtime.control_url, flush=True)
    print(f'Phone:          http://127.0.0.1:{args.port}/   pairing code {runtime.ctx.pairing.code}', flush=True)
    print('Type "live" or "offline" to change the fake stream state, Ctrl+C to stop.', flush=True)
    stop = threading.Event()
    try:
        for line in sys.stdin:
            fixture.stdin.write(line)
            fixture.stdin.flush()
        stop.wait()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
        fixture.terminate()


if __name__ == '__main__':
    main()
