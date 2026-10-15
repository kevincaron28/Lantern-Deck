import json
import threading
import time
import unittest
from collections import deque
from studio import normalize_state, action_for, StudioClient
from maison_bridge import MaisonBridge

RAW = {'mic_mute':False,'audio_mute':False,'stream_status':0,'scene':'Gaming',
       'scene_list':[{'name':'Gaming'},{'name':'BRB'}], 'private_extra':'never forward'}

def fake_studio():
    client=StudioClient.__new__(StudioClient)
    client.changed=threading.Condition();client.command_lock=threading.Lock()
    client.data=normalize_state(RAW);client.updated=time.monotonic();client.sequence=1
    client.results={};client.socket=object();client.error='offline';client.sent=[]
    def emit(name,payload=None):
        client.sent.append((name,payload))
        if name=='sync_settings':client.sequence+=1;client.updated=time.monotonic()
        if name=='action_emit':
            action=payload['action'].split('.')[-1]
            if action=='scene':client.data['scene']=payload['payload']['settings']['scene']
            else:client.data[action+'_mute']=not client.data[action+'_mute']
            client.results['stream_deck/'+payload['context']]={'code':0}
    client.emit=emit
    return client

class StudioTests(unittest.TestCase):
    def test_state_redaction_and_strict_types(self):
        state=normalize_state(json.dumps(RAW))
        self.assertNotIn('private_extra',state)
        self.assertEqual(state['scenes'],['Gaming','BRB'])
        for key,value in [('mic_mute',0),('audio_mute','false'),('stream_status',True),('scene_list',[{'name':'x'},{'name':'x'}])]:
            with self.assertRaises(ValueError):normalize_state(RAW | {key:value})

    def test_allowlist(self):
        state=normalize_state(RAW)
        for command in ({'action':'livestartend'},{'action':'mic','muted':'yes'},{'action':'scene','scene':'unknown'}):
            with self.assertRaises(ValueError):action_for(command,state)

    def test_verified_mute_is_idempotent(self):
        client=fake_studio()
        self.assertTrue(client.execute({'action':'mic','muted':True})['state']['mic_mute'])
        client.execute({'action':'mic','muted':True})
        self.assertEqual(sum(n=='action_emit' for n,p in client.sent),1)
        self.assertFalse(client.data['audio_mute'])
        self.assertEqual(client.execute({'action':'scene','scene':'BRB'})['state']['scene'],'BRB')

    def test_stale_snapshot_never_reports_connected(self):
        client=fake_studio();client.updated-=10
        self.assertFalse(client.snapshot()['connected'])
        self.assertIsNone(client.snapshot()['state'])

    def test_bridge_rejects_disabled_expired_duplicate(self):
        bridge=MaisonBridge.__new__(MaisonBridge)
        bridge.enabled=False;bridge.seen=deque(maxlen=256);bridge.studio=fake_studio()
        msg={'type':'action','id':'one','command':{'action':'audio','muted':True},'expires':time.time()*1000+5000}
        self.assertEqual(bridge.handle(msg)['error'],'control_disabled')
        bridge.enabled=True
        self.assertEqual(bridge.handle(msg)['error'],'duplicate_command')
        self.assertEqual(bridge.handle(msg|{'id':'two','expires':0})['error'],'command_expired')
        self.assertTrue(bridge.handle(msg|{'id':'three'})['ok'])
        self.assertTrue(bridge.studio.data['audio_mute'])
        self.assertFalse(bridge.studio.data['mic_mute'])

if __name__=='__main__':unittest.main()
