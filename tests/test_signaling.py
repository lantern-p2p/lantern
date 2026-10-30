"""Integration tests for Lantern's same-origin HTTP/WebSocket service."""

from __future__ import annotations

import unittest

from aiohttp import ClientSession
from aiohttp.test_utils import TestServer

import server


class SignalingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.test_server = TestServer(server.create_app())
        await self.test_server.start_server()
        self.session = ClientSession()

    async def asyncTearDown(self) -> None:
        await self.session.close()
        await self.test_server.close()

    async def connect(self):
        origin = str(self.test_server.make_url("/")).rstrip("/")
        return await self.session.ws_connect(self.test_server.make_url("/ws"), origin=origin)

    async def receive(self, websocket):
        message = await websocket.receive_json(timeout=2)
        return message

    async def test_create_join_and_forward_signaling(self) -> None:
        async with await self.connect() as host, await self.connect() as guest:
            await host.send_json({"type": "create"})
            created = await self.receive(host)
            self.assertEqual(created["type"], "created")
            self.assertGreaterEqual(len(created["room"]), 8)

            await guest.send_json({"type": "join", "room": created["room"]})
            self.assertEqual(await self.receive(guest), {"type": "joined", "room": created["room"]})
            self.assertEqual(await self.receive(host), {"type": "peer-joined"})

            offer = {"type": "offer", "description": {"type": "offer", "sdp": "test-sdp"}}
            await host.send_json(offer)
            self.assertEqual(await self.receive(guest), offer)

    async def test_same_socket_cannot_join_its_own_room(self) -> None:
        async with await self.connect() as peer:
            await peer.send_json({"type": "create"})
            created = await self.receive(peer)
            await peer.send_json({"type": "join", "room": created["room"]})
            error = await self.receive(peer)
            self.assertEqual(error["type"], "error")

    async def test_creating_again_ends_old_room_and_notifies_guest(self) -> None:
        async with await self.connect() as host, await self.connect() as guest:
            await host.send_json({"type": "create"})
            first_room = (await self.receive(host))["room"]
            await guest.send_json({"type": "join", "room": first_room})
            await self.receive(guest)
            await self.receive(host)

            await host.send_json({"type": "create"})
            self.assertEqual(await self.receive(guest), {"type": "peer-left"})
            second_room = (await self.receive(host))["room"]
            self.assertNotEqual(first_room, second_room)

            async with await self.connect() as stranger:
                await stranger.send_json({"type": "join", "room": first_room})
                self.assertEqual((await self.receive(stranger))["type"], "error")

    async def test_requires_same_origin_and_sets_security_headers(self) -> None:
        response = await self.session.get(self.test_server.make_url("/"))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'self'", response.headers["Content-Security-Policy"])
        with self.assertRaises(Exception):
            await self.session.ws_connect(self.test_server.make_url("/ws"), origin="https://not-lantern.invalid")

    async def test_invalid_room_and_signaling_shape_are_rejected(self) -> None:
        async with await self.connect() as peer:
            await peer.send_json({"type": "join", "room": "../../etc/passwd"})
            self.assertEqual((await self.receive(peer))["type"], "error")
            await peer.send_json({"type": "create"})
            await self.receive(peer)
            await peer.send_json({"type": "offer", "description": "not-an-object"})
            self.assertEqual((await self.receive(peer))["type"], "error")

    async def test_health_is_public_but_smoke_test_is_disabled_by_default(self) -> None:
        health = await self.session.get(self.test_server.make_url("/healthz"))
        self.assertEqual(health.status, 200)
        self.assertEqual(await health.json(), {"ok": True, "service": "lantern-signaling"})
        smoke = await self.session.get(self.test_server.make_url("/tests/browser_smoke.html"))
        self.assertEqual(smoke.status, 404)


if __name__ == "__main__":
    unittest.main()
