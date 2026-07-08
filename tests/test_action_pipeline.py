"""动作管道单元测试"""

import pytest

from app.events import EventBus
from app.scheduler.action_pipeline import Action, ActionPipeline


class MockAction(Action):
    """模拟动作"""

    def __init__(self, name: str, should_succeed: bool = True) -> None:
        super().__init__(name)
        self._should_succeed = should_succeed
        self.executed = False
        self.rolled_back = False

    async def execute(self) -> bool:
        self.executed = True
        return self._should_succeed

    async def rollback(self) -> bool:
        self.rolled_back = True
        return True


class TestActionPipeline:
    """ActionPipeline 测试"""

    @pytest.mark.asyncio
    async def test_successful_pipeline(self) -> None:
        bus = EventBus()
        pipeline = ActionPipeline("test", bus)

        a1 = MockAction("action1")
        a2 = MockAction("action2")
        pipeline.add_action(a1).add_action(a2)

        result = await pipeline.execute()
        assert result is True
        assert a1.executed
        assert a2.executed
        assert not a1.rolled_back
        assert not a2.rolled_back

    @pytest.mark.asyncio
    async def test_failed_pipeline_rolls_back(self) -> None:
        bus = EventBus()
        pipeline = ActionPipeline("test", bus)

        a1 = MockAction("action1", should_succeed=True)
        a2 = MockAction("action2", should_succeed=False)
        a3 = MockAction("action3")
        pipeline.add_action(a1).add_action(a2).add_action(a3)

        result = await pipeline.execute()
        assert result is False
        assert a1.executed
        assert a2.executed
        assert not a3.executed  # a2 失败后 a3 不应执行
        assert a1.rolled_back  # a1 应该被回滚
        assert not a2.rolled_back  # a2 本身不需要回滚

    @pytest.mark.asyncio
    async def test_exception_triggers_rollback(self) -> None:
        bus = EventBus()
        pipeline = ActionPipeline("test", bus)

        class ExceptionAction(Action):
            async def execute(self) -> bool:
                raise RuntimeError("test error")

            async def rollback(self) -> bool:
                return True

        a1 = MockAction("action1")
        a2 = ExceptionAction("action2")
        pipeline.add_action(a1).add_action(a2)

        result = await pipeline.execute()
        assert result is False
        assert a1.rolled_back
