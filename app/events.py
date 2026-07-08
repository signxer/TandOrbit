"""TandOrbit 事件总线

所有模块通过事件总线通信，禁止直接调用。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine, Union

from loguru import logger


# 事件类型定义
class Event:
    """事件基类"""

    def __init__(self, source: str = "", **kwargs: Any) -> None:
        self.source = source
        self.data = kwargs

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source={self.source!r})"


# --- 具体事件 ---


class ModeChangedEvent(Event):
    """模式切换事件"""

    def __init__(self, old_mode: str, new_mode: str, source: str = "") -> None:
        super().__init__(source=source, old_mode=old_mode, new_mode=new_mode)
        self.old_mode = old_mode
        self.new_mode = new_mode


class DisplayChangedEvent(Event):
    """显示器状态变化"""

    def __init__(self, display_id: int, enabled: bool, source: str = "") -> None:
        super().__init__(source=source, display_id=display_id, enabled=enabled)
        self.display_id = display_id
        self.enabled = enabled


class DeviceStatusChangedEvent(Event):
    """设备状态变化"""

    def __init__(self, device: str, status: str, source: str = "") -> None:
        super().__init__(source=source, device=device, status=status)
        self.device = device
        self.status = status


class DeskflowStatusChangedEvent(Event):
    """Deskflow 连接状态变化"""

    def __init__(self, connected: bool, source: str = "") -> None:
        super().__init__(source=source, connected=connected)
        self.connected = connected


class ActionCompletedEvent(Event):
    """动作完成事件"""

    def __init__(
        self, action_name: str, success: bool, error: str = "", source: str = ""
    ) -> None:
        super().__init__(
            source=source, action_name=action_name, success=success, error=error
        )
        self.action_name = action_name
        self.success = success
        self.error = error


class ErrorEvent(Event):
    """错误事件"""

    def __init__(self, message: str, exception: Exception | None = None, source: str = "") -> None:
        super().__init__(source=source, message=message, exception=exception)
        self.message = message
        self.exception = exception


class SystemReadyEvent(Event):
    """系统就绪事件"""

    pass


class ConfigChangedEvent(Event):
    """配置变更事件"""

    def __init__(self, key: str, source: str = "") -> None:
        super().__init__(source=source, key=key)
        self.key = key


# --- 事件总线 ---

# 回调类型：同步或异步
SyncCallback = Callable[[Event], None]
AsyncCallback = Callable[[Event], Coroutine[Any, Any, None]]
Callback = Union[SyncCallback, AsyncCallback]


class EventBus:
    """事件总线

    所有模块通过 publish/subscribe 通信，禁止直接调用。
    支持同步和异步回调。
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callback]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history = 1000

    def subscribe(self, event_type: type[Event], callback: Callback) -> None:
        """订阅事件"""
        event_name = event_type.__name__
        self._subscribers[event_name].append(callback)
        logger.debug(f"Subscribed to {event_name}: {callback.__qualname__}")

    def unsubscribe(self, event_type: type[Event], callback: Callback) -> None:
        """取消订阅"""
        event_name = event_type.__name__
        if callback in self._subscribers[event_name]:
            self._subscribers[event_name].remove(callback)

    def publish(self, event: Event) -> None:
        """发布事件（同步）"""
        event_name = event.__class__.__name__
        logger.debug(f"Publishing event: {event}")
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        for callback in self._subscribers.get(event_name, []):
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event handler {callback.__qualname__}: {e}")

    async def publish_async(self, event: Event) -> None:
        """发布事件（异步）"""
        event_name = event.__class__.__name__
        logger.debug(f"Publishing async event: {event}")
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        for callback in self._subscribers.get(event_name, []):
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error in async event handler {callback.__qualname__}: {e}")

    def get_history(self, event_type: type[Event] | None = None) -> list[Event]:
        """获取事件历史"""
        if event_type is None:
            return list(self._history)
        event_name = event_type.__name__
        return [e for e in self._history if e.__class__.__name__ == event_name]

    def clear_history(self) -> None:
        """清空事件历史"""
        self._history.clear()


# 全局事件总线实例
event_bus = EventBus()
