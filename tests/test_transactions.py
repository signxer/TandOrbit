from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.asyncio

from app.config import ConfigManager
from app.display_modes import DisplayModes
from app.enums import Mode
from app.events import EventBus
from app.models import DisplayInfo
from app.state.state_machine import StateManager
from app.transition import LocalParticipant, ModeCoordinator, TransitionError, TransitionJournal


class FakePower:
    session_active = True
    windows_awake = True

    def __init__(self, on=True):
        self.on = on

    async def read(self):
        return self.on

    async def set(self, value):
        self.on = value


class FakeDisplay:
    def __init__(self, enabled=(True, True), prefix="device"):
        self.monitors = [DisplayInfo(id=i, name="Same model", device_id=f"{prefix}:{i}", is_enabled=flag)
                         for i, flag in enumerate(enabled, 1)]
        self.changes = []

    async def list_displays(self):
        return [monitor.model_copy() for monitor in self.monitors]

    async def enable_display(self, display_id):
        self.changes.append((display_id, True))
        next(m for m in self.monitors if m.id == display_id).is_enabled = True
        return True

    async def disable_display(self, display_id):
        self.changes.append((display_id, False))
        next(m for m in self.monitors if m.id == display_id).is_enabled = False
        return True

    async def is_mirrored(self):
        return False


def participant(tmp_path, role, source=Mode.MAC):
    cfg = ConfigManager(tmp_path / role / "config.yaml")
    power = FakePower(source == Mode.SHARE or source.name.lower() == role)
    enabled = ((True, False) if role == "mac" else (False, True)) if source == Mode.SHARE else (True, True)
    display = FakeDisplay(enabled, role)
    outlet = DisplayModes(role, cfg, display, power)
    state = StateManager(EventBus())
    state.force_set(source)
    journal = TransitionJournal(cfg.data_dir / "state.db")
    return LocalParticipant(journal, outlet, state, cfg)


@pytest.mark.parametrize(("source", "target"), [(s, t) for s in (Mode.MAC, Mode.WINDOWS, Mode.SHARE)
                                                for t in (Mode.MAC, Mode.WINDOWS, Mode.SHARE) if s != t])
async def test_switch_directions(source, target, tmp_path):
    mac, win = (participant(tmp_path, role, source) for role in ("mac", "windows"))
    seen = []

    async def peer(record, phase):
        assert mac.state.current_mode == source
        if phase == "commit":
            assert win.state.current_mode == source
        response = await win.step(record["id"], record["target"], phase, record["share_role"])
        if phase == "activate":
            # Both target outputs are ready before either side performs release.
            if target != Mode.MAC:
                assert win.output.power.on
            if target != Mode.WINDOWS:
                assert mac.output.power.on
        return response

    service = ModeCoordinator(mac.journal, mac, peer, seen.append, lambda _record: None)
    operation = service.submit(target.name)
    await service._task
    assert mac.state.current_mode == win.state.current_mode == target
    assert mac.config.config.last_mode == win.config.config.last_mode == target.name
    assert seen[-1]["phase"] == "committed"
    assert service.status(operation["id"])["phase"] == "committed"
    assert service.submit(target.name, operation["id"])["id"] == operation["id"]


async def test_rollback_and_resume_commit(tmp_path):
    mac, win = (participant(tmp_path, role) for role in ("mac", "windows"))
    fail_verify = True
    drop_ack = True

    async def peer(record, phase):
        nonlocal drop_ack
        if fail_verify and phase == "verify":
            raise TransitionError("remote rejected")
        response = await win.step(record["id"], record["target"], phase, record["share_role"])
        if phase == "commit" and drop_ack:
            drop_ack = False
            raise OSError("ack lost")
        return response

    service = ModeCoordinator(mac.journal, mac, peer, lambda _record: None, lambda _record: None)
    first = service.submit("SHARE")
    await service._task
    assert service.status(first["id"])["phase"] == "restored"
    assert mac.state.current_mode == win.state.current_mode == Mode.MAC
    assert all(m.is_enabled for m in mac.output.display.monitors)
    assert win.output.power.on is False

    fail_verify = False
    second = service.submit("SHARE")
    await service._task
    assert service.status(second["id"])["phase"] == "decision_commit"
    assert mac.state.current_mode == Mode.MAC
    assert win.state.current_mode == Mode.SHARE
    with pytest.raises(TransitionError, match="待恢复"):
        service.submit("WINDOWS")
    restarted = ModeCoordinator(mac.journal, mac, peer, lambda _record: None, lambda _record: None)
    await restarted.recover()
    assert restarted.status(second["id"])["phase"] == "committed"
    assert mac.state.current_mode == win.state.current_mode == Mode.SHARE


async def test_queue_is_bounded_and_stable_identity(tmp_path):
    mac, win = (participant(tmp_path, role) for role in ("mac", "windows"))
    win.config.update({"display": {"windows_primary_monitor_id": "windows:1",
                                   "windows_secondary_monitor_id": "windows:2"}})
    win.output.display.monitors[0].id = 17
    win.output.display.monitors[1].id = 19
    ready = asyncio.Event()

    async def peer(record, phase):
        await ready.wait()
        return await win.step(record["id"], record["target"], phase, record["share_role"])

    service = ModeCoordinator(mac.journal, mac, peer, lambda _record: None, lambda _record: None)
    first = service.submit("SHARE")
    assert service.submit("SHARE")["id"] == first["id"]
    queued = service.submit("WINDOWS")
    with pytest.raises(TransitionError, match="排队"):
        service.submit("MAC")
    ready.set()
    await service._task
    assert service.status(queued["id"])["phase"] == "committed"
    assert (17, False) in win.output.display.changes
    assert (17, True) in win.output.display.changes


async def test_unconfirmed_recovery_stops_new_operations(tmp_path):
    mac, win = (participant(tmp_path, role) for role in ("mac", "windows"))
    offline = True

    async def peer(record, phase):
        if offline and phase in ("verify", "restore"):
            raise OSError("offline")
        return await win.step(record["id"], record["target"], phase, record["share_role"])

    service = ModeCoordinator(mac.journal, mac, peer, lambda _record: None, lambda _record: None)
    operation = service.submit("SHARE")
    await service._task
    assert service.status(operation["id"])["phase"] == "recovering"
    with pytest.raises(TransitionError, match="待恢复"):
        service.submit("WINDOWS")
    offline = False
    await service.recover()
    assert service.status(operation["id"])["phase"] == "restored"
