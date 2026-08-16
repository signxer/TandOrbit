"""显示器拓扑验证逻辑测试（verify_display_mode 真实校验）"""

import pytest

from app.events import EventBus
from app.models import DisplayInfo
from plugins.multimonitortool.plugin import MultiMonitorToolPlugin


class FakeMultiMonitorTool(MultiMonitorToolPlugin):
    """假插件：用固定显示器列表代替真实枚举"""

    def __init__(self, displays: list[DisplayInfo]) -> None:
        super().__init__(EventBus(), {})
        self._displays = displays

    async def list_displays(self) -> list[DisplayInfo]:
        return self._displays


def _d(display_id: int, enabled: bool, primary: bool = False) -> DisplayInfo:
    return DisplayInfo(
        id=display_id,
        name=f"DISPLAY{display_id}",
        is_primary=primary,
        is_enabled=enabled,
    )


class TestVerifyDisplayMode:
    """verify_display_mode 应按真实枚举结果判断，而不是恒真"""

    @pytest.mark.asyncio
    async def test_extend_both_enabled(self) -> None:
        plugin = FakeMultiMonitorTool([_d(1, True, primary=True), _d(2, True)])
        assert await plugin.verify_display_mode("extend", 1, 2) is True

    @pytest.mark.asyncio
    async def test_extend_primary_disabled_fails(self) -> None:
        plugin = FakeMultiMonitorTool([_d(1, False, primary=True), _d(2, True)])
        assert await plugin.verify_display_mode("extend", 1, 2) is False

    @pytest.mark.asyncio
    async def test_extend_secondary_disabled_fails(self) -> None:
        plugin = FakeMultiMonitorTool([_d(1, True, primary=True), _d(2, False)])
        assert await plugin.verify_display_mode("extend", 1, 2) is False

    @pytest.mark.asyncio
    async def test_extend_primary_missing_fails(self) -> None:
        plugin = FakeMultiMonitorTool([_d(2, True)])
        assert await plugin.verify_display_mode("extend", 1, 2) is False

    @pytest.mark.asyncio
    async def test_share_primary_disabled_secondary_enabled(self) -> None:
        plugin = FakeMultiMonitorTool([_d(1, False, primary=True), _d(2, True)])
        assert await plugin.verify_display_mode("share", 1, 2) is True

    @pytest.mark.asyncio
    async def test_share_primary_still_enabled_fails(self) -> None:
        plugin = FakeMultiMonitorTool([_d(1, True, primary=True), _d(2, True)])
        assert await plugin.verify_display_mode("share", 1, 2) is False

    @pytest.mark.asyncio
    async def test_share_secondary_disabled_fails(self) -> None:
        plugin = FakeMultiMonitorTool([_d(1, False, primary=True), _d(2, False)])
        assert await plugin.verify_display_mode("share", 1, 2) is False

    @pytest.mark.asyncio
    async def test_share_secondary_missing_fails(self) -> None:
        plugin = FakeMultiMonitorTool([_d(1, False, primary=True)])
        assert await plugin.verify_display_mode("share", 1, 2) is False

    @pytest.mark.asyncio
    async def test_unknown_mode_fails(self) -> None:
        plugin = FakeMultiMonitorTool([_d(1, True, primary=True), _d(2, True)])
        assert await plugin.verify_display_mode("clone", 1, 2) is False
