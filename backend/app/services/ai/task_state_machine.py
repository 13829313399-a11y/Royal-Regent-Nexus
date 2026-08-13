from __future__ import annotations

from app.schemas.ai.task import AITaskState, AITaskStepState


class AITaskTransitionError(ValueError):
    code = "AI_TASK_INVALID_TRANSITION"

    def __init__(self, current: str, requested: str) -> None:
        super().__init__(f"invalid AI Task transition: {current} -> {requested}")
        self.current = current
        self.requested = requested


TASK_TRANSITIONS: dict[AITaskState, frozenset[AITaskState]] = {
    AITaskState.CREATED: frozenset({AITaskState.UNDERSTOOD}),
    AITaskState.UNDERSTOOD: frozenset({AITaskState.PLANNED, AITaskState.RUNNING}),
    AITaskState.PLANNED: frozenset({AITaskState.RUNNING, AITaskState.CANCELLING}),
    AITaskState.RUNNING: frozenset(
        {
            AITaskState.WAITING_INPUT,
            AITaskState.VERIFYING,
            AITaskState.FAILED,
            AITaskState.CANCELLING,
        }
    ),
    AITaskState.WAITING_INPUT: frozenset(
        {AITaskState.RUNNING, AITaskState.CANCELLING}
    ),
    AITaskState.WAITING_APPROVAL: frozenset(),
    AITaskState.VERIFYING: frozenset({AITaskState.COMPLETED, AITaskState.FAILED}),
    AITaskState.COMPLETED: frozenset(),
    AITaskState.CANCELLING: frozenset({AITaskState.CANCELLED}),
    AITaskState.CANCELLED: frozenset(),
    AITaskState.FAILED: frozenset({AITaskState.RETRY_PENDING}),
    AITaskState.RETRY_PENDING: frozenset({AITaskState.RUNNING}),
}

STEP_TRANSITIONS: dict[AITaskStepState, frozenset[AITaskStepState]] = {
    AITaskStepState.PENDING: frozenset(
        {AITaskStepState.RUNNING, AITaskStepState.CANCELLED}
    ),
    AITaskStepState.RUNNING: frozenset(
        {
            AITaskStepState.WAITING_INPUT,
            AITaskStepState.VERIFYING,
            AITaskStepState.COMPLETED,
            AITaskStepState.FAILED,
            AITaskStepState.CANCELLED,
        }
    ),
    AITaskStepState.WAITING_INPUT: frozenset(
        {AITaskStepState.RUNNING, AITaskStepState.CANCELLED}
    ),
    AITaskStepState.VERIFYING: frozenset(
        {AITaskStepState.COMPLETED, AITaskStepState.FAILED}
    ),
    AITaskStepState.COMPLETED: frozenset(),
    AITaskStepState.CANCELLED: frozenset(),
    AITaskStepState.FAILED: frozenset({AITaskStepState.RETRY_PENDING}),
    AITaskStepState.RETRY_PENDING: frozenset({AITaskStepState.RUNNING}),
}

TERMINAL_TASK_STATES = frozenset(
    {AITaskState.COMPLETED, AITaskState.CANCELLED, AITaskState.FAILED}
)


def require_task_transition(current: str, requested: str) -> AITaskState:
    try:
        current_state = AITaskState(current)
        requested_state = AITaskState(requested)
    except ValueError as exc:
        raise AITaskTransitionError(current, requested) from exc
    if requested_state not in TASK_TRANSITIONS[current_state]:
        raise AITaskTransitionError(current, requested)
    return requested_state


def require_step_transition(current: str, requested: str) -> AITaskStepState:
    try:
        current_state = AITaskStepState(current)
        requested_state = AITaskStepState(requested)
    except ValueError as exc:
        raise AITaskTransitionError(current, requested) from exc
    if requested_state not in STEP_TRANSITIONS[current_state]:
        raise AITaskTransitionError(current, requested)
    return requested_state
