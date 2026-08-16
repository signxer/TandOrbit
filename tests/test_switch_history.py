"""切换历史记录与成功率测试（SQLite 持久化）"""

import tempfile
from pathlib import Path

import pytest

from app.config import ConfigManager
from app.controller.controller import Controller
from app.enums import Mode
from app.events import EventBus
from app.plugin_base import PluginRegistry
from app.scheduler.scheduler import Scheduler
from app.state.state_machine import StateManager


def _make_controller(tmp_path: Path) -> Controller:
    bus = EventBus()
    return Controller(
        event_bus=bus,
        state_manager=StateManager(bus),
        scheduler=Scheduler(bus),
        plugin_registry=PluginRegistry(bus),
        config_manager=ConfigManager(tmp_path / "config.yaml"),
    )


class TestSwitchHistory:
    def test_record_and_get_history(self, tmp_path: Path) -> None:
        c = _make_controller(tmp_path)
        import time

        start = time.monotonic()
        c._record_switch(Mode.MAC, Mode.WINDOWS, True, start, "")
        c._record_switch(Mode.WINDOWS, Mode.SHARE, False, start, "动作失败")

        history = c.get_switch_history()
        assert len(history) == 2
        # 最新在前
        assert history[0]["from"] == "WINDOWS"
        assert history[0]["to"] == "SHARE"
        assert history[0]["success"] is False
        assert history[0]["error"] == "动作失败"
        assert history[1]["success"] is True

    def test_success_rate(self, tmp_path: Path) -> None:
        c = _make_controller(tmp_path)
        import time

        start = time.monotonic()
        for i in range(4):
            c._record_switch(Mode.MAC, Mode.WINDOWS, i % 2 == 0, start, "")
        ok, total, rate = c.get_success_rate(20)
        assert total == 4
        assert ok == 2
        assert rate == 0.5

    def test_history_persisted_across_instances(self, tmp_path: Path) -> None:
        """重启不丢：新 Controller 实例仍能读到历史"""
        c1 = _make_controller(tmp_path)
        import time

        c1._record_switch(Mode.MAC, Mode.WINDOWS, True, time.monotonic(), "")

        c2 = _make_controller(tmp_path)  # 模拟重启
        history = c2.get_switch_history()
        assert len(history) == 1
        assert history[0]["to"] == "WINDOWS"
        assert history[0]["success"] is True

    def test_empty_history(self, tmp_path: Path) -> None:
        c = _make_controller(tmp_path)
        assert c.get_switch_history() == []
        assert c.get_success_rate(20) == (0, 0, 0.0)
