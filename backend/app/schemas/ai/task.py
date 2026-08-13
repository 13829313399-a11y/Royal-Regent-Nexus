from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from app.schemas.ai.context import AIPageContextInput
from app.schemas.ai.evidence import AIEvidenceReferenceV1
from app.schemas.ai.tool import AIToolRiskLevel


class AITaskType(StrEnum):
    READ = "READ"
    COMPUTE = "COMPUTE"
    SIMULATE = "SIMULATE"
    PREVIEW = "PREVIEW"


class AITaskState(StrEnum):
    CREATED = "CREATED"
    UNDERSTOOD = "UNDERSTOOD"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"


class AITaskStepState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"


class AITaskEventType(StrEnum):
    TASK_CREATED = "TASK_CREATED"
    STATE_TRANSITION = "STATE_TRANSITION"
    STEP_STATE_TRANSITION = "STEP_STATE_TRANSITION"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    RESUME_REQUESTED = "RESUME_REQUESTED"
    LEASE_CLAIMED = "LEASE_CLAIMED"
    LEASE_RELEASED = "LEASE_RELEASED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"


class AITaskWorkerStatus(StrEnum):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    WAITING_RETRY = "WAITING_RETRY"
    IDLE = "IDLE"


class AITaskCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = "1"
    available: bool
    worker_enabled: bool


class AITaskStepCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64)
    kind: AITaskType
    label: str = Field(min_length=1, max_length=160)
    tool_name: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
        max_length=160,
    )
    arguments: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        return value.strip()


class AITaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: AITaskType
    factory_scope: str = Field(min_length=1, max_length=64)
    conversation_id: str | None = Field(
        default=None,
        pattern=r"^aicv-[a-f0-9]{32}$",
        max_length=64,
    )
    input_message_id: str | None = Field(
        default=None,
        pattern=r"^aimsg-[a-f0-9]{32}$",
        max_length=64,
    )
    primary_skill_id: str = Field(
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
        max_length=160,
    )
    primary_skill_version: str | None = Field(
        default=None,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
        max_length=32,
    )
    supporting_skill_ids: tuple[str, ...] = Field(default=(), max_length=3)
    proposed_tool_names: tuple[str, ...] | None = Field(default=None, max_length=32)
    proposed_max_steps: int | None = Field(default=None, ge=1, le=6)
    proposed_maximum_risk: AIToolRiskLevel | None = None
    proposed_token_budget: int | None = Field(default=None, ge=256, le=16_000)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    page_context: AIPageContextInput | None = None
    steps: tuple[AITaskStepCreate, ...] = Field(min_length=1, max_length=6)

    @field_validator("factory_scope", "idempotency_key")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("supporting_skill_ids", "proposed_tool_names")
    @classmethod
    def validate_unique_ids(
        cls,
        value: tuple[str, ...] | None,
    ) -> tuple[str, ...] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Task Skill and Tool ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_closed_task(self) -> AITaskCreate:
        if len({step.key for step in self.steps}) != len(self.steps):
            raise ValueError("Task step keys must be unique")
        if (
            self.page_context is not None
            and self.page_context.factory_id != self.factory_scope
        ):
            raise ValueError("Task page factory must equal factory_scope")
        if self.input_message_id is not None and self.conversation_id is None:
            raise ValueError("Task input_message_id requires conversation_id")
        if (
            self.proposed_max_steps is not None
            and len(self.steps) > self.proposed_max_steps
        ):
            raise ValueError("Task steps exceed proposed max_steps")
        if self.task_type != AITaskType.PREVIEW and any(
            step.kind == AITaskType.PREVIEW for step in self.steps
        ):
            raise ValueError("Only PREVIEW tasks may contain PREVIEW steps")
        return self


class AITaskCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason_code: str = Field(
        default="USER_CANCELLED",
        pattern=r"^[A-Z][A-Z0-9_]{2,95}$",
        max_length=96,
    )


class AITaskResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    expected_input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_runtime_plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class AITaskRuntimePlanData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    primary_skill_id: str
    primary_skill_version: str
    supporting_skill_ids: tuple[str, ...]
    allowed_tool_names: tuple[str, ...]
    maximum_risk: AIToolRiskLevel
    max_steps: int = Field(ge=1, le=6)
    token_budget: int = Field(ge=256, le=16_000)
    output_schema_id: str


class AITaskStepData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    ordinal: int = Field(ge=1, le=6)
    key: str
    kind: AITaskType
    label: str
    state: AITaskStepState
    tool_name: str | None
    tool_version: str | None
    arguments_hash: str
    side_effect_class: str
    idempotent: bool
    revision: int = Field(ge=1)
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=1, le=3)
    result_hash: str
    result_metadata: dict[str, JsonValue]
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str


class AITaskData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    owner_user_id: str
    conversation_id: str | None
    input_message_id: str | None
    factory_scope: str
    task_type: AITaskType
    state: AITaskState
    maximum_risk: AIToolRiskLevel
    primary_skill_id: str
    primary_skill_version: str
    primary_skill_hash: str
    prompt_version: str
    prompt_hash: str
    runtime_plan: AITaskRuntimePlanData
    runtime_plan_hash: str
    input_hash: str
    revision: int = Field(ge=1)
    step_count: int = Field(ge=1, le=6)
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None
    retention_expires_at: datetime | None
    backup_delete_by: datetime | None
    cancellation_requested_at: datetime | None
    resume_requested_at: datetime | None
    failure_code: str
    worker_status: AITaskWorkerStatus
    lease_expires_at: datetime | None
    last_heartbeat_at: datetime | None
    next_attempt_at: datetime | None
    claim_count: int = Field(ge=0)
    steps: tuple[AITaskStepData, ...]


class AITaskSummaryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str | None
    factory_scope: str
    task_type: AITaskType
    state: AITaskState
    maximum_risk: AIToolRiskLevel
    primary_skill_id: str
    revision: int = Field(ge=1)
    step_count: int = Field(ge=1, le=6)
    worker_status: AITaskWorkerStatus
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


class AITaskListPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[AITaskSummaryData, ...]
    next_cursor: str | None = Field(default=None, max_length=512)


class AIArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(
        min_length=8,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$",
    )
    artifact_kind: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Z][A-Z0-9_]+$",
    )
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    access_policy: Literal["REAUTHORIZE_ON_OPEN"] = "REAUTHORIZE_ON_OPEN"


class AITaskEventData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    step_id: str | None
    sequence: int = Field(ge=1)
    event_type: AITaskEventType
    actor_type: str
    transition_from: AITaskState | AITaskStepState | None
    transition_to: AITaskState | AITaskStepState | None
    reason_code: str
    evidence: tuple[AIEvidenceReferenceV1, ...]
    artifacts: tuple[AIArtifactReference, ...]
    created_at: datetime


class AITaskEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[AITaskEventData, ...]
    next_after: int | None = Field(default=None, ge=1)
