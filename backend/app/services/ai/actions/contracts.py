from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.schemas.ai.action_confirmation import AIActionVerificationData

if TYPE_CHECKING:
    from app.schemas.ai.action_confirmation import AIControlledApplyResult


class ActionVerificationError(RuntimeError):
    """The domain write returned but the formal read-back did not verify it."""


@dataclass(frozen=True, slots=True)
class ActionHandlerManifest:
    action_type: str
    handler_version: str
    autonomy_level: str
    target_state: str
    model_may_propose: bool
    model_may_approve: bool
    model_may_execute: bool
    publish_allowed: bool
    rollback_allowed: bool


@dataclass(frozen=True, slots=True)
class ActionApprovalPolicy:
    policy_id: str
    policy_version: str
    approvals_required: int
    approver_must_be_proposer: bool
    allowed_source: str


ActionPostVerifier = Callable[
    [Session, BaseModel, "AIControlledApplyResult"], AIActionVerificationData
]
