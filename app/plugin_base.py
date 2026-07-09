"""TandOrbit 插件基类

所有系统能力采用插件化设计，统一接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from app.enums import PluginStatus
from app.events import EventBus


class Plugin(ABC):
    """插件基类

    所有插件必须实现此接口。
    """

    def __init__(self, name: str, event_bus: EventBus, config: dict[str, Any] | None = None) -> None:
        self.name = name
        self.event_bus = event_bus
        self.config = config or {}
        self._status = PluginStatus.REGISTERED
        self._init_error: str = ""

    @property
    def status(self) -> PluginStatus:
        return self._status

    @abstractmethod
    async def initialize(self) -> bool:
        """初始化插件"""
        ...

    @abstractmethod
    async def enable(self) -> bool:
        """启用插件"""
        ...

    @abstractmethod
    async def disable(self) -> bool:
        """禁用插件"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭插件"""
        ...

    def _set_status(self, status: PluginStatus) -> None:
        old = self._status
        self._status = status
        logger.debug(f"Plugin {self.name}: {old.name} -> {status.name}")


class PluginRegistry:
    """插件注册表

    管理所有插件的注册、初始化和生命周期。
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._event_bus = event_bus

    def register(self, plugin: Plugin) -> None:
        """注册插件"""
        if plugin.name in self._plugins:
            logger.warning(f"Plugin {plugin.name} already registered, replacing")
        self._plugins[plugin.name] = plugin
        logger.info(f"Registered plugin: {plugin.name}")

    def unregister(self, name: str) -> None:
        """注销插件"""
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"Unregistered plugin: {name}")

    def get(self, name: str) -> Plugin | None:
        """获取插件"""
        return self._plugins.get(name)

    def get_all(self) -> dict[str, Plugin]:
        """获取所有插件"""
        return dict(self._plugins)

    async def initialize_all(self) -> tuple[bool, list[tuple[str, bool, str]]]:
        """初始化所有插件，返回 (全部成功, [(插件名, 成功, 原因)])"""
        all_ok = True
        results: list[tuple[str, bool, str]] = []
        for name, plugin in self._plugins.items():
            try:
                plugin._init_error = ""
                ok = await plugin.initialize()
                if ok:
                    plugin._set_status(PluginStatus.INITIALIZED)
                    logger.info(f"Plugin {name} initialized")
                    results.append((name, True, ""))
                else:
                    plugin._set_status(PluginStatus.ERROR)
                    reason = plugin._init_error or f"Plugin {name} failed to initialize"
                    logger.error(reason)
                    results.append((name, False, reason))
                    all_ok = False
            except Exception as e:
                plugin._set_status(PluginStatus.ERROR)
                msg = f"Plugin {name} initialization error: {e}"
                logger.error(msg)
                results.append((name, False, msg))
                all_ok = False
        return all_ok, results

    async def enable_all(self) -> bool:
        """启用所有插件"""
        all_ok = True
        for name, plugin in self._plugins.items():
            if plugin.status == PluginStatus.INITIALIZED:
                try:
                    ok = await plugin.enable()
                    if ok:
                        plugin._set_status(PluginStatus.ENABLED)
                    else:
                        all_ok = False
                except Exception as e:
                    logger.error(f"Plugin {name} enable error: {e}")
                    all_ok = False
        return all_ok

    async def shutdown_all(self) -> None:
        """关闭所有插件"""
        for name, plugin in self._plugins.items():
            try:
                await plugin.shutdown()
                plugin._set_status(PluginStatus.DISABLED)
            except Exception as e:
                logger.error(f"Plugin {name} shutdown error: {e}")

    async def health_check_all(self) -> dict[str, bool]:
        """检查所有插件健康状态"""
        results = {}
        for name, plugin in self._plugins.items():
            try:
                results[name] = await plugin.health_check()
            except Exception:
                results[name] = False
        return results
