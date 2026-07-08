"""TandOrbit 控制器

唯一入口，负责参数检查、状态检查、调度 Scheduler。
不负责业务逻辑。
"""

from __future__ import annotations

from loguru import logger

from app.config import ConfigManager
from app.enums import Mode
from app.events import EventBus
from app.plugin_base import PluginRegistry
from app.scheduler.scheduler import Scheduler
from app.state.state_machine import StateManager


class Controller:
    """控制器

    所有操作的唯一入口。
    GUI → Controller → Scheduler → Actions → Plugins
    """

    def __init__(
        self,
        event_bus: EventBus,
        state_manager: StateManager,
        scheduler: Scheduler,
        plugin_registry: PluginRegistry,
        config_manager: ConfigManager,
    ) -> None:
        self._event_bus = event_bus
        self._state = state_manager
        self._scheduler = scheduler
        self._plugins = plugin_registry
        self._config = config_manager

    @property
    def current_mode(self) -> Mode:
        return self._state.current_mode

    @property
    def is_transitioning(self) -> bool:
        return self._state.is_transitioning

    async def switch_mode(self, target: Mode) -> bool:
        """切换工作模式

        Args:
            target: 目标模式

        Returns:
            bool: 是否切换成功
        """
        logger.info(f"Controller: switch_mode({target.name})")

        # 1. 检查是否可以转换
        if not self._state.can_transition(target):
            logger.error(
                f"Cannot transition: {self._state.current_mode.name} -> {target.name}"
            )
            return False

        # 2. 设置目标状态
        if not self._state.set_target(target):
            return False

        # 3. 构建管道
        pipeline = self._scheduler.build_pipeline(self._state.current_mode, target)
        if pipeline is None:
            logger.error("Failed to build pipeline")
            self._state.rollback_transition()
            return False

        # 4. 开始转换
        if not self._state.begin_transition():
            self._state.rollback_transition()
            return False

        # 5. 执行管道
        success = await pipeline.execute()

        # 6. 提交或回滚
        if success:
            self._state.commit_transition()
            logger.info(f"Mode switched to {target.name}")
        else:
            self._state.rollback_transition()
            logger.error(f"Failed to switch to {target.name}, rolled back")

        return success

    async def get_system_status(self) -> dict[str, object]:
        """获取系统状态"""
        health = await self._plugins.health_check_all()
        return {
            "current_mode": self._state.current_mode.name,
            "is_transitioning": self._state.is_transitioning,
            "plugins_health": health,
            "config_display_primary": self._config.config.display.primary_id,
            "config_display_secondary": self._config.config.display.secondary_id,
        }

    async def initialize(self) -> bool:
        """初始化系统"""
        logger.info("Controller: initializing system")
        self._config.load()
        ok = await self._plugins.initialize_all()
        if ok:
            await self._plugins.enable_all()
        return ok

    async def shutdown(self) -> None:
        """关闭系统"""
        logger.info("Controller: shutting down system")
        await self._plugins.shutdown_all()
