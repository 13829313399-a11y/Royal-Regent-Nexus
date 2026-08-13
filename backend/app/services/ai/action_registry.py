from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.schemas.ai.action_confirmation import (
    AIControlledApplyResult,
    AIInjectionSchedulingApplyActionSummary,
)
from app.services.ai.actions.contracts import (
    ActionApprovalPolicy,
    ActionHandlerManifest,
    ActionPostVerifier,
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


def _legacy_manifest() -> ActionHandlerManifest:
    return ActionHandlerManifest(
        action_type="APPLY_INJECTION_AUTO_SCHEDULE_RUN",
        handler_version="legacy-confirmation-v1",
        autonomy_level="L3",
        target_state="DRAFT",
        model_may_propose=True,
        model_may_approve=False,
        model_may_execute=False,
        publish_allowed=False,
        rollback_allowed=False,
    )


def _legacy_approval_policy() -> ActionApprovalPolicy:
    return ActionApprovalPolicy(
        policy_id="single-explicit-owner-approval",
        policy_version="legacy-confirmation-v1",
        approvals_required=1,
        approver_must_be_proposer=True,
        allowed_source="AUTHENTICATED_USER_API",
    )


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
    manifest: ActionHandlerManifest = field(default_factory=_legacy_manifest)
    approval_policy: ActionApprovalPolicy = field(
        default_factory=_legacy_approval_policy
    )
    post_verifier: ActionPostVerifier | None = None


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
