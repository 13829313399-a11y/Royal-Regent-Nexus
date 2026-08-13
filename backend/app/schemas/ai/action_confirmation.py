from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai.tool import StrictToolInput

AIActionConfirmationStatus = Literal[
    "PENDING",
    "CONFIRMED",
    "EXECUTED",
    "EXPIRED",
    "CANCELLED",
    "STALE",
    "FAILED",
]

AIActionLifecycleStatus = Literal[
    "PROPOSED",
    "WAITING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "EXPIRED",
    "CANCELLED",
    "COMMITTING",
    "VERIFYING",
    "EXECUTED",
    "FAILED",
    "STALE",
]


class InjectionSchedulingApplyProposalInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=96)

    @field_validator("factory_id", "run_id")
    @classmethod
    def strip_proposal_text(cls, value: str) -> str:
        return value.strip()


class AIInjectionSchedulingApplyCanonicalAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_id: str
    run_id: str
    run_revision: int = Field(ge=1)
    plan_id: str
    expected_plan_revision: int = Field(ge=1)
    expected_rule_revision: int = Field(ge=1)


class AIInjectionSchedulingApplyActionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: Literal["APPLY_INJECTION_AUTO_SCHEDULE_RUN"] = (
        "APPLY_INJECTION_AUTO_SCHEDULE_RUN"
    )
    run_id: str
    plan_id: str
    plan_revision: int = Field(ge=1)
    rule_revision: int = Field(ge=1)
    assignment_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    effect_label: Literal["应用到 DRAFT，不会发布生产"] = "应用到 DRAFT，不会发布生产"
    requires_override_reason: bool


class AIActionConfirmationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-action-confirmation-v1"] = "ai-action-confirmation-v1"
    result_type: Literal["ai.action_confirmation"] = "ai.action_confirmation"
    source_type: Literal["FORMAL"] = "FORMAL"
    confirmation_id: str
    tool_name: Literal["injection_scheduling.apply_preview_run"]
    risk_level: Literal["CONSEQUENTIAL_WRITE"] = "CONSEQUENTIAL_WRITE"
    factory_id: str
    entity_type: Literal["auto_schedule_run"] = "auto_schedule_run"
    entity_id: str
    entity_revision: int = Field(ge=1)
    args_hash: str = Field(min_length=64, max_length=64)
    expires_at: str
    status: AIActionConfirmationStatus
    created_at: str
    confirmed_at: str
    executed_at: str
    failure_code: str
    action_summary: AIInjectionSchedulingApplyActionSummary


class AIActionConfirmRequest(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_args_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("factory_id")
    @classmethod
    def strip_factory(cls, value: str) -> str:
        return value.strip()


class AIActionCancelRequest(AIActionConfirmRequest):
    pass


class AIActionApproveRequest(AIActionConfirmRequest):
    approval_request_id: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )

    @field_validator("approval_request_id")
    @classmethod
    def strip_approval_request_id(cls, value: str) -> str:
        return value.strip()


class AIActionRejectRequest(AIActionConfirmRequest):
    rejection_reason: str = Field(min_length=1, max_length=1000)

    @field_validator("rejection_reason")
    @classmethod
    def strip_rejection_reason(cls, value: str) -> str:
        return value.strip()


