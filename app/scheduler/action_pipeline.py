"""TandOrbit 动作管道

所有模式切换均采用 Pipeline 执行，禁止 if-else。
支持动作失败时自动 Rollback。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from app.enums import ActionStatus
from app.events import ActionCompletedEvent, EventBus


class Action(ABC):
    """动作基类"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.status = ActionStatus.PENDING
        self.error: str = ""
        self.duration_ms: float = 0.0

    @abstractmethod
    async def execute(self) -> bool:
        """执行动作，返回是否成功"""
        ...

    @abstractmethod
    async def rollback(self) -> bool:
        """回滚动作，返回是否成功"""
        ...


class ActionPipeline:
    """动作管道

    按顺序执行一组动作，失败时自动回滚已执行的动作。
    """

    def __init__(self, name: str, event_bus: EventBus) -> None:
        self.name = name
        self._actions: list[Action] = []
        self._executed: list[Action] = []
        self._event_bus = event_bus

    def add_action(self, action: Action) -> ActionPipeline:
        """添加动作到管道（链式调用）"""
        self._actions.append(action)
        return self

    async def execute(self) -> bool:
        """执行整个管道

        Returns:
            bool: 是否全部成功
        """
        logger.info(f"Pipeline [{self.name}] started with {len(self._actions)} actions")
        start_time = time.monotonic()

        for action in self._actions:
            action_start = time.monotonic()
            action.status = ActionStatus.RUNNING
            logger.info(f"Pipeline [{self.name}] executing: {action.name}")

            try:
                success = await action.execute()
                action.duration_ms = (time.monotonic() - action_start) * 1000

                if success:
                    action.status = ActionStatus.SUCCESS
                    self._executed.append(action)
                    logger.info(
                        f"Pipeline [{self.name}] action {action.name} succeeded "
                        f"({action.duration_ms:.1f}ms)"
                    )
                    self._event_bus.publish(
                        ActionCompletedEvent(
                            action_name=action.name,
                            success=True,
                            source=self.name,
                        )
                    )
                else:
                    action.status = ActionStatus.FAILED
                    logger.error(f"Pipeline [{self.name}] action {action.name} failed")
                    self._event_bus.publish(
                        ActionCompletedEvent(
                            action_name=action.name,
                            success=False,
                            error=action.error,
                            source=self.name,
                        )
                    )
                    await self._rollback()
                    return False

            except Exception as e:
                action.status = ActionStatus.FAILED
                action.error = str(e)
                action.duration_ms = (time.monotonic() - action_start) * 1000
                logger.error(
                    f"Pipeline [{self.name}] action {action.name} exception: {e}"
                )
                self._event_bus.publish(
                    ActionCompletedEvent(
                        action_name=action.name,
                        success=False,
                        error=str(e),
                        source=self.name,
                    )
                )
                await self._rollback()
                return False

        total_ms = (time.monotonic() - start_time) * 1000
        logger.info(f"Pipeline [{self.name}] completed successfully ({total_ms:.1f}ms)")
        return True

    async def _rollback(self) -> None:
        """回滚已执行的动作（逆序）"""
        logger.warning(f"Pipeline [{self.name}] rolling back {len(self._executed)} actions")
        for action in reversed(self._executed):
            try:
                logger.info(f"Pipeline [{self.name}] rolling back: {action.name}")
                ok = await action.rollback()
                if ok:
                    action.status = ActionStatus.ROLLED_BACK
                    logger.info(f"Pipeline [{self.name}] rolled back: {action.name}")
                else:
                    logger.error(
                        f"Pipeline [{self.name}] rollback failed: {action.name}"
                    )
            except Exception as e:
                logger.error(
                    f"Pipeline [{self.name}] rollback exception for {action.name}: {e}"
                )
        self._executed.clear()
