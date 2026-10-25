"""Start Lantern Deck: server, studio connection, Maison bridge, tray and control center."""
import argparse
import json
import logging
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request

from lantern import VERSION, desktop, log as logsetup, storage
from lantern.bridge import MaisonLink
from lantern.deck import DeckStore
from lantern.devices import Devices
from lantern.engine import Engine
from lantern.hotkeys import send_keys
from lantern.server import Context, serve, stop
from lantern.settings import Settings
from lantern.studio import OfflineStudio, StudioClient
from lantern.updates import UpdateChecker

log = logging.getLogger('lantern')
DEFAULT_PORT = 8765


class Runtime:
    def __init__(self, data_dir, host='0.0.0.0', port=DEFAULT_PORT, studio=None, sender=send_keys,
                 maison=True, autostart=None):
        self.data_dir = Path(data_dir)
        settings = Settings(self.data_dir / 'settings.json')
        store = DeckStore(self.data_dir / 'deck.json')
        self.studio = studio or StudioClient()
        engine = Engine(store, self.studio, settings, sender)
        devices = Devices(self.data_dir / 'devices.json')
        self.ctx = Context(self.data_dir, store, engine, devices, settings, autostart=autostart,
                           open_logs=lambda: desktop.open_folder(self.data_dir / 'logs'))
        if maison:
            self.ctx.maison = MaisonLink(self.data_dir, engine)
        self.server, self.thread = serve(self.ctx, host, port)

    @property
    def control_url(self):
        return f'http://127.0.0.1:{self.ctx.port}/control#admin={self.ctx.admin}'

    def start_background(self):
        if self.ctx.maison:
            self.ctx.maison.start()
        if self.ctx.settings['check_updates']:
            self.ctx.updates = UpdateChecker(on_result=self.ctx.engine.bus.notify)
            self.ctx.updates.start()

    def close(self):
        self.ctx.engine._control = False
        stop(self.ctx, self.server)
        if self.ctx.maison:
            self.ctx.maison.close()
        self.studio.close()
        log.info('Lantern Deck stopped')


def notify_running_instance(port):
    try:
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/local/show', data=b'{}',
                                         headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(request, timeout=3).close()
        return True
    except OSError:
        return False


def run(args):
    data_dir = Path(args.data_dir) if args.data_dir else storage.data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    logsetup.setup(data_dir)
    log.info('Lantern Deck %s starting', VERSION)
    mutex = desktop.acquire_single_instance()
    if mutex is None:
        if not notify_running_instance(args.port):
            desktop.message_box('Lantern Deck', 'Lantern Deck is already running. Look for its icon in the taskbar tray.')
        return 0
    try:
        runtime = Runtime(data_dir, args.bind, args.port, autostart=desktop.Autostart())
    except OSError as exc:
        log.error('Could not start: %s', exc)
        desktop.message_box('Lantern Deck could not start',
                            f'Port {args.port} may be in use by another program, or the data folder is not writable.\n\n{exc}',
                            error=True)
        return 1
    except (ValueError, TypeError) as exc:
        log.error('Invalid saved configuration: %s', exc)
        desktop.message_box('Configuration needs attention',
                            'A saved file in %LOCALAPPDATA%\\LanternDeck is invalid and was not changed.\n\n'
                            'Rename deck.json or settings.json there, restart, then import a backup.\n\n' + str(exc),
                            error=True)
        return 1
    ctx = runtime.ctx
    ctx.show_window = lambda: desktop.open_window(runtime.control_url, data_dir)
    runtime.start_background()
    if not args.background:
        ctx.show_window()
    done = threading.Event()
    try:
        try:
            tray = desktop.Tray(ctx, ctx.show_window, done.set)
        except ImportError:
            tray = None
            log.warning('Tray icon unavailable (pystray missing); press Ctrl+C to stop')
        if tray:
            tray.run()
        else:
            done.wait()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
    return 0


