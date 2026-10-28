"""Tiny local WebSocket signaling server for the Lantern prototype."""

from __future__ import annotations

import asyncio
import json
import secrets
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import unquote, urlsplit

try:
    import websockets
except ImportError as exc:
    raise SystemExit("Install the single dependency with: python -m pip install websockets") from exc


ROOT = Path(__file__).resolve().parent
rooms: dict[str, set] = defaultdict(set)


async def leave_room(websocket, room: str | None) -> None:
    if not room:
        return
    peers = rooms.pop(room, None)
    if not peers:
        return
    peers.discard(websocket)
    for peer in tuple(peers):
        try:
            await peer.send(json.dumps({"type": "peer-left"}))
        except websockets.ConnectionClosed:
            pass


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        requested = unquote(urlsplit(path).path).lstrip("/")
        if not requested:
            requested = "index.html"
        candidate = (ROOT / requested).resolve()
        allowed = {
            (ROOT / "index.html").resolve(),
            (ROOT / "app.js").resolve(),
            (ROOT / "tests" / "browser_smoke.html").resolve(),
        }
        if candidate not in allowed:
            return str(ROOT / "__not_found__")
        return str(candidate)

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
    async with websockets.serve(
        signaling,
        "127.0.0.1",
        8766,
        max_size=2**20,
        origins=[None, "http://127.0.0.1:8765", "http://localhost:8765"],
    ):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLantern stopped.")
