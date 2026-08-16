"""DDC/CI 输入源切换与读回验证动作测试"""

from __future__ import annotations

import pytest

from app.enums import InputSource, PluginStatus
from app.events import EventBus
from app.scheduler.actions import SwitchDisplayInputsAction, VerifyDisplayInputsAction
from plugins.ddc.plugin import DDCPlugin


class FakeDDC:
    """模拟 DDC 插件"""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.status = PluginStatus.ENABLED
        self.inputs: dict[int, str] = {}  # 当前输入源（模拟读回）

    async def set_input_source(self, display_id: int, source) -> bool:
        self.calls.append((display_id, source.value))
        self.inputs[display_id] = source.value
        return True

    async def get_input_source(self, display_id: int) -> InputSource | None:
        value = self.inputs.get(display_id)
        if value is None:
            return None
        return InputSource(value)


class UnreadableDDC(FakeDDC):
    """模拟不支持读回输入源的显示器"""

    async def get_input_source(self, display_id: int) -> InputSource | None:
        return None


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


class TestVerifyDisplayInputsAction:
    """DDC 输入源读回验证"""

    @pytest.mark.asyncio
    async def test_verifies_after_switch(self) -> None:
        ddc = FakeDDC()
        input_map = {"1": {"mac": "hdmi1", "windows": "dp1"}}
        action = VerifyDisplayInputsAction(ddc, input_map, "mac")
        assert await action.execute() is True  # 读回与预期一致

    @pytest.mark.asyncio
    async def test_retries_when_mismatch_then_succeeds(self) -> None:
        ddc = FakeDDC()
        # 第一次 set 后输入仍是旧的（模拟切换延迟），验证重试后成功
        ddc.inputs = {1: "dp1"}
        input_map = {"1": {"mac": "hdmi1"}}

        class SlowDDC(FakeDDC):
            async def set_input_source(self, display_id, source) -> bool:
                ok = await super().set_input_source(display_id, source)
                return ok

        # 重试时 set 会更新 inputs → 第二次读回成功
        action = VerifyDisplayInputsAction(ddc, input_map, "mac", max_attempts=3, interval=0.0)
        assert await action.execute() is True

    @pytest.mark.asyncio
    async def test_unreadable_display_passes(self) -> None:
        # 显示器不支持读回 → 不误报失败
        ddc = UnreadableDDC()
        input_map = {"1": {"mac": "hdmi1"}}
        action = VerifyDisplayInputsAction(ddc, input_map, "mac")
        assert await action.execute() is True

    @pytest.mark.asyncio
    async def test_noop_without_map(self) -> None:
        ddc = FakeDDC()
        assert await VerifyDisplayInputsAction(ddc, {}, "mac").execute() is True
        assert await VerifyDisplayInputsAction(None, {"1": {"mac": "hdmi1"}}, "mac").execute() is True
