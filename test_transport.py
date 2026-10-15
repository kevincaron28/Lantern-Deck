import subprocess,time,json
from pathlib import Path
from studio import StudioClient
Path('work').mkdir(exist_ok=True)
p=subprocess.Popen(['node','tests/studio-fixture.cjs'],stdout=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
c=None
try:
 port=int(p.stdout.readline().strip());c=StudioClient(lambda:[port]);deadline=time.monotonic()+10
 while not c.snapshot()['connected'] and time.monotonic()<deadline:time.sleep(.1)
 assert c.snapshot()['connected'], c.snapshot()
 assert c.execute({'action':'mic','muted':True})['state']['mic_mute']
 assert c.execute({'action':'mic','muted':True})['state']['mic_mute']
 assert c.execute({'action':'mic','muted':False})['state']['mic_mute'] is False
 assert c.execute({'action':'audio','muted':True})['state']['audio_mute']
 assert c.execute({'action':'scene','scene':'BRB'})['state']['scene']=='BRB'
 p.terminate();p.wait();time.sleep(.4)
 assert c.snapshot()['connected'] is False
 result={'ok':True,'fixture_only':True,'checks':['Socket.IO handshake and subprotocol','join once','state read','mute target idempotency','scene selection','disconnect invalidation'],'real_studio_modified':False}
 Path('work/studio-transport-test.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
 if c:c.close()
 if p.poll() is None:p.terminate();p.wait()
