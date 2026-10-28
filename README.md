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
channel. Localhost is used for the initial test, so this is not yet a public,
multi-device deployment.

## Current scope

- Select multiple individual files or a directory tree.
- Send files directly over a WebRTC data channel.
- Re-create selected relative folder paths on the receiver.
- Verify each received file with SHA-256 before saving.
- Show transfer progress and per-file status.

This is an experimental prototype, not a security-audited product. Do not use it
for sensitive files yet. It has no authentication, room expiry, TURN relay,
resume, or production abuse controls.
