"""TandOrbit 调度器

负责模式切换的动作编排和执行。
"""

from __future__ import annotations

from loguru import logger

from app.enums import Mode
from app.events import EventBus
from app.scheduler.action_pipeline import Action, ActionPipeline


class Scheduler:
    """调度器

    负责根据当前状态和目标状态，编排和执行动作序列。
    所有模式切换均通过 Pipeline 执行。
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._action_factories: dict[tuple[Mode, Mode], list[type[Action]]] = {}

    def register_transition(
        self, from_mode: Mode, to_mode: Mode, actions: list[type[Action]]
    ) -> None:
        """注册状态转换对应的动作序列"""
        self._action_factories[(from_mode, to_mode)] = actions
        logger.debug(
            f"Registered transition: {from_mode.name} -> {to_mode.name} "
            f"with {len(actions)} actions"
        )

    def build_pipeline(self, from_mode: Mode, to_mode: Mode) -> ActionPipeline | None:
        """构建动作管道"""
        key = (from_mode, to_mode)
        action_classes = self._action_factories.get(key)
        if action_classes is None:
            logger.error(f"No actions registered for {from_mode.name} -> {to_mode.name}")
            return None

        pipeline = ActionPipeline(
            name=f"{from_mode.name}_to_{to_mode.name}",
            event_bus=self._event_bus,
        )
        for cls in action_classes:
            pipeline.add_action(cls())
        return pipeline
