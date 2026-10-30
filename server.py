"""Single-process HTTP and WebSocket signaling service for Lantern."""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web


ROOT = Path(__file__).resolve().parent
ROOM_TTL_SECONDS = 2 * 60 * 60
CREATE_LIMIT = 5
CREATE_WINDOW_SECONDS = 60
MAX_CONNECTIONS = int(os.environ.get("LANTERN_MAX_CONNECTIONS", "300"))
ROOM_CODE = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
FORWARDED_TYPES = {"offer", "answer", "candidate", "ready"}
STATIC_FILES = {
    "/": (ROOT / "index.html", "text/html"),
    "/index.html": (ROOT / "index.html", "text/html"),
    "/app.js": (ROOT / "app.js", "text/javascript"),
    "/favicon.svg": (ROOT / "favicon.svg", "image/svg+xml"),
}
TEST_FILES = {
    "/tests/browser_smoke.html": (ROOT / "tests" / "browser_smoke.html", "text/html"),
    "/tests/browser_smoke.js": (ROOT / "tests" / "browser_smoke.js", "text/javascript"),
}


@dataclass
class Room:
    peers: set[web.WebSocketResponse] = field(default_factory=set)
    expires_at: float = field(default_factory=lambda: time.monotonic() + ROOM_TTL_SECONDS)


class SignalingHub:
    """Ephemeral room state. File payloads are never accepted by this service."""

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.connections: set[web.WebSocketResponse] = set()
        self.creates_by_ip: dict[str, deque[float]] = defaultdict(deque)

    async def notify(self, peers: set[web.WebSocketResponse], message: dict) -> None:
        payload = json.dumps(message, separators=(",", ":"))
        for peer in tuple(peers):
            if not peer.closed:
                try:
                    await peer.send_str(payload)
                except (ConnectionError, RuntimeError):
                    pass

    async def leave(self, websocket: web.WebSocketResponse, room_code: str | None) -> None:
        room = self.rooms.get(room_code or "")
        if not room:
            return
        room.peers.discard(websocket)
        if not room.peers:
            self.rooms.pop(room_code or "", None)
        else:
            await self.notify(room.peers, {"type": "peer-left"})

    async def end_room(self, room_code: str | None, requester: web.WebSocketResponse) -> None:
        room = self.rooms.pop(room_code or "", None)
        if room:
            await self.notify(room.peers - {requester}, {"type": "peer-left"})

    def can_create(self, address: str) -> bool:
        now = time.monotonic()
        attempts = self.creates_by_ip[address]
        while attempts and now - attempts[0] >= CREATE_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= CREATE_LIMIT:
            return False
        attempts.append(now)
        return True


HUB_KEY = web.AppKey("hub", SignalingHub)
EXPIRY_TASK_KEY = web.AppKey("expiry_task", asyncio.Task)


def security_headers(response: web.StreamResponse, websocket_origin: str) -> web.StreamResponse:
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "SAMEORIGIN",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"connect-src 'self' {websocket_origin} stun: turn: turns:; "
            "img-src 'self' data:; font-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'self'"
        ),
        "Cache-Control": "no-store, max-age=0",
    })
    return response


@web.middleware
async def security_middleware(request: web.Request, handler):
    response = await handler(request)
    forwarded_scheme = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
    is_https = forwarded_scheme == "https" if os.environ.get("RENDER_SERVICE_ID") else request.scheme == "https"
    websocket_scheme = "wss" if is_https else "ws"
    return security_headers(response, f"{websocket_scheme}://{request.host}")


async def static_file(request: web.Request) -> web.Response:
    path, _content_type = STATIC_FILES.get(request.path) or TEST_FILES[request.path]
    return web.FileResponse(path)


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "lantern-signaling"})


