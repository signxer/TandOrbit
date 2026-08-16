"""DDC/CI 输入源切换动作测试"""

import pytest

from app.enums import PluginStatus
from app.events import EventBus
from app.scheduler.actions import SwitchDisplayInputsAction
from plugins.ddc.plugin import DDCPlugin


class FakeDDC:
    """模拟 DDC 插件"""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.status = PluginStatus.ENABLED

    async def set_input_source(self, display_id: int, source) -> bool:
        self.calls.append((display_id, source.value))
        return True


class ErrorDDC(FakeDDC):
    async def set_input_source(self, display_id: int, source) -> bool:
        return False


class TestSwitchDisplayInputsAction:
    @pytest.mark.asyncio
    async def test_switches_inputs_for_target_mode(self) -> None:
        ddc = FakeDDC()
        input_map = {"1": {"mac": "hdmi1", "windows": "dp1"}, "2": {"mac": "dp1", "windows": "hdmi2"}}
        action = SwitchDisplayInputsAction(ddc, input_map, "mac")
        assert await action.execute() is True
        assert ddc.calls == [(1, "hdmi1"), (2, "dp1")]

    @pytest.mark.asyncio
    async def test_windows_target_uses_windows_inputs(self) -> None:
        ddc = FakeDDC()
        input_map = {"1": {"mac": "hdmi1", "windows": "dp1"}}
        action = SwitchDisplayInputsAction(ddc, input_map, "windows")
        await action.execute()
        assert ddc.calls == [(1, "dp1")]

    @pytest.mark.asyncio
    async def test_empty_map_is_noop(self) -> None:
        ddc = FakeDDC()
        action = SwitchDisplayInputsAction(ddc, {}, "mac")
        assert await action.execute() is True
        assert ddc.calls == []

    @pytest.mark.asyncio
    async def test_no_plugin_is_noop(self) -> None:
        action = SwitchDisplayInputsAction(None, {"1": {"mac": "hdmi1"}}, "mac")
        assert await action.execute() is True

    @pytest.mark.asyncio
    async def test_error_plugin_is_noop(self) -> None:
        ddc = FakeDDC()
        ddc.status = PluginStatus.ERROR
        action = SwitchDisplayInputsAction(ddc, {"1": {"mac": "hdmi1"}}, "mac")
        assert await action.execute() is True
        assert ddc.calls == []

    @pytest.mark.asyncio
    async def test_failure_does_not_fail_pipeline(self) -> None:
        ddc = ErrorDDC()
        action = SwitchDisplayInputsAction(ddc, {"1": {"mac": "hdmi1"}}, "mac")
        assert await action.execute() is True  # 尽力而为

    @pytest.mark.asyncio
    async def test_unknown_input_source_skipped(self) -> None:
        ddc = FakeDDC()
        input_map = {"1": {"mac": "not-a-source"}, "2": {"mac": "hdmi2"}}
        action = SwitchDisplayInputsAction(ddc, input_map, "mac")
        assert await action.execute() is True
        assert ddc.calls == [(2, "hdmi2")]


class TestDDCMonitorStr:
    def test_fallback_monitor_str(self, monkeypatch) -> None:
        """display_id 未配置时按 DISPLAY 编号生成"""
        plugin = DDCPlugin(EventBus(), {})

        class _FakeDisplay:
            primary_id = 1
            secondary_id = 2
            ddc_primary_monitor = r"\\.\DISPLAY1\Monitor0"
            ddc_secondary_monitor = r"\\.\DISPLAY2\Monitor0"

        class _FakeCfg:
            display = _FakeDisplay()

        import app.config as config_mod

        class _FakeCM:
            def load(self) -> _FakeCfg:
                return _FakeCfg()

        monkeypatch.setattr(config_mod, "ConfigManager", _FakeCM)
        assert plugin._monitor_str(1) == r"\\.\DISPLAY1\Monitor0"
        assert plugin._monitor_str(2) == r"\\.\DISPLAY2\Monitor0"
        assert plugin._monitor_str(3) == r"\\.\DISPLAY3\Monitor0"
