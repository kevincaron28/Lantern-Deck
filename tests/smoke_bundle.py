"""Run the packaged app's self-test from a copy in a path with spaces and no Python on PATH."""
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
source = root / 'outputs' / 'dist' / 'Lantern Deck'
target = root / 'work' / 'portable check with spaces' / 'Lantern Deck'
if target.exists():
    shutil.rmtree(target)
shutil.copytree(source, target)
exe = target / 'Lantern Deck.exe'
env = dict(os.environ)
env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
for name in ('PYTHONPATH', 'PYTHONHOME', 'LANTERN_DATA_DIR'):
    env.pop(name, None)
report = target.parent / 'report.json'
report.unlink(missing_ok=True)
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
run = subprocess.run([str(exe), '--self-test', str(report)], cwd=target, env=env, startupinfo=startup,
                     creationflags=subprocess.CREATE_NO_WINDOW, timeout=120, check=False)
result = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {'ok': False, 'error': 'No report'}
result['exit_code'] = run.returncode
result['python_on_path'] = False
(root / 'work' / 'binary-smoke.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
if run.returncode or not result['ok']:
    raise SystemExit(1)
