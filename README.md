# Lantern

Local prototype of a browser-based peer-to-peer file and folder transfer tool.

## Run locally

Requirements: Python 3.10+ and a modern browser with WebRTC support.

```powershell
python server.py
```

Open `http://127.0.0.1:8765` in two browser windows. Create a room in one window,
join the displayed room code in the other, then choose files or folders and send.
For this prototype, both windows must be on the same computer. The signaling
server only exchanges connection metadata; file bytes travel over a WebRTC data
channel. Google STUN is contacted to help establish a direct route and may see
the peers' public IP addresses; it does not relay file contents. Localhost is
used for the initial test, so this is not yet a public, multi-device deployment.

## Tests

Run the signaling-server integration tests with:

```powershell
python -m unittest discover -s tests -v
```

With the server running, open `http://127.0.0.1:8765/tests/browser_smoke.html`
and click **Run transfer test** for a local end-to-end browser check. It creates
two isolated browser peers, transfers generated sample data (including an empty
file and a nested path), verifies SHA-256, and checks saving through an in-memory
filesystem stub. It does not read or send real user files.

## Current scope

- Select multiple individual files or a directory tree.
- Send files directly over a WebRTC data channel.
- Re-create selected relative folder paths on the receiver.
- Verify each received file with SHA-256 before saving.
- Show transfer progress and per-file status.

This is an experimental prototype, not a security-audited product. Do not use it
for sensitive files yet. It has no authentication, idle-room timeout, TURN relay,
resume, or production abuse controls. Signaling is currently restricted to
localhost and the app only serves its explicitly allowed local pages/scripts.
The browser buffers selected and received files while hashing and saving, so
memory use grows with the size of a transfer. Use smaller transfers until a
streaming implementation is added.
