"""事件总线单元测试"""

import pytest

from app.events import Event, EventBus, ModeChangedEvent


class TestEventBus:
    """EventBus 测试"""

    def test_subscribe_and_publish(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(ModeChangedEvent, lambda e: received.append(e))

        event = ModeChangedEvent(old_mode="MAC", new_mode="WINDOWS")
        bus.publish(event)

        assert len(received) == 1
        assert received[0] is event

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        callback = lambda e: received.append(e)
        bus.subscribe(ModeChangedEvent, callback)
        bus.unsubscribe(ModeChangedEvent, callback)

        bus.publish(ModeChangedEvent(old_mode="MAC", new_mode="WINDOWS"))
        assert len(received) == 0

    def test_multiple_subscribers(self) -> None:
        bus = EventBus()
        received1: list[Event] = []
        received2: list[Event] = []
        bus.subscribe(ModeChangedEvent, lambda e: received1.append(e))
        bus.subscribe(ModeChangedEvent, lambda e: received2.append(e))

        bus.publish(ModeChangedEvent(old_mode="MAC", new_mode="WINDOWS"))
        assert len(received1) == 1
        assert len(received2) == 1

    def test_history(self) -> None:
        bus = EventBus()
        bus.publish(ModeChangedEvent(old_mode="MAC", new_mode="WINDOWS"))
        bus.publish(ModeChangedEvent(old_mode="WINDOWS", new_mode="SHARE"))

        history = bus.get_history()
        assert len(history) == 2

    def test_history_filter(self) -> None:
        bus = EventBus()
        bus.publish(ModeChangedEvent(old_mode="MAC", new_mode="WINDOWS"))
        bus.publish(Event(source="test"))

        history = bus.get_history(ModeChangedEvent)
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_publish_async(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        async def handler(e: Event) -> None:
            received.append(e)

        bus.subscribe(ModeChangedEvent, handler)
        await bus.publish_async(ModeChangedEvent(old_mode="MAC", new_mode="WINDOWS"))
        assert len(received) == 1
