"""Pair on loopback using real certificates and independently confirmed numbers."""
import asyncio
import json

import pytest

from app.communication.discovery import DiscoveryService
from app.communication.nearby_pairing import NearbyPairing
from app.communication.pairing import Pairing


async def _event(events: asyncio.Queue, kind: str):
    async with asyncio.timeout(3):
        while True:
            event, payload = await events.get()
            if event == kind:
                return payload
            assert event != "error", payload


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["paired", "cancelled", "invalid_signature"])
async def test_nearby_pairing_waits_for_both_devices(tmp_path, monkeypatch, outcome):
    mac = Pairing(tmp_path / "mac", "mac")
    windows = Pairing(tmp_path / "windows", "windows")
    mac_discovery, win_discovery = DiscoveryService(), DiscoveryService()
    mac_events, win_events = asyncio.Queue(), asyncio.Queue()
    initiator = NearbyPairing(mac, mac_discovery, 5001, "", lambda *event: mac_events.put_nowait(event))
    listener = NearbyPairing(windows, win_discovery, 5000, "AB:CD:EF:00:11:22",
                             lambda *event: win_events.put_nowait(event))
    await initiator.start("127.0.0.1")
    await listener.start("127.0.0.1")
    operation = asyncio.create_task(initiator.connect("127.0.0.1", win_discovery._pairing_port))
    try:
        left, right = await asyncio.gather(_event(mac_events, "compare"), _event(win_events, "compare"))
        assert left["number"] == right["number"]
        assert len(left["number"]) == 6 and left["number"].isdigit()
        await initiator.decide(True)
        assert mac.peer is None and windows.peer is None
        if outcome == "invalid_signature":
            monkeypatch.setattr(windows, "sign_confirmation", lambda _: b"invalid")
            await listener.decide(True)
            await _event(mac_events, "error")
            assert mac.peer is None
        elif outcome == "paired":
            await listener.decide(True)
            await asyncio.gather(_event(mac_events, "paired"), _event(win_events, "paired"))
            assert mac.peer["fingerprint"] == windows.offer("127.0.0.1", 5000)["fingerprint"]
            assert windows.peer["fingerprint"] == mac.offer("127.0.0.1", 5001)["fingerprint"]
            assert mac.peer["mac_address"] == "AB:CD:EF:00:11:22"
            assert mac.context() and windows.context(server=True)
        else:
            await listener.decide(False)
            assert "取消" in await _event(win_events, "error")
            assert "结束" in await _event(mac_events, "error")
            assert mac.peer is None and windows.peer is None
    finally:
        await asyncio.gather(operation, initiator.close(), listener.close(), return_exceptions=True)
    assert mac_discovery._pairing_port == win_discovery._pairing_port == 0


@pytest.mark.asyncio
async def test_changed_identity_is_rejected_before_showing_a_number(tmp_path):
    pairing = Pairing(tmp_path, "mac")
    discovery = DiscoveryService()
    events = asyncio.Queue()
    listener = NearbyPairing(pairing, discovery, 5001, "", lambda *event: events.put_nowait(event))
    await listener.start("127.0.0.1")
    reader, writer = await asyncio.open_connection("127.0.0.1", discovery._pairing_port)
    try:
        async with asyncio.timeout(3):
            await reader.readline()
            writer.write((json.dumps({"type": "commit", "version": 1, "digest": "0" * 64}) + "\n").encode())
            await writer.drain()
            await reader.readline()
            writer.write(b'{"type":"reveal","version":1,"payload":{"name":"changed"}}\n')
            await writer.drain()
            assert "身份比对失败" in await _event(events, "error")
            assert pairing.peer is None
    finally:
        writer.close()
        await writer.wait_closed()
        await listener.close()


def test_discovery_only_lists_computers_that_opened_pairing():
    discovery = DiscoveryService()
    role = "windows" if discovery._local_role == "mac" else "mac"
    message = {"magic": "TandOrbit", "role": role, "port": 5000, "name": "Other computer"}
    source = ("192.168.0.2", 5678)
    discovery._handle_broadcast(json.dumps(message).encode(), source)
    assert discovery.peer["host"] == source[0]
    assert discovery.pairing_candidates() == []
    discovery._handle_broadcast(json.dumps({**message, "pairing_port": 43210}).encode(), source)
    assert discovery.pairing_candidates()[0]["pairing_port"] == 43210
    discovery._handle_broadcast(json.dumps({**message, "pairing_port": 0}).encode(), source)
    assert discovery.pairing_candidates() == []
