const $ = (id) => document.getElementById(id);
const status = (text) => {
  $('status').textContent = text;
  if (!$('statusLight')) return;
  const lower = text.toLowerCase();
  $('statusLight').dataset.state = /error|failed|not found|closed|incomplete|invalid|rejected|malformed/.test(lower)
    ? 'error'
    : /connected directly|peer connection: connected|verified and saved/.test(lower)
      ? 'online'
      : 'idle';
};
let socket, pc, channel, isInitiator = false, isSending = false, files = [], incoming = null, pending = [];

function updateControls() {
  const connected = channel?.readyState === 'open';
  $('send').disabled = !connected || !files.length || isSending;
  $('accept').disabled = !incoming?.finished || !incoming.files.length;
}

function connect() {
  if (socket && socket.readyState === WebSocket.OPEN) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const nextSocket = new WebSocket(`ws://${location.hostname}:8766`);
    socket = nextSocket;
    nextSocket.onopen = resolve;
    nextSocket.onerror = () => reject(new Error('Could not connect to local signaling server.'));
    nextSocket.onmessage = (event) => onSignal(JSON.parse(event.data));
    nextSocket.onclose = () => {
      if (socket !== nextSocket) return;
      if (channel?.readyState === 'open') {
        status('Signaling server disconnected. The active direct transfer can continue, but create/join is unavailable.');
        return;
      }
      if (pc && pc.connectionState !== 'closed') pc.close();
      channel = null; pc = null; pending = []; incoming = null;
      $('room').textContent = '— — — — —'; $('roomInput').value = '';
      updateControls(); status('Signaling server disconnected. The old room code is no longer valid; create a fresh room after reconnecting.');
    };
  });
}

function sendSignal(message) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

function setupPeer(initiator) {
  isInitiator = initiator;
  pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
  pc.onicecandidate = ({ candidate }) => { if (candidate) sendSignal({ type: 'candidate', candidate }); };
  pc.onconnectionstatechange = () => {
    if (pc.connectionState === 'connected') status('Connected directly. Choose files or a folder to send.');
    else if (pc.connectionState === 'failed') status('Connection failed. Create a fresh room and have the other device join its new code.');
    else if (pc.connectionState === 'disconnected') status('Connection interrupted. Waiting for the other device to reconnect…');
    updateControls();
  };
  if (initiator) attachChannel(pc.createDataChannel('lantern-files', { ordered: true }));
  else pc.ondatachannel = (event) => attachChannel(event.channel);
}

function attachChannel(ch) {
  channel = ch;
  channel.binaryType = 'arraybuffer';
  channel.onopen = () => { status('Connected directly. Choose files or a folder to send.'); updateControls(); sendSignal({ type: 'ready' }); };
  channel.onclose = () => { status('Transfer connection closed. Create a fresh room to reconnect.'); updateControls(); };
  channel.onmessage = ({ data }) => receiveMessage(data);
}

async function onSignal(message) {
  try {
    if (message.type === 'created' || message.type === 'joined') {
      $('room').textContent = message.room;
      $('roomInput').value = message.room;
      status(message.type === 'created' ? 'Room created. Open a second window and join with this code.' : 'Joined. Waiting for direct connection…');
      if (message.type === 'joined') setupPeer(false);
    } else if (message.type === 'peer-joined' && isInitiator) {
      const offer = await pc.createOffer(); await pc.setLocalDescription(offer); sendSignal({ type: 'offer', description: pc.localDescription });
    } else if (message.type === 'offer') {
      if (!pc) setupPeer(false);
      await pc.setRemoteDescription(message.description);
      for (const candidate of pending) await pc.addIceCandidate(candidate);
      pending = [];
      const answer = await pc.createAnswer(); await pc.setLocalDescription(answer); sendSignal({ type: 'answer', description: pc.localDescription });
    } else if (message.type === 'answer' && isInitiator) {
      await pc.setRemoteDescription(message.description);
      for (const candidate of pending) await pc.addIceCandidate(candidate);
      pending = [];
    } else if (message.type === 'candidate') {
      if (pc?.remoteDescription) await pc.addIceCandidate(message.candidate); else pending.push(message.candidate);
    } else if (message.type === 'peer-left') {
      if (channel && channel.readyState !== 'closed') channel.close();
      if (pc && pc.connectionState !== 'closed') pc.close();
      channel = null; pc = null; pending = []; incoming = null;
      $('room').textContent = '— — — — —'; $('roomInput').value = '';
      updateControls(); status('The other device left; that room has ended. Create or join a fresh room.');
    }
    else if (message.type === 'error') status(message.message);
  } catch (error) { status(`Connection error: ${error.message}`); }
}

