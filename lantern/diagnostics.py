"""Read-only diagnostics report. Contains no tokens, codes or credentials."""
import os
import platform
import sys
import time

from lantern import VERSION


def installed_studio_version():
    """Version recorded by the LIVE Studio installer, if any (registry, read-only)."""
    if os.name != 'nt':
        return None
    import winreg
    roots = [(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Uninstall'),
             (winreg.HKEY_LOCAL_MACHINE, r'Software\Microsoft\Windows\CurrentVersion\Uninstall'),
             (winreg.HKEY_LOCAL_MACHINE, r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')]
    for root, path in roots:
        try:
            with winreg.OpenKey(root, path) as parent:
                for index in range(winreg.QueryInfoKey(parent)[0]):
                    try:
                        with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as key:
                            name = winreg.QueryValueEx(key, 'DisplayName')[0]
                            if str(name).lower().startswith('tiktok live studio'):
                                return str(winreg.QueryValueEx(key, 'DisplayVersion')[0])
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def report(ctx):
    engine = ctx.engine
    studio = engine.studio_state()
    detail = engine.studio.diagnostics()
    return {
        'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
        'lantern': {'version': VERSION, 'frozen': bool(getattr(sys, 'frozen', False)),
                    'python': platform.python_version(), 'windows': platform.platform()},
        'live_control': engine.control,
        'studio': {'installed_version': installed_studio_version(), 'process_running': detail['running'],
                   'listening_ports': detail['ports'], 'connected_port': detail['port'],
                   'connection_detail': detail['detail'], 'connected': studio['connected'],
                   'scene_count': len(studio['scenes']), 'current_scene': studio['scene'],
                   'mic_muted': studio['mic_muted'], 'audio_muted': studio['audio_muted'],
                   'stream_status': studio['stream_status']},
        'maison': ctx.maison.status() if ctx.maison else None,
        'phones': {'paired': len(ctx.devices.public()), 'port': ctx.port},
        'network': ctx.addresses(),
        'settings': ctx.settings.public(),
        'deck': {'buttons': len(ctx.store.config['buttons']),
                 'kinds': sorted({b['action']['kind'] for b in ctx.store.config['buttons']})},
        'data_folder': str(ctx.data_dir),
        'last_studio_test': ctx.last_test,
    }
