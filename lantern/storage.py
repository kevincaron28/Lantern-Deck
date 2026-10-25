"""Data folder location and small atomic JSON helpers."""
import json
import os
from pathlib import Path
import sys
import time

MAX_BACKUPS = 10


def data_dir():
    """Settings live outside the program so updates never touch them."""
    override = os.environ.get('LANTERN_DATA_DIR')
    if override:
        path = Path(override)
    else:
        path = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LanternDeck'
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_dir():
    """Folder holding the bundled web assets (PyInstaller or source checkout)."""
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, data):
    """Write through a temporary file so a crash never leaves half a file."""
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def backup(path):
    """Copy an existing file to a timestamped backup and keep the newest few."""
    path = Path(path)
    if not path.exists():
        return None
    target = path.with_name(f'{path.stem}-backup-{time.time_ns()}{path.suffix}')
    target.write_bytes(path.read_bytes())
    backups = sorted(path.parent.glob(f'{path.stem}-backup-*{path.suffix}'))
    for old in backups[:-MAX_BACKUPS]:
        try:
            old.unlink()
        except OSError:
            pass
    return target
