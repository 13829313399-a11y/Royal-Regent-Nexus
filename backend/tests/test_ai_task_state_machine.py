from __future__ import annotations

import pytest
from app.schemas.ai.task import AITaskState, AITaskStepState
from app.services.ai.task_state_machine import (
    STEP_TRANSITIONS,
    TASK_TRANSITIONS,
    AITaskTransitionError,
    require_step_transition,
    require_task_transition,
)


def test_task_state_machine_accepts_only_the_declared_edges() -> None:
    for current in AITaskState:
        for requested in AITaskState:
            if requested in TASK_TRANSITIONS[current]:
                assert (
                    require_task_transition(current.value, requested.value) is requested
                )
            else:
                with pytest.raises(AITaskTransitionError) as exc_info:
                    require_task_transition(current.value, requested.value)
                assert exc_info.value.code == "AI_TASK_INVALID_TRANSITION"


def test_waiting_approval_is_reserved_and_unreachable() -> None:
    assert TASK_TRANSITIONS[AITaskState.WAITING_APPROVAL] == frozenset()
    assert all(
        AITaskState.WAITING_APPROVAL not in targets
        for targets in TASK_TRANSITIONS.values()
    )


def test_step_state_machine_accepts_only_the_declared_edges() -> None:
    for current in AITaskStepState:
        for requested in AITaskStepState:
            if requested in STEP_TRANSITIONS[current]:
                assert (
                    require_step_transition(current.value, requested.value) is requested
                )
            else:
                with pytest.raises(AITaskTransitionError):
                    require_step_transition(current.value, requested.value)


@pytest.mark.parametrize(
    ("current", "requested"),
    [("UNKNOWN", "RUNNING"), ("CREATED", "UNKNOWN")],
)
def test_unknown_task_states_fail_closed(current: str, requested: str) -> None:
    with pytest.raises(AITaskTransitionError):
        require_task_transition(current, requested)
