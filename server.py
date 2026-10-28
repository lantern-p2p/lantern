"""Tiny local WebSocket signaling server for the Lantern prototype."""

from __future__ import annotations

import asyncio
import json
import secrets
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

try:
    import websockets
except ImportError as exc:
    raise SystemExit("Install the single dependency with: python -m pip install websockets") from exc


ROOT = Path(__file__).resolve().parent
rooms: dict[str, set] = defaultdict(set)


async def leave_room(websocket, room: str | None) -> None:
    if not room:
        return
    peers = rooms.get(room)
    if not peers:
        return
    peers.discard(websocket)
    for peer in tuple(peers):
        try:
            await peer.send(json.dumps({"type": "peer-left"}))
        except websockets.ConnectionClosed:
            peers.discard(peer)
    if not peers:
        rooms.pop(room, None)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, _format, *_args):
        pass


async def signaling(websocket):
    room = None
    try:
        async for raw in websocket:
            message = json.loads(raw)
            kind = message.get("type")
            if kind == "create":
                await leave_room(websocket, room)
                room = secrets.token_urlsafe(5)
                rooms[room].add(websocket)
                await websocket.send(json.dumps({"type": "created", "room": room}))
            elif kind == "join":
                candidate = str(message.get("room", ""))
                peers = rooms.get(candidate, set())
                if not peers or len(peers) >= 2:
                    await websocket.send(json.dumps({"type": "error", "message": "Room not found or full."}))
                    continue
                if websocket in peers:
                    await websocket.send(json.dumps({"type": "error", "message": "Open the room code in a second browser or device."}))
                    continue
                if room != candidate:
                    await leave_room(websocket, room)
                room = candidate
                peers.add(websocket)
                await websocket.send(json.dumps({"type": "joined", "room": room}))
                for peer in tuple(peers):
                    if peer is not websocket:
                        await peer.send(json.dumps({"type": "peer-joined"}))
            elif room and kind in {"offer", "answer", "candidate", "ready"}:
                for peer in tuple(rooms.get(room, set())):
                    if peer is not websocket:
                        await peer.send(raw)
    except (websockets.ConnectionClosed, json.JSONDecodeError):
        pass
    finally:
        await leave_room(websocket, room)


async def main():
    http = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    Thread(target=http.serve_forever, daemon=True).start()
    print("Lantern prototype: http://127.0.0.1:8765  (Ctrl+C to stop)")
    async with websockets.serve(signaling, "127.0.0.1", 8766, max_size=2**20):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLantern stopped.")