def origin_matches_request(request: web.Request) -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return False
    try:
        parsed = urlsplit(origin)
        forwarded_scheme = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
        expected_scheme = (
            "https" if forwarded_scheme == "https" else "http"
        ) if os.environ.get("RENDER_SERVICE_ID") else request.scheme
        return (
            parsed.scheme == expected_scheme
            and parsed.netloc.casefold() == request.host.casefold()
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


async def websocket_handler(request: web.Request) -> web.StreamResponse:
    hub: SignalingHub = request.app[HUB_KEY]
    if not origin_matches_request(request):
        raise web.HTTPForbidden(text="WebSocket origin is not allowed.")
    if len(hub.connections) >= MAX_CONNECTIONS:
        raise web.HTTPServiceUnavailable(text="Lantern is at its temporary connection limit. Try again shortly.")

    websocket = web.WebSocketResponse(max_msg_size=1024 * 1024, heartbeat=25, compress=False)
    await websocket.prepare(request)
    hub.connections.add(websocket)
    room_code: str | None = None
    address = request.remote or "unknown"
    if os.environ.get("RENDER_SERVICE_ID"):
        address = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip() or address
    try:
        async for frame in websocket:
            if frame.type == WSMsgType.TEXT:
                try:
                    message = json.loads(frame.data)
                except json.JSONDecodeError:
                    await hub.notify({websocket}, {"type": "error", "message": "Malformed signaling message."})
                    continue
                if not isinstance(message, dict):
                    await hub.notify({websocket}, {"type": "error", "message": "Invalid signaling message."})
                    continue
                kind = message.get("type")

                if kind == "create":
                    if not hub.can_create(address):
                        await hub.notify({websocket}, {"type": "error", "message": "Room creation is temporarily rate-limited. Please wait a minute."})
                        continue
                    await hub.end_room(room_code, websocket)
                    room_code = secrets.token_urlsafe(9)
                    hub.rooms[room_code] = Room(peers={websocket})
                    await hub.notify({websocket}, {"type": "created", "room": room_code})

                elif kind == "join":
                    candidate = message.get("room")
                    if not isinstance(candidate, str) or not ROOM_CODE.fullmatch(candidate):
                        await hub.notify({websocket}, {"type": "error", "message": "Enter a valid room code."})
                        continue
                    room = hub.rooms.get(candidate)
                    if room and room.expires_at <= time.monotonic():
                        await hub.notify(room.peers, {"type": "peer-left"})
                        hub.rooms.pop(candidate, None)
                        room = None
                    if not room or len(room.peers) >= 2:
                        await hub.notify({websocket}, {"type": "error", "message": "Room not found or full."})
                        continue
                    if websocket in room.peers:
                        await hub.notify({websocket}, {"type": "error", "message": "Open the room code on a second browser or device."})
                        continue
                    await hub.leave(websocket, room_code)
                    room_code = candidate
                    room.peers.add(websocket)
                    room.expires_at = time.monotonic() + ROOM_TTL_SECONDS
                    await hub.notify({websocket}, {"type": "joined", "room": room_code})
                    await hub.notify(room.peers - {websocket}, {"type": "peer-joined"})

                elif kind in FORWARDED_TYPES and room_code:
                    if kind in {"offer", "answer"} and not isinstance(message.get("description"), dict):
                        await hub.notify({websocket}, {"type": "error", "message": "Invalid connection description."})
                        continue
                    if kind == "candidate" and message.get("candidate") is not None and not isinstance(message.get("candidate"), dict):
                        await hub.notify({websocket}, {"type": "error", "message": "Invalid connection candidate."})
                        continue
                    room = hub.rooms.get(room_code)
                    if room:
                        await hub.notify(room.peers - {websocket}, message)
                else:
                    await hub.notify({websocket}, {"type": "error", "message": "Unsupported signaling message."})

            elif frame.type == WSMsgType.ERROR:
                break
    finally:
        hub.connections.discard(websocket)
        await hub.leave(websocket, room_code)
        await websocket.close()
    return websocket


async def expire_rooms(app: web.Application) -> None:
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        hub: SignalingHub = app[HUB_KEY]
        for address, attempts in tuple(hub.creates_by_ip.items()):
            while attempts and now - attempts[0] >= CREATE_WINDOW_SECONDS:
                attempts.popleft()
            if not attempts:
                hub.creates_by_ip.pop(address, None)
        for code, room in tuple(hub.rooms.items()):
            if room.expires_at <= now:
                await hub.notify(room.peers, {"type": "peer-left"})
                hub.rooms.pop(code, None)
                room.peers.clear()


async def start_expiration_task(app: web.Application) -> None:
    app[EXPIRY_TASK_KEY] = asyncio.create_task(expire_rooms(app))


async def stop_expiration_task(app: web.Application) -> None:
    task = app.get(EXPIRY_TASK_KEY)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> web.Application:
    app = web.Application(client_max_size=1024 * 1024, middlewares=[security_middleware])
    app[HUB_KEY] = SignalingHub()
    app.router.add_get("/healthz", health)
    app.router.add_get("/ws", websocket_handler)
    for route, (path, _content_type) in STATIC_FILES.items():
        app.router.add_get(route, static_file)
    if os.environ.get("LANTERN_ENABLE_TESTS") == "1":
        for route in TEST_FILES:
            app.router.add_get(route, static_file)
    app.on_startup.append(start_expiration_task)
    app.on_cleanup.append(stop_expiration_task)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    print(f"Lantern listening on http://0.0.0.0:{port} (Ctrl+C to stop)")
    web.run_app(create_app(), host="0.0.0.0", port=port, access_log=None)