class AIActionExecuteRequest(AIActionConfirmRequest):
    execution_request_id: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    review_override_reason: str = Field(default="", max_length=2000)

    @field_validator("execution_request_id", "review_override_reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class AIControlledApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_status: Literal["APPLIED"]
    plan_id: str
    plan_revision: int = Field(ge=2)
    plan_status: Literal["DRAFT"]
    audit_sequence: int = Field(ge=1)
    idempotent_replay: bool
    outcome_label: Literal["已应用到 DRAFT，尚未发布生产"] = (
        "已应用到 DRAFT，尚未发布生产"
    )


class AIActionExecutionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-action-execution-v1"] = "ai-action-execution-v1"
    result_type: Literal["ai.action_execution"] = "ai.action_execution"
    source_type: Literal["FORMAL"] = "FORMAL"
    confirmation: AIActionConfirmationData
    result: AIControlledApplyResult


class AIActionHandlerManifestData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: Literal["APPLY_INJECTION_AUTO_SCHEDULE_RUN"]
    handler_version: str
    autonomy_level: Literal["L3"] = "L3"
    risk_level: Literal["CONSEQUENTIAL_WRITE"] = "CONSEQUENTIAL_WRITE"
    target_state: Literal["DRAFT"] = "DRAFT"
    model_may_propose: Literal[True] = True
    model_may_approve: Literal[False] = False
    model_may_execute: Literal[False] = False
    publish_allowed: Literal[False] = False
    rollback_allowed: Literal[False] = False


class AIActionApprovalPolicyData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: Literal["single-explicit-owner-approval"] = (
        "single-explicit-owner-approval"
    )
    policy_version: str
    approvals_required: Literal[1] = 1
    approver_must_be_proposer: Literal[True] = True
    allowed_source: Literal["AUTHENTICATED_USER_API"] = "AUTHENTICATED_USER_API"
    binds_user: Literal[True] = True
    binds_factory: Literal[True] = True
    binds_action: Literal[True] = True
    binds_args_hash: Literal[True] = True
    binds_entity_revision: Literal[True] = True
    binds_ttl: Literal[True] = True


class AIActionApprovalBindingData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_user_id: str
    approval_request_id: str
    factory_id: str
    action_type: str
    args_hash: str = Field(min_length=64, max_length=64)
    entity_revision: int = Field(ge=1)
    expires_at: str
    approved_at: str


class AIActionVerificationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_type: Literal["FORMAL_DRAFT_READ_BACK"] = (
        "FORMAL_DRAFT_READ_BACK"
    )
    verified: Literal[True] = True
    factory_id: str
    entity_type: Literal["injection_scheduling_plan"] = "injection_scheduling_plan"
    entity_id: str
    entity_revision: int = Field(ge=1)
    entity_status: Literal["DRAFT"] = "DRAFT"
    run_id: str
    run_status: Literal["APPLIED"] = "APPLIED"
    domain_audit_id: str
    verified_at: str


class AIActionCompensationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    automatic_compensation_available: Literal[False] = False
    mode: Literal["NEW_DRAFT_PROPOSAL_REQUIRED"] = "NEW_DRAFT_PROPOSAL_REQUIRED"
    guidance: Literal[
        "如需修正，请重新生成 DRAFT Preview 并通过新的人工批准；本 Gateway 不执行 Publish 或 Rollback。"
    ] = "如需修正，请重新生成 DRAFT Preview 并通过新的人工批准；本 Gateway 不执行 Publish 或 Rollback。"


class AIActionProposalData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-action-proposal-v1"] = "ai-action-proposal-v1"
    result_type: Literal["ai.action_proposal"] = "ai.action_proposal"
    source_type: Literal["FORMAL"] = "FORMAL"
    proposal_id: str
    compatibility_confirmation_id: str
    lifecycle_status: AIActionLifecycleStatus
    legacy_status: AIActionConfirmationStatus
    factory_id: str
    entity_type: str
    entity_id: str
    entity_revision: int = Field(ge=1)
    args_hash: str = Field(min_length=64, max_length=64)
    expires_at: str
    created_at: str
    failure_code: str
    manifest: AIActionHandlerManifestData
    approval_policy: AIActionApprovalPolicyData
    approval: AIActionApprovalBindingData | None = None
    action_summary: AIInjectionSchedulingApplyActionSummary
    verification: AIActionVerificationData | None = None
    compensation: AIActionCompensationData


class AIActionGatewayExecutionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-action-gateway-execution-v1"] = (
        "ai-action-gateway-execution-v1"
    )
    result_type: Literal["ai.action_gateway_execution"] = (
        "ai.action_gateway_execution"
    )
    proposal: AIActionProposalData
    result: AIControlledApplyResult
