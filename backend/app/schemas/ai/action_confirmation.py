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
