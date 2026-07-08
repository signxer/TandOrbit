"""TandOrbit 状态机

所有工作模式切换均由状态机驱动，确保状态一致性。
"""

from __future__ import annotations

from loguru import logger

from app.enums import Mode
from app.events import EventBus, ModeChangedEvent


# 合法的状态转换表
VALID_TRANSITIONS: dict[Mode, set[Mode]] = {
    Mode.UNKNOWN: {Mode.MAC, Mode.WINDOWS},
    Mode.MAC: {Mode.WINDOWS, Mode.SHARE, Mode.PRESENTATION},
    Mode.WINDOWS: {Mode.MAC, Mode.SHARE, Mode.PRESENTATION},
    Mode.SHARE: {Mode.MAC, Mode.WINDOWS, Mode.PRESENTATION},
    Mode.PRESENTATION: {Mode.MAC, Mode.WINDOWS, Mode.SHARE},
}


class StateManager:
    """状态管理器

    维护系统当前工作模式，管理状态转换。
    禁止插件直接保存状态，所有状态由 StateManager 统一管理。
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._current_mode: Mode = Mode.UNKNOWN
        self._target_mode: Mode | None = None
        self._transitioning: bool = False
        self._event_bus = event_bus
        self._history: list[tuple[Mode, Mode]] = []

    @property
    def current_mode(self) -> Mode:
        return self._current_mode

    @property
    def target_mode(self) -> Mode | None:
        return self._target_mode

    @property
    def is_transitioning(self) -> bool:
        return self._transitioning

    def can_transition(self, target: Mode) -> bool:
        """检查是否可以转换到目标状态"""
        if self._transitioning:
            logger.warning("State is transitioning, cannot switch")
            return False
        valid = VALID_TRANSITIONS.get(self._current_mode, set())
        return target in valid

    def set_target(self, target: Mode) -> bool:
        """设置目标状态"""
        if not self.can_transition(target):
            logger.error(
                f"Invalid transition: {self._current_mode.name} -> {target.name}"
            )
            return False
        self._target_mode = target
        logger.info(f"Target mode set: {target.name}")
        return True

    def begin_transition(self) -> bool:
        """开始状态转换"""
        if self._target_mode is None:
            logger.error("No target mode set")
            return False
        if self._transitioning:
            logger.warning("Already transitioning")
            return False
        self._transitioning = True
        logger.info(
            f"Transitioning: {self._current_mode.name} -> {self._target_mode.name}"
        )
        return True

    def commit_transition(self) -> None:
        """提交状态转换（成功完成）"""
        if self._target_mode is None:
            return
        old_mode = self._current_mode
        self._current_mode = self._target_mode
        self._target_mode = None
        self._transitioning = False
        self._history.append((old_mode, self._current_mode))
        logger.info(f"State committed: {old_mode.name} -> {self._current_mode.name}")
        self._event_bus.publish(
            ModeChangedEvent(
                old_mode=old_mode.name,
                new_mode=self._current_mode.name,
                source="StateManager",
            )
        )

    def rollback_transition(self) -> None:
        """回滚状态转换（失败恢复）"""
        if self._target_mode is None:
            return
        logger.warning(
            f"Rolling back transition: staying at {self._current_mode.name}"
        )
        self._target_mode = None
        self._transitioning = False

    def force_set(self, mode: Mode) -> None:
        """强制设置状态（仅用于初始化或异常恢复）"""
        old = self._current_mode
        self._current_mode = mode
        self._target_mode = None
        self._transitioning = False
        logger.warning(f"Force set mode: {old.name} -> {mode.name}")
        self._event_bus.publish(
            ModeChangedEvent(old_mode=old.name, new_mode=mode.name, source="StateManager")
        )

    def get_history(self) -> list[tuple[Mode, Mode]]:
        """获取状态转换历史"""
        return list(self._history)
