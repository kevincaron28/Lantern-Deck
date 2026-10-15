const {Server}=require('socket.io');
const http=require('http');
const server=http.createServer();const io=new Server(server,{serveClient:false});
const state={mic_mute:false,audio_mute:false,stream_status:0,scene:'Game',scene_list:[{name:'Game'},{name:'BRB'}]};
io.use((socket,next)=>socket.request.headers['sec-websocket-protocol']==='streamdeck_ttls_v1'?next():next(Error('protocol')));
io.on('connection',socket=>{
 let joined=false;
 socket.on('stream_deck/join_room',()=>{if(joined)throw Error('Duplicate join');joined=true;socket.emit('stream_deck/sync_settings',JSON.stringify(state));});
 socket.on('stream_deck/sync_settings',()=>{if(joined)socket.emit('stream_deck/sync_settings',JSON.stringify(state));});
 socket.on('stream_deck/action_emit',raw=>{const data=JSON.parse(raw);const kind=data.action.split('.').at(-1);if(kind==='mic'||kind==='audio')state[kind+'_mute']=!state[kind+'_mute'];else if(kind==='scene')state.scene=data.payload.settings.scene;else throw Error('Forbidden action');socket.emit('stream_deck/'+data.context,JSON.stringify({code:0}));socket.emit('stream_deck/sync_settings',JSON.stringify(state));});
});
server.listen(0,'127.0.0.1',()=>console.log(server.address().port));
