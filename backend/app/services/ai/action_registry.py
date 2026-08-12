from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.schemas.ai.action_confirmation import (
    AIControlledApplyResult,
    AIInjectionSchedulingApplyActionSummary,
)
from app.services.auth import AuthContext

if TYPE_CHECKING:
    from app.models.ai_action import AIActionConfirmation


class ActionConfirmationStaleError(RuntimeError):
    pass


ActionSummaryBuilder = Callable[
    [Session, BaseModel], AIInjectionSchedulingApplyActionSummary
]
ActionFreshnessValidator = Callable[
    [Session, "AIActionConfirmation", BaseModel], None
]
ActionExecutionValidator = Callable[[Session, BaseModel, str, AuthContext], None]
ActionExecutor = Callable[
    [Session, BaseModel, str, str, AuthContext], AIControlledApplyResult
]


@dataclass(frozen=True, slots=True)
class AIActionHandler:
    tool_name: str
    action_model: type[BaseModel]
    risk_level: str
    required_permission: str
    allowed_departments: frozenset[str]
    factory_argument: str
    entity_type: str
    entity_id_argument: str
    entity_revision_argument: str
    summary_builder: ActionSummaryBuilder
    freshness_validator: ActionFreshnessValidator
    execution_validator: ActionExecutionValidator
    executor: ActionExecutor


class AIActionRegistry:
    def __init__(self, handlers: tuple[AIActionHandler, ...]) -> None:
        self._handlers = {handler.tool_name: handler for handler in handlers}
        if len(self._handlers) != len(handlers):
            raise ValueError("AI action handler names must be unique")

    def resolve(self, tool_name: str) -> AIActionHandler | None:
        return self._handlers.get(tool_name)


def build_default_action_registry() -> AIActionRegistry:
    from app.services.ai.controlled_apply import injection_scheduling_apply_handler

    return AIActionRegistry((injection_scheduling_apply_handler(),))
