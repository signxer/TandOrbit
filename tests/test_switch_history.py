"""切换历史记录与成功率测试"""

import pytest

from app.config import ConfigManager
from app.controller.controller import Controller
from app.enums import Mode
from app.events import EventBus
from app.plugin_base import PluginRegistry
from app.scheduler.scheduler import Scheduler
from app.state.state_machine import StateManager


def _make_controller() -> Controller:
    bus = EventBus()
    return Controller(
        event_bus=bus,
        state_manager=StateManager(bus),
        scheduler=Scheduler(bus),
        plugin_registry=PluginRegistry(bus),
        config_manager=ConfigManager(),
    )


class TestSwitchHistory:
    def test_record_and_get_history(self) -> None:
        c = _make_controller()
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

    def test_success_rate(self) -> None:
        c = _make_controller()
        import time

        start = time.monotonic()
        for i in range(4):
            c._record_switch(Mode.MAC, Mode.WINDOWS, i % 2 == 0, start, "")
        ok, total, rate = c.get_success_rate(20)
        assert total == 4
        assert ok == 2
        assert rate == 0.5

    def test_history_capped_at_100(self) -> None:
        c = _make_controller()
        import time

        start = time.monotonic()
        for i in range(120):
            c._record_switch(Mode.MAC, Mode.WINDOWS, True, start, "")
        assert len(c.get_switch_history()) == 100

    def test_empty_history(self) -> None:
        c = _make_controller()
        assert c.get_switch_history() == []
        assert c.get_success_rate(20) == (0, 0, 0.0)
