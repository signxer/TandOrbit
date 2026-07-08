"""状态机单元测试"""

import pytest

from app.enums import Mode
from app.events import EventBus, ModeChangedEvent
from app.state.state_machine import StateManager


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def state_manager(event_bus: EventBus) -> StateManager:
    return StateManager(event_bus)


class TestStateManager:
    """StateManager 测试"""

    def test_initial_state(self, state_manager: StateManager) -> None:
        assert state_manager.current_mode == Mode.UNKNOWN
        assert state_manager.target_mode is None
        assert not state_manager.is_transitioning

    def test_can_transition_from_unknown(self, state_manager: StateManager) -> None:
        assert state_manager.can_transition(Mode.MAC)
        assert state_manager.can_transition(Mode.WINDOWS)
        assert not state_manager.can_transition(Mode.SHARE)

    def test_can_transition_from_mac(self, state_manager: StateManager) -> None:
        state_manager.force_set(Mode.MAC)
        assert state_manager.can_transition(Mode.WINDOWS)
        assert state_manager.can_transition(Mode.SHARE)
        assert state_manager.can_transition(Mode.PRESENTATION)
        assert not state_manager.can_transition(Mode.MAC)

    def test_set_target(self, state_manager: StateManager) -> None:
        assert state_manager.set_target(Mode.MAC)
        assert state_manager.target_mode == Mode.MAC

    def test_set_invalid_target(self, state_manager: StateManager) -> None:
        assert not state_manager.set_target(Mode.SHARE)

    def test_transition_commit(self, state_manager: StateManager, event_bus: EventBus) -> None:
        events: list[ModeChangedEvent] = []
        event_bus.subscribe(ModeChangedEvent, lambda e: events.append(e))

        state_manager.set_target(Mode.MAC)
        assert state_manager.begin_transition()
        assert state_manager.is_transitioning
        state_manager.commit_transition()

        assert state_manager.current_mode == Mode.MAC
        assert not state_manager.is_transitioning
        assert len(events) == 1
        assert events[0].new_mode == "MAC"

    def test_transition_rollback(self, state_manager: StateManager) -> None:
        state_manager.set_target(Mode.MAC)
        state_manager.begin_transition()
        state_manager.rollback_transition()

        assert state_manager.current_mode == Mode.UNKNOWN
        assert not state_manager.is_transitioning
        assert state_manager.target_mode is None

    def test_force_set(self, state_manager: StateManager) -> None:
        state_manager.force_set(Mode.SHARE)
        assert state_manager.current_mode == Mode.SHARE

    def test_history(self, state_manager: StateManager) -> None:
        state_manager.force_set(Mode.MAC)
        state_manager.set_target(Mode.WINDOWS)
        state_manager.begin_transition()
        state_manager.commit_transition()

        history = state_manager.get_history()
        assert len(history) == 1
        assert history[0] == (Mode.MAC, Mode.WINDOWS)  # 只有 commit 记录
