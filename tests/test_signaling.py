"""Integration tests for Lantern's local WebSocket signaling server."""

from __future__ import annotations

import asyncio
import json
import unittest

import websockets

import server


class SignalingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = await websockets.serve(server.signaling, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self) -> None:
        self.server.close()
        await self.server.wait_closed()
        await asyncio.sleep(0)

    async def connect(self):
        return await websockets.connect(f"ws://127.0.0.1:{self.port}")

    async def receive(self, websocket):
        return json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))

    async def test_create_join_and_forward_signaling(self) -> None:
        async with await self.connect() as host, await self.connect() as guest:
            await host.send(json.dumps({"type": "create"}))
            created = await self.receive(host)
            self.assertEqual(created["type"], "created")

            await guest.send(json.dumps({"type": "join", "room": created["room"]}))
            joined = await self.receive(guest)
            self.assertEqual(joined, {"type": "joined", "room": created["room"]})
            self.assertEqual(await self.receive(host), {"type": "peer-joined"})

            offer = {"type": "offer", "description": {"type": "offer", "sdp": "test-sdp"}}
            await host.send(json.dumps(offer))
            self.assertEqual(await self.receive(guest), offer)

    async def test_same_socket_cannot_join_its_own_room(self) -> None:
        async with await self.connect() as peer:
            await peer.send(json.dumps({"type": "create"}))
            created = await self.receive(peer)
            await peer.send(json.dumps({"type": "join", "room": created["room"]}))
            error = await self.receive(peer)
            self.assertEqual(error["type"], "error")
            self.assertIn("second browser", error["message"])

    async def test_creating_again_expires_old_room_and_notifies_guest(self) -> None:
        async with await self.connect() as host, await self.connect() as guest, await self.connect() as stranger:
            await host.send(json.dumps({"type": "create"}))
            first_room = (await self.receive(host))["room"]
            await guest.send(json.dumps({"type": "join", "room": first_room}))
            await self.receive(guest)
            await self.receive(host)

            await host.send(json.dumps({"type": "create"}))
            self.assertEqual(await self.receive(guest), {"type": "peer-left"})
            second_room = (await self.receive(host))["room"]
            self.assertNotEqual(first_room, second_room)

            await stranger.send(json.dumps({"type": "join", "room": first_room}))
            self.assertEqual((await self.receive(stranger))["type"], "error")


if __name__ == "__main__":
    unittest.main()
