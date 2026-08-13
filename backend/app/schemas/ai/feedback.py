from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ai.tool import StrictToolInput

FeedbackTargetType = Literal["RESPONSE", "MESSAGE", "TASK", "ACTION"]
FeedbackRating = Literal["HELPFUL", "NOT_HELPFUL"]
FeedbackIssueCategory = Literal[
    "NONE",
    "INCORRECT",
    "MISSING_CONTEXT",
    "WRONG_TOOL",
    "WRONG_ARGUMENTS",
    "UNSUPPORTED_CLAIM",
    "PERMISSION",
    "PREVIEW_MISLABEL",
    "UNSAFE",
    "OTHER",
]
FeedbackStatus = Literal["SUBMITTED", "TRIAGED", "EVAL_CANDIDATE", "DISMISSED"]
OperationalAlertType = Literal[
    "COST_PER_SUCCESSFUL_TASK",
    "PROVIDER_FAILURE",
    "TOOL_FAILURE",
    "WORKER_RECOVERY",
    "SCANNER_STALE",
    "BUDGET",
]


class AIFeedbackCreate(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    target_type: FeedbackTargetType
    target_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    rating: FeedbackRating
    issue_category: FeedbackIssueCategory = "NONE"
    comment: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )

    @field_validator("factory_id", "target_id", "comment", "idempotency_key")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_feedback_meaning(self) -> "AIFeedbackCreate":
        if self.rating == "HELPFUL" and self.issue_category != "NONE":
            raise ValueError("Helpful feedback cannot claim an issue category")
        if self.rating == "NOT_HELPFUL" and self.issue_category == "NONE":
            raise ValueError("Not-helpful feedback requires an issue category")
        return self


class AIFeedbackReview(StrictToolInput):
    status: Literal["TRIAGED", "EVAL_CANDIDATE", "DISMISSED"]
    review_note: str = Field(min_length=4, max_length=2000)
    eval_suite_id: str = Field(default="", max_length=128, pattern=r"^[a-z0-9_]*$")
    eval_case_id: str = Field(default="", max_length=128, pattern=r"^[a-z0-9_]*$")

    @field_validator("review_note", "eval_suite_id", "eval_case_id")
    @classmethod
    def strip_review_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_eval_candidate(self) -> "AIFeedbackReview":
        has_refs = bool(self.eval_suite_id and self.eval_case_id)
        if self.status == "EVAL_CANDIDATE" and not has_refs:
            raise ValueError("Eval candidates require explicit suite and case ids")
        if self.status != "EVAL_CANDIDATE" and (
            self.eval_suite_id or self.eval_case_id
        ):
            raise ValueError("Only Eval candidates may carry Eval proposal refs")
        return self


class AIFeedbackData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-feedback-v1"] = "ai-feedback-v1"
    id: str
    owner_user_id: str
    factory_id: str
    target_type: FeedbackTargetType
    target_id: str
    rating: FeedbackRating
    issue_category: FeedbackIssueCategory
    comment: str
    status: FeedbackStatus
    reviewed_by: str | None
    review_note: str
    eval_suite_id: str
    eval_case_id: str
    created_at: str
    updated_at: str
    reviewed_at: str
    auto_applied_to_prompt_or_knowledge: Literal[False] = False


class AIFeedbackPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AIFeedbackData]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class AIMetricRates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_success_rate: float | None
    grounded_claim_rate: float | None
    citation_accuracy: float | None
    tool_selection_precision: float | None
    tool_argument_accuracy: float | None
    user_correction_rate: float | None
    provider_retry_rate: float | None
    model_failure_rate: float | None
    tool_failure_rate: float | None
    worker_retry_rate: float | None
    unauthorized_action_rate: float
    cross_factory_leakage_rate: float
    preview_executed_mislabel_rate: float


class AIMetricLatency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_run_p50_ms: int | None
    model_run_p95_ms: int | None
    tool_call_p50_ms: int | None
    tool_call_p95_ms: int | None


class AIMetricSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-metric-summary-v1"] = "ai-metric-summary-v1"
    from_time: str
    to_time: str
    model_runs: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    tasks: int = Field(ge=0)
    actions: int = Field(ge=0)
    feedback_items: int = Field(ge=0)
    eval_runs: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_microusd: int = Field(ge=0)
    cost_per_successful_task_microusd: int | None
    cost_basis: Literal["UNAVAILABLE", "CONFIGURED_ESTIMATE", "MIXED"]
    rates: AIMetricRates
    latency: AIMetricLatency
    failures: dict[str, int]
    raw_prompt_recorded: Literal[False] = False
    raw_tool_result_recorded: Literal[False] = False
    chain_of_thought_recorded: Literal[False] = False


class AIMetricEventData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    request_id: str
    event_type: Literal["MODEL_RUN", "TOOL_CALL"]
    factory_id: str
    conversation_id: str
    task_id: str
    action_id: str
    skill_id: str
    skill_version: str
    skill_hash: str
    prompt_version: str
    prompt_hash: str
    provider: str
    model: str
    tool_name: str
    tool_version: str
    status: Literal["SUCCESS", "FAILURE", "DENIED", "CANCELLED"]
    duration_ms: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_microusd: int
    cost_basis: Literal["UNAVAILABLE", "CONFIGURED_ESTIMATE", "PROVIDER_REPORTED"]
    retry_count: int
    error_code: str
    evidence_count: int
    truncated: bool
    unauthorized_action: bool
    cross_factory_leakage: bool
    preview_executed_mislabel: bool
    created_at: str


class AIOperationalAlertItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_type: OperationalAlertType
    triggered: bool
    observed_value: int = Field(ge=0)
    threshold_value: int = Field(gt=0)
    notification_ids: list[str]
    detail_code: str


class AIOperationalAlertEvaluationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-operational-alert-evaluation-v1"] = (
        "ai-operational-alert-evaluation-v1"
    )
    evaluated_at: str
    window_minutes: int = Field(ge=1, le=1440)
    recipient_count: int = Field(ge=1, le=16)
    items: list[AIOperationalAlertItemData]


class AIOperationalAlertAcknowledgementRequest(StrictToolInput):
    notification_ids: list[str] = Field(min_length=1, max_length=96)

    @field_validator("notification_ids")
    @classmethod
    def validate_notification_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Operational alert notification ids must be unique")
        for value in values:
            if (
                len(value) != 48
                or not value.startswith("ainotif-")
                or any(character not in "0123456789abcdef" for character in value[8:])
            ):
                raise ValueError("Operational alert notification id is invalid")
        return values


class AIOperationalAlertAcknowledgementItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: str
    alert_type: OperationalAlertType
    status: Literal["unread", "read", "handled"]
    created_at: str
    read_at: str
    handled_at: str
    acknowledged: bool


class AIOperationalAlertAcknowledgementReportData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-operational-alert-acknowledgement-v1"] = (
        "ai-operational-alert-acknowledgement-v1"
    )
    generated_at: str
    notification_count: int = Field(ge=1, le=96)
    recipient_count: int = Field(ge=1, le=16)
    complete_delivery_set: bool
    all_acknowledged: bool
    items: list[AIOperationalAlertAcknowledgementItemData]


class AIEvalRunData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-eval-run-v1"] = "ai-eval-run-v1"
    id: str
    suite_id: str
    dataset_version: str
    dataset_hash: str
    runner_version: str
    mode: Literal["OFFLINE_FAKE", "LIVE_PROVIDER"]
    skill_id: str
    skill_version: str
    skill_hash: str
    prompt_version: str
    prompt_hash: str
    provider: str
    model: str
    status: Literal["PASSED", "FAILED", "ERROR"]
    case_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    metrics: dict[str, float | None]
    created_by: str
    created_at: str
    completed_at: str
    raw_cases_recorded: Literal[False] = False
