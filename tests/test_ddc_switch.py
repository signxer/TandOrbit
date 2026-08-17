"""DDC/CI 设备标识测试。

TandOrbit 自动模式切换不调用 DDC/CI 输入源控制，避免关闭显示器自动识别。
DDC 仅保留设备标识/其他显示器能力的测试。
"""

from __future__ import annotations

from app.events import EventBus
from plugins.ddc.plugin import DDCPlugin


class TestDDCMonitorStr:
    def test_configured_monitor_str(self, monkeypatch) -> None:
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
            def load(self):
                return _FakeCfg()

        monkeypatch.setattr(config_mod, "ConfigManager", _FakeCM)
        assert plugin._monitor_str(1) == r"\\.\DISPLAY1\Monitor0"
        assert plugin._monitor_str(2) == r"\\.\DISPLAY2\Monitor0"
        assert plugin._monitor_str(3) == r"\\.\DISPLAY3\Monitor0"
