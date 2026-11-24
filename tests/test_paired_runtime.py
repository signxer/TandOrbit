from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

pytestmark = pytest.mark.asyncio

from app.communication.mac_client import MacClient
from app.communication.pairing import Pairing
from app.controller.controller import Controller
from app.enums import Mode
from app.events import EventBus
from app.native_input import NativeInput
from app.plugin_base import PluginRegistry
from app.runtime import Runtime
from app.scheduler.scheduler import Scheduler
from app.sharing import ShareSession
from tests.test_transactions import participant


class FakeInput(NativeInput):
    available = True

    def __init__(self):
        super().__init__()
        self.events = []
        self.geometry((0, 0, 100, 100))

    def start(self, callback):
        super().start(callback)
        self.available = True

    def pointer(self):
        return self._pointer

    def move_cursor(self, x, y):
        self._pointer = (x, y)

    def inject(self, event):
        self.events.append(event)
        return True


def _free_ports():
    with socket.socket() as mac, socket.socket() as windows:
        mac.bind(("127.0.0.1", 0))
        windows.bind(("127.0.0.1", 0))
        return {"mac": mac.getsockname()[1], "windows": windows.getsockname()[1]}


async def until(condition):
    for _ in range(100):
        if condition():
            return
        await asyncio.sleep(0.05)
    assert condition()


@pytest.mark.parametrize("controller_role", ["windows", "mac"])
async def test_two_paired_agents_switch_and_share(tmp_path, controller_role):
    try:
        ports = _free_ports()
    except PermissionError:
        pytest.skip("local socket binding disabled by execution sandbox")
    nodes = {}
    clips = {"mac": [], "windows": []}
    for role in ports:
        fake = participant(tmp_path, role)
        config = fake.config
        config.update({role: {"port": ports[role]},
                       "sharing": {"clipboard_enabled": True, "controller": controller_role}})
        events = EventBus()
        registry = PluginRegistry(events)
        registry._plugins["betterdisplay" if role == "mac" else "multimonitortool"] = fake.output.display
        controller = Controller(events, fake.state, Scheduler(events), registry, config)
        pairing = Pairing(config.data_dir, role)
        native = FakeInput()
        sharing = ShareSession(role, config, native, clips[role].append, lambda _record: None)
        nodes[role] = Runtime(controller, role, pairing, fake.output.power, lambda _record: None, sharing)

    mac, win = nodes["mac"], nodes["windows"]
    for local, remote in ((mac, win), (win, mac)):
        local.pairing.trust(remote.pairing.offer("127.0.0.1", ports[remote.role]))
        await local.start()
    try:
        await until(lambda: all(node.server.started for node in nodes.values()))
        assert await mac.online() and await win.online()

        unknown = Pairing(tmp_path / "unknown", "mac")
        unknown.trust(win.pairing.offer("127.0.0.1", ports["windows"]))
        unpaired = MacClient("127.0.0.1", ports["windows"], tls=unknown.context())
        try:
            with pytest.raises(httpx.TransportError):
                await unpaired.request("GET", "/api/health")
        finally:
            await unpaired.close()

        assert await win.switch(Mode.SHARE)
        assert mac.controller.current_mode == win.controller.current_mode == Mode.SHARE
        await until(lambda: win.sharing._ready("input") and mac.sharing._ready("input"))
        source, target = (win, mac) if controller_role == "windows" else (mac, win)
        source.sharing._input({"kind": "move", "x": 99, "y": 50, "dx": 2, "dy": 0})
        await until(lambda: source.sharing._owned)
        source.sharing._input({"kind": "key", "code": 11, "down": True})
        await until(lambda: bool(target.sharing.native.events))
        await until(lambda: source.sharing._clipboard_armed and target.sharing._clipboard_armed)
        source.sharing._clipboard("跨机 clipboard 🛰️")
        await until(lambda: clips[target.role] == ["跨机 clipboard 🛰️"])
        target.sharing._clipboard("跨机 clipboard 🛰️")
        target.sharing._clipboard("a" * (64 * 1024 + 1))
        await asyncio.sleep(0.1)
        assert clips[source.role] == []
        target.sharing._clipboard("文本返回")
        await until(lambda: clips[source.role] == ["文本返回"])
        await source.sharing.close()
        await until(lambda: target.sharing.native.events[-1] == {"kind": "key", "code": 11, "down": False})
    finally:
        await asyncio.gather(*(node.close() for node in nodes.values()))


async def test_wol_packet_with_no_agent_times_out(tmp_path):
    fake = participant(tmp_path, "mac")
    events = EventBus()
    registry = PluginRegistry(events)
    controller = Controller(events, fake.state, Scheduler(events), registry, fake.config)
    pairing = Pairing(fake.config.data_dir, "mac")
    windows = Pairing(tmp_path / "win", "windows")
    pairing.trust(windows.offer("127.0.0.1", 5000, "AB:CD:EF:00:11:22"))
    runtime = Runtime(controller, "mac", pairing, fake.output.power, lambda _record: None)
    sent = []

    async def wake(address):
        sent.append(address)
        return True

    from types import SimpleNamespace
    registry._plugins["wol"] = SimpleNamespace(wake=wake)
    with pytest.raises(RuntimeError, match="未在"):
        await runtime.wake_windows(timeout=0)
    assert sent == ["AB:CD:EF:00:11:22"]
