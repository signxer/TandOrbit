"""端到端远端状态验证测试（Controller._verify_remote_state）"""

import pytest

from app.communication.mac_client import MacClient
from app.config import ConfigManager
from app.controller.controller import Controller
from app.enums import Mode
from app.events import EventBus
from app.models import DisplayInfo
from app.plugin_base import PluginRegistry
from app.scheduler.scheduler import Scheduler
from app.state.state_machine import StateManager


class FakeWinClient:
    """模拟 Windows Agent 客户端（list_displays 返回固定列表）"""

    def __init__(self, displays: list[DisplayInfo]) -> None:
        self.host = "192.168.1.100"
        self.port = 5000
        self._displays = displays

    async def list_displays(self) -> list[DisplayInfo]:
        return self._displays

    async def set_mode(self, mode_name: str) -> bool:
        return True


def _make_controller(displays: list[DisplayInfo]) -> Controller:
    bus = EventBus()
    controller = Controller(
        event_bus=bus,
        state_manager=StateManager(bus),
        scheduler=Scheduler(bus),
        plugin_registry=PluginRegistry(bus),
        config_manager=ConfigManager(),
    )
    controller._win_client = FakeWinClient(displays)  # type: ignore[assignment]
    return controller


def _d(display_id: int, enabled: bool, primary: bool = False) -> DisplayInfo:
    return DisplayInfo(
        id=display_id,
        name=f"DISPLAY{display_id}",
        is_primary=primary,
        is_enabled=enabled,
    )


class TestVerifyRemoteState:
    """Mac 端对 Windows 远端显示器拓扑的端到端验证"""

    @pytest.mark.asyncio
    async def test_windows_mode_both_enabled_ok(self) -> None:
        c = _make_controller([_d(1, True, primary=True), _d(2, True)])
        assert await c._verify_remote_state(Mode.WINDOWS) is True

    @pytest.mark.asyncio
    async def test_windows_mode_primary_disabled_fails(self) -> None:
        c = _make_controller([_d(1, False, primary=True), _d(2, True)])
        assert await c._verify_remote_state(Mode.WINDOWS) is False

    @pytest.mark.asyncio
    async def test_windows_mode_secondary_disabled_fails(self) -> None:
        c = _make_controller([_d(1, True, primary=True), _d(2, False)])
        assert await c._verify_remote_state(Mode.WINDOWS) is False

    @pytest.mark.asyncio
    async def test_share_mode_ok(self) -> None:
        c = _make_controller([_d(1, False, primary=True), _d(2, True)])
        assert await c._verify_remote_state(Mode.SHARE) is True

    @pytest.mark.asyncio
    async def test_share_mode_primary_still_enabled_fails(self) -> None:
        c = _make_controller([_d(1, True, primary=True), _d(2, True)])
        assert await c._verify_remote_state(Mode.SHARE) is False

    @pytest.mark.asyncio
    async def test_share_mode_secondary_missing_fails(self) -> None:
        c = _make_controller([_d(1, False, primary=True)])
        assert await c._verify_remote_state(Mode.SHARE) is False

    @pytest.mark.asyncio
    async def test_mac_mode_skips_verification(self) -> None:
        # MAC 模式无法读取电源状态，直接视为通过
        c = _make_controller([])
        assert await c._verify_remote_state(Mode.MAC) is True


class TestPostSyncAndVerify:
    """后同步 + 验证：远端在线时通过，失败时重试后仍失败则返回 False"""

    @pytest.mark.asyncio
    async def test_verify_passes(self) -> None:
        c = _make_controller([_d(1, True, primary=True), _d(2, True)])
        assert await c._post_sync_and_verify(Mode.WINDOWS) is True

    @pytest.mark.asyncio
    async def test_verify_fails_after_retries(self) -> None:
        # 远端状态始终不符合（主屏禁用），重试后仍失败
        c = _make_controller([_d(1, False, primary=True), _d(2, True)])
        assert await c._post_sync_and_verify(Mode.WINDOWS, max_attempts=2, interval=0.0) is False
        assert "远端显示器状态验证失败" in c.last_error
