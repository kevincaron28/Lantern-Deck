"""Windows desktop integration: single instance, tray icon, app window, start with Windows."""
import ctypes
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import webbrowser

log = logging.getLogger(__name__)
MUTEX_NAME = 'Local\\LanternDeck.SingleInstance'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_VALUE = 'Lantern Deck'
ERROR_ALREADY_EXISTS = 183


def acquire_single_instance():
    """Return a mutex handle, or None when another Lantern Deck is already running."""
    if os.name != 'nt':
        return True
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return handle


def message_box(title, text, error=False):
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
    else:
        print(f'{title}: {text}', file=sys.stderr)


def launch_command():
    """Command used for start-with-Windows; opens straight to the tray."""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}" --background'
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    script = Path(__file__).resolve().parent.parent / 'run_lantern.py'
    return f'"{pythonw if pythonw.exists() else sys.executable}" "{script}" --background'


class Autostart:
    """HKCU Run entry; changed only when the user flips the setting."""

    def __init__(self, command=None, registry=None):
        self.command = command or launch_command()
        if registry is None and os.name == 'nt':
            import winreg
            registry = winreg
        self.registry = registry

    def enabled(self):
        if self.registry is None:
            return False
        try:
            with self.registry.OpenKey(self.registry.HKEY_CURRENT_USER, RUN_KEY) as key:
                return self.registry.QueryValueEx(key, RUN_VALUE)[0] == self.command
        except OSError:
            return False

    def set(self, enabled):
        if self.registry is None:
            raise OSError('Start with Windows is only available on Windows')
        reg = self.registry
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            if enabled:
                reg.SetValueEx(key, RUN_VALUE, 0, reg.REG_SZ, self.command)
            else:
                try:
                    reg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        log.info('Start with Windows %s', 'enabled' if enabled else 'disabled')
        return self.enabled()


def find_edge():
    candidates = [shutil.which('msedge')]
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
        if base:
            candidates.append(str(Path(base) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'))
    return next((c for c in candidates if c and Path(c).exists()), None)


def open_window(url, data_dir):
    """Open the control center as a chromeless Edge app window, else the default browser."""
    edge = find_edge()
    if edge:
        try:
            subprocess.Popen([edge, f'--app={url}', f'--user-data-dir={Path(data_dir) / "window"}',
                              '--no-first-run', '--no-default-browser-check', '--window-size=1220,880'],
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return True
        except OSError:
            log.warning('Edge app window failed; using the default browser')
    return webbrowser.open(url)


def open_folder(path):
    if os.name == 'nt':
        os.startfile(str(path))  # noqa: S606 - opens our own data folder in Explorer.


def tray_image(active=False, size=64):
    """Lantern glyph; glows cyan while Live control is ON."""
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size / 64
    glow = (84, 232, 219, 255) if active else (128, 138, 156, 255)
    draw.rounded_rectangle([20 * s, 4 * s, 44 * s, 12 * s], radius=3 * s, fill=(225, 230, 240, 255))
    draw.rounded_rectangle([14 * s, 12 * s, 50 * s, 56 * s], radius=9 * s, fill=(28, 33, 44, 255),
                           outline=(225, 230, 240, 255), width=max(1, int(4 * s)))
    draw.ellipse([23 * s, 22 * s, 41 * s, 46 * s], fill=glow)
    draw.rectangle([22 * s, 56 * s, 42 * s, 60 * s], fill=(225, 230, 240, 255))
    return image


class Tray:
    def __init__(self, ctx, show_window, quit_app):
        import pystray
        self.pystray, self.ctx = pystray, ctx
        self.show_window, self.quit_app = show_window, quit_app
        item = pystray.MenuItem
        menu = pystray.Menu(
            item('Open control center', lambda: show_window(), default=True),
            item('Live control', self._toggle_control, checked=lambda _: ctx.engine.control),
            item('Open Maison Deck', lambda: webbrowser.open(ctx.maison.origin + '/deck.html') if ctx.maison else None),
            pystray.Menu.SEPARATOR,
            item('Start with Windows', self._toggle_autostart,
                 checked=lambda _: bool(ctx.autostart and ctx.autostart.enabled()),
                 enabled=lambda _: ctx.autostart is not None),
            item('Open log folder', lambda: open_folder(ctx.data_dir / 'logs')),
            pystray.Menu.SEPARATOR,
            item('Quit Lantern Deck', self._quit))
        self.icon = pystray.Icon('lantern-deck', tray_image(ctx.engine.control), 'Lantern Deck', menu)
        self._shown = None
        ctx.engine.bus_listeners.append(self.refresh)

    def _toggle_control(self):
        self.ctx.engine.set_control(not self.ctx.engine.control)

    def _toggle_autostart(self):
        try:
            self.ctx.autostart.set(not self.ctx.autostart.enabled())
        except OSError:
            log.exception('Could not change start with Windows')

    def refresh(self):
        studio = self.ctx.engine.studio_state()
        key = (self.ctx.engine.control, studio['connected'], studio['live'])
        if key == self._shown:
            return
        self._shown = key
        self.icon.icon = tray_image(key[0])
        self.icon.title = 'Lantern Deck · Live control ' + ('ON' if key[0] else 'OFF') + \
            (' · Studio connected' if key[1] else ' · Studio offline') + (' · LIVE' if key[2] else '')
        self.icon.update_menu()

    def _quit(self):
        self.icon.stop()
        self.quit_app()

    def run(self):
        self.icon.run()
