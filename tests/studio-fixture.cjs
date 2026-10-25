// Fake LIVE Studio controller (Socket.IO) for tests and UI development. Never touches the real app.
// Prints its port on the first line. Type "live" or "offline" on stdin to change stream_status.
const { Server } = require('socket.io');
const http = require('http');
const readline = require('readline');

const server = http.createServer();
const io = new Server(server, { serveClient: false });
const state = {
  mic_mute: false, audio_mute: false, stream_status: 0, scene: 'Starting soon',
  scene_list: [{ name: 'Starting soon' }, { name: 'Gaming' }, { name: 'BRB' }, { name: 'Ending' }]
};
const sockets = new Set();
const broadcast = () => { for (const s of sockets) s.emit('stream_deck/sync_settings', JSON.stringify(state)); };

io.use((socket, next) => socket.request.headers['sec-websocket-protocol'] === 'streamdeck_ttls_v1' ? next() : next(Error('protocol')));
io.on('connection', socket => {
  let joined = false;
  socket.on('stream_deck/join_room', () => {
    if (joined) throw Error('Duplicate join');
    joined = true; sockets.add(socket);
    socket.emit('stream_deck/sync_settings', JSON.stringify(state));
  });
  socket.on('disconnect', () => sockets.delete(socket));
  socket.on('stream_deck/sync_settings', () => { if (joined) socket.emit('stream_deck/sync_settings', JSON.stringify(state)); });
  socket.on('stream_deck/action_emit', raw => {
    const data = JSON.parse(raw);
    const kind = data.action.split('.').at(-1);
    if (kind === 'mic' || kind === 'audio') state[kind + '_mute'] = !state[kind + '_mute'];
    else if (kind === 'scene') state.scene = data.payload.settings.scene;
    else throw Error('Forbidden action');
    socket.emit('stream_deck/' + data.context, JSON.stringify({ code: 0 }));
    broadcast();
  });
});
readline.createInterface({ input: process.stdin }).on('line', line => {
  if (line.trim() === 'live') state.stream_status = 1;
  if (line.trim() === 'offline') state.stream_status = 0;
  broadcast();
});
server.listen(Number(process.env.FIXTURE_PORT || 0), '127.0.0.1', () => process.stdout.write(String(server.address().port) + '\n'));
