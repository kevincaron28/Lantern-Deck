import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
target = root / 'work' / 'portable check with spaces'
target.mkdir(exist_ok=True)
exe = target / 'Lantern Deck.exe'
shutil.copy2(root / 'outputs' / exe.name, exe)
env = dict(os.environ)
env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
env.pop('PYTHONPATH', None)
env.pop('PYTHONHOME', None)
report = target / 'report.json'
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
run = subprocess.run([str(exe), '--self-test', str(report)], cwd=target, env=env,
                     startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW, timeout=90)
result = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {'ok':False, 'error':'No report'}
result['exit_code'] = run.returncode
result['python_on_path'] = False
(root / 'work' / 'binary-smoke.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
if run.returncode or not result['ok']:
    raise SystemExit(1)