def self_test(report_path):
    """Exercise the packaged app end to end without real keys, studio or network."""
    checks = []
    result = {'ok': False}
    runtime = None
    try:
        with tempfile.TemporaryDirectory() as temp:
            sent = []
            runtime = Runtime(Path(temp), '127.0.0.1', 0, studio=OfflineStudio(), sender=sent.append, maison=False)
            ctx = runtime.ctx
            base = f'http://127.0.0.1:{ctx.port}'

            def call(route, token='', body=None):
                req = urllib.request.Request(base + route, data=None if body is None else json.dumps(body).encode(),
                                             headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
                with urllib.request.urlopen(req, timeout=5) as response:
                    return json.load(response)
            for asset in ('/', '/control', '/app.js', '/control.js', '/client.js', '/shortcuts.js', '/i18n.js',
                          '/style.css', '/control.css', '/icon.svg'):
                with urllib.request.urlopen(base + asset, timeout=5) as response:
                    assert response.status == 200 and len(response.read()) > 100, asset
            checks.append('bundled web assets')
            token = call('/api/pair', body={'code': ctx.pairing.code, 'name': 'Self-test'})['token']
            phone = call('/api/state', token)
            assert phone['admin'] is False and phone['control'] is False
            checks.append('phone pairing')
            call('/api/profile', ctx.admin, {'name': 'hotkeys'})
            assert call('/api/press', token, {'id': 'microphone'})['code'] == 'rehearsed' and not sent
            call('/api/control', ctx.admin, {'enabled': True})
            ctx.engine.last = 0  # Skip the anti-double-tap cooldown between the two presses.
            assert call('/api/press', token, {'id': 'brb'})['code'] == 'keys_sent' and sent == ['CTRL+SHIFT+3']
            call('/api/control', ctx.admin, {'enabled': False})
            checks.append('rehearsal and live control switch')
            req = urllib.request.Request(base + '/api/events', headers={'Authorization': 'Bearer ' + token})
            with urllib.request.urlopen(req, timeout=5) as stream:
                assert stream.readline().startswith(b'data: {')
            checks.append('live event stream')
            admin = call('/api/state', ctx.admin)
            assert admin['network'] is not None and admin['pairing']['code']
            from lantern.server import qr_rows
            assert len(qr_rows('http://192.168.1.2:8765/')) > 20
            checks.append('control center state and QR')
            call('/api/profile', ctx.admin, {'name': 'direct'})
            assert call('/api/export', ctx.admin)['buttons'][0]['action']['kind'] == 'scene'
            assert list(Path(temp).glob('deck-backup-*.json'))
            checks.append('profiles, backup and export')
            assert Devices(Path(temp) / 'devices.json').find(token) is not None
            call('/api/devices/revoke', ctx.admin, {'all': True})
            assert Devices(Path(temp) / 'devices.json').find(token) is None
            checks.append('persistent devices and revocation')
            from lantern import dpapi
            assert dpapi.unprotect(dpapi.protect(b'self-test')) == b'self-test'
            checks.append('DPAPI credential encryption')
            assert desktop.tray_image(True).size == (64, 64)
            import pystray  # noqa: F401 - bundled tray backend must import.
            checks.append('tray icon')
            runtime.close()
            runtime = None
            result = {'ok': True, 'version': VERSION, 'checks': checks, 'real_keys_sent': False}
    except Exception as exc:  # The report must always be written.
        result = {'ok': False, 'error': repr(exc), 'passed': checks}
    finally:
        if runtime:
            runtime.close()
        Path(report_path).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog='Lantern Deck', description='Private control deck for TikTok LIVE Studio')
    parser.add_argument('--background', action='store_true', help='Start in the tray without opening a window')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--bind', default='0.0.0.0', help='Listen address (127.0.0.1 keeps phones out)')
    parser.add_argument('--data-dir', help='Use another data folder (testing)')
    parser.add_argument('--self-test', type=Path, metavar='REPORT', help='Run the packaged self-test')
    parser.add_argument('--version', action='version', version=VERSION)
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.self_test)
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
