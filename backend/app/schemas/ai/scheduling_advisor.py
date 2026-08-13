from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ai.preview import AIPreviewManifestV1, AIScenarioCompareContractV1
from app.schemas.ai.scheduling import AIEntityLink
from app.schemas.ai.tool import StrictToolInput

SchedulingObjective = Literal[
    "BALANCED",
    "DELIVERY_PRIORITY",
    "MINIMIZE_CHANGEOVER",
    "LOAD_BALANCE",
]


class InjectionSchedulingPreviewIntentInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    objective: SchedulingObjective = "BALANCED"
    solver: Literal["HEURISTIC", "CP_SAT", "AUTO"] = "AUTO"
    horizon_days: int = Field(default=14, ge=1, le=30)
    order_scope: Literal["ALL_ELIGIBLE", "SELECTED"] = "ALL_ELIGIBLE"
    order_ids: list[str] = Field(default_factory=list, max_length=500)
    time_limit_seconds: int = Field(default=10, ge=1, le=30)
    scenario_name: str = Field(default="AI 候选方案", min_length=1, max_length=128)
    compare_with_run_id: str | None = Field(default=None, max_length=96)

    @field_validator("factory_id", "scenario_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("compare_with_run_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @field_validator("order_ids")
    @classmethod
    def normalize_order_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(values) or len(normalized) != len(set(normalized)):
            raise ValueError("订单 ID 不能为空或重复")
        return normalized

    @model_validator(mode="after")
    def validate_scope(self):
        if self.order_scope == "SELECTED" and not self.order_ids:
            raise ValueError("SELECTED 范围必须提供 order_ids")
        if self.order_scope == "ALL_ELIGIBLE" and self.order_ids:
            raise ValueError("ALL_ELIGIBLE 范围不能提供 order_ids")
        return self


class InjectionSchedulingPreviewComparisonInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    run_ids: list[str] = Field(min_length=2, max_length=4)

    @field_validator("factory_id")
    @classmethod
    def strip_factory(cls, value: str) -> str:
        return value.strip()

    @field_validator("run_ids")
    @classmethod
    def normalize_run_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(values) or len(normalized) != len(set(normalized)):
            raise ValueError("Run ID 不能为空或重复")
        if any(len(value) > 96 for value in normalized):
            raise ValueError("Run ID 过长")
        return normalized


class AISchedulingMetricDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: int | None
    after: int | None
    change: int | None


class AISchedulingPreviewMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_order_count: int | None = Field(default=None, ge=0)
    scheduled_count: int | None = Field(default=None, ge=0)
    review_count: int | None = Field(default=None, ge=0)
    unassigned_count: int | None = Field(default=None, ge=0)
    moved_task_count: int | None = Field(default=None, ge=0)
    overdue: AISchedulingMetricDelta
    mold_changes: AISchedulingMetricDelta
    dark_to_light_changes: AISchedulingMetricDelta
    load_ratio_min: float | None = Field(default=None, ge=0)
    load_ratio_max: float | None = Field(default=None, ge=0)
    load_ratio_average: float | None = Field(default=None, ge=0)
    solver_elapsed_ms: float | None = Field(default=None, ge=0)


class AISchedulingPreviewRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    plan_id: str
    plan_revision: int = Field(ge=1)
    rule_revision: int = Field(ge=1)
    status: Literal["SUCCEEDED", "PARTIAL"]
    requested_solver: Literal["HEURISTIC", "CP_SAT", "AUTO"]
    actual_solver: Literal["HEURISTIC", "CP_SAT"]
    solver_status: str
    fallback_used: bool
    scenario_group_id: str
    scenario_name: str
    alternative_no: int = Field(ge=1, le=9)
    horizon_start: str
    horizon_end: str
    metrics: AISchedulingPreviewMetrics
    preview_manifest: AIPreviewManifestV1 | None = None


class AIInjectionSchedulingPreviewData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-scheduling-preview-v1"] = "ai-scheduling-preview-v1"
    result_type: Literal["injection_scheduling.preview_run"] = (
        "injection_scheduling.preview_run"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    risk_level: Literal["PREVIEW_WITH_AUDIT"] = "PREVIEW_WITH_AUDIT"
    factory_id: str
    as_of: str
    candidate_label: Literal["候选方案，尚未应用"] = "候选方案，尚未应用"
    applied: Literal[False] = False
    intent_objective: SchedulingObjective
    run: AISchedulingPreviewRunSummary
    entity_links: list[AIEntityLink]


class AIInjectionSchedulingComparisonData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-scheduling-comparison-v1"] = (
        "ai-scheduling-comparison-v1"
    )
    result_type: Literal["injection_scheduling.preview_comparison"] = (
        "injection_scheduling.preview_comparison"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str
    as_of: str
    candidate_label: Literal["候选方案，尚未应用"] = "候选方案，尚未应用"
    comparable_snapshot: bool
    comparison_warning: str
    runs: list[AISchedulingPreviewRunSummary] = Field(min_length=2, max_length=4)
    scenario_compare: AIScenarioCompareContractV1 | None = None
    entity_links: list[AIEntityLink]