async function createRoom() {
  try {
    if (channel && channel.readyState !== 'closed') channel.close();
    if (pc && pc.connectionState !== 'closed') pc.close();
    channel = null; pc = null; pending = []; incoming = null;
    $('room').textContent = '— — — — —'; updateControls();
    await connect(); setupPeer(true); sendSignal({ type: 'create' });
  }
  catch (error) { status(error.message); }
}
async function joinRoom() {
  const room = $('roomInput').value.trim();
  if (!room) { status('Enter a room code first.'); return; }
  try {
    if (channel && channel.readyState !== 'closed') channel.close();
    if (pc && pc.connectionState !== 'closed') pc.close();
    channel = null; pc = null; pending = []; incoming = null;
    $('room').textContent = '— — — — —'; updateControls();
    await connect(); sendSignal({ type: 'join', room });
  }
  catch (error) { status(error.message); }
}

function showFiles(fileList) {
  files = [...fileList];
  $('selection').textContent = files.length
    ? `${files.length} ${files.length === 1 ? 'file' : 'files'} selected · ${formatBytes(files.reduce((n, f) => n + f.size, 0))}`
    : 'Nothing selected yet';
  $('files').replaceChildren(...files.map((file) => {
    const li = document.createElement('li'); li.textContent = `${file.webkitRelativePath || file.name} — ${formatBytes(file.size)}`; return li;
  }));
  updateControls();
}
function formatBytes(n) { return n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(2)} MB`; }
function waitBuffered() {
  if (channel.bufferedAmount < 1024 * 1024) return Promise.resolve();
  return new Promise((resolve) => { channel.onbufferedamountlow = resolve; channel.bufferedAmountLowThreshold = 256 * 1024; });
}

async function sendFiles() {
  if (!channel || channel.readyState !== 'open' || !files.length) return;
  isSending = true; updateControls();
  try {
    const totalBytes = files.reduce((n, file) => n + file.size, 0);
    channel.send(JSON.stringify({ kind: 'start', count: files.length, totalBytes }));
    let done = 0;
    for (const file of files) {
      const path = file.webkitRelativePath || file.name;
      status(`Preparing ${file.name} for integrity checking…`);
      const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer()))].map((b) => b.toString(16).padStart(2, '0')).join('');
      channel.send(JSON.stringify({ kind: 'file', name: file.name, path, size: file.size, digest }));
      const chunkSize = 64 * 1024;
      for (let offset = 0; offset < file.size; offset += chunkSize) {
        await waitBuffered(); channel.send(await file.slice(offset, offset + chunkSize).arrayBuffer());
        done += Math.min(chunkSize, file.size - offset); $('progress').value = done / Math.max(1, files.reduce((n, f) => n + f.size, 0));
      }
      channel.send(JSON.stringify({ kind: 'end-file' }));
    }
    channel.send(JSON.stringify({ kind: 'end' })); $('progress').value = 1; status('All files sent. Waiting for the receiver to accept them.');
  } catch (error) { status(`Send failed: ${error.message}`); }
  finally { isSending = false; updateControls(); }
}

function receiveMessage(data) {
  if (typeof data !== 'string') {
    if (!incoming?.current) return;
    incoming.parts.push(data);
    incoming.fileBytes += data.byteLength;
    incoming.receivedBytes += data.byteLength;
    $('progress').value = incoming.totalBytes
      ? Math.min(1, incoming.receivedBytes / incoming.totalBytes)
      : 0;
    return;
  }
  let msg; try { msg = JSON.parse(data); } catch { status('Received malformed transfer metadata.'); return; }
  if (msg.kind === 'start') {
    if (!Number.isSafeInteger(msg.count) || msg.count < 1 || !Number.isSafeInteger(msg.totalBytes) || msg.totalBytes < 0) {
      status('Received invalid transfer metadata.'); return;
    }
    incoming = { expected: msg.count, completed: 0, parts: [], files: [], totalBytes: msg.totalBytes || 0, receivedBytes: 0, fileBytes: 0, finished: false };
    $('progress').value = 0; updateControls(); status(`Incoming ${msg.count} file(s). Transfer in progress…`);
  } else if (msg.kind === 'file') {
    if (!incoming || incoming.current || typeof msg.path !== 'string' || !Number.isSafeInteger(msg.size) || msg.size < 0 || !/^[\da-f]{64}$/i.test(msg.digest || '')) {
      status('Received invalid file metadata.'); incoming = null; updateControls(); return;
    }
    incoming.current = msg; incoming.parts = []; incoming.fileBytes = 0;
    const li = document.createElement('li'); li.textContent = `Incoming: ${msg.path} — ${formatBytes(msg.size)}`; $('files').append(li);
  } else if (msg.kind === 'end-file') {
    if (!incoming?.current) return;
    if (incoming.fileBytes !== incoming.current.size) {
      status(`Transfer incomplete: ${incoming.current.path} expected ${formatBytes(incoming.current.size)}, received ${formatBytes(incoming.fileBytes)}.`);
      incoming = null; updateControls(); return;
    }
    incoming.files.push({ meta: incoming.current, parts: incoming.parts });
    incoming.completed++; incoming.current = null; incoming.parts = [];
  } else if (msg.kind === 'end') {
    if (!incoming) { status('Received transfer end without a transfer start.'); return; }
    if (incoming.completed !== incoming.expected || incoming.receivedBytes !== incoming.totalBytes) {
      status('Transfer incomplete or inconsistent. Ask the sender to retry in a fresh room.');
      incoming = null; updateControls(); return;
    }
    incoming.finished = true; $('progress').value = 1; updateControls();
    status('Transfer received. Review the list, then accept to verify and save.');
  }
}

async function acceptFiles() {
  if (!incoming?.files.length) { status('No completed files to accept yet.'); return; }
  try {
    for (const item of incoming.files) {
      const blob = new Blob(item.parts);
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map((b) => b.toString(16).padStart(2, '0')).join('');
      if (hash !== item.meta.digest) throw new Error(`Integrity check failed: ${item.meta.path}`);
    }
    const safePaths = incoming.files.map(({ meta }) => {
      const normalized = meta.path.replaceAll('\\', '/');
      const parts = normalized.split('/');
      if (!normalized || normalized.startsWith('/') || /^[a-z]:/i.test(normalized) || parts.some((part) => !part || part === '.' || part === '..' || part.includes('\0'))) {
        throw new Error('Rejected an unsafe or empty file path.');
      }
      return parts;
    });
    if ('showDirectoryPicker' in window) {
      const root = await window.showDirectoryPicker({ mode: 'readwrite' });
      for (const [index, item] of incoming.files.entries()) {
        const parts = safePaths[index];
        let directory = root;
        for (const segment of parts.slice(0, -1)) directory = await directory.getDirectoryHandle(segment, { create: true });
        const handle = await directory.getFileHandle(parts.at(-1), { create: true });
        const writable = await handle.createWritable();
        await writable.write(new Blob(item.parts));
        await writable.close();
      }
      status(`${incoming.files.length} file(s) verified and saved with folder structure.`);
    } else {
      for (const item of incoming.files) {
        const url = URL.createObjectURL(new Blob(item.parts));
        const a = document.createElement('a'); a.href = url; a.download = item.meta.name; a.rel = 'noopener'; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
      status(`${incoming.files.length} file(s) verified; browser downloads started (folder structure is not preserved in this browser).`);
    }
    $('accept').disabled = true; incoming = null;
  } catch (error) { status(error.message); }
}

$('create').onclick = createRoom;
$('join').onclick = joinRoom;
$('send').onclick = sendFiles;
$('accept').onclick = acceptFiles;
$('filePicker').onchange = (event) => showFiles(event.target.files);
$('folderPicker').onchange = (event) => showFiles(event.target.files);
$('copyRoom').onclick = async () => {
  const code = $('room').textContent.trim();
  if (!code || code === '— — — — —') return;
  try { await navigator.clipboard.writeText(code); status('Room code copied. Share it only with your intended recipient.'); }
  catch { $('roomInput').value = code; $('roomInput').select(); status('Select and copy the room code manually.'); }
};
$('dropzone').addEventListener('dragover', (event) => { event.preventDefault(); $('dropzone').classList.add('drag'); });
$('dropzone').addEventListener('dragleave', () => $('dropzone').classList.remove('drag'));
$('dropzone').addEventListener('drop', (event) => {
  event.preventDefault(); $('dropzone').classList.remove('drag'); showFiles(event.dataTransfer.files);
});
