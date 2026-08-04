from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.injection_scheduling_execution import InjectionSchedulingPlanOut


class StrictWriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InjectionSchedulingObjectiveWeights(StrictWriteModel):
    tardiness_weight: int = Field(default=100, ge=0, le=1000)
    transition_weight: int = Field(default=2, ge=0, le=100)
    class_gap_weight: float = Field(default=1.5, ge=0, le=100)
    load_balance_weight: int = Field(default=25, ge=0, le=1000)
    existing_task_move_cost: int = Field(default=40, ge=0, le=1000)


class InjectionSchedulingRunCreate(StrictWriteModel):
    factory_id: str
    plan_id: str = Field(min_length=1, max_length=96)
    expected_plan_revision: int = Field(ge=1)
    rule_revision: int = Field(ge=1)
    mode: Literal["PREVIEW"] = "PREVIEW"
    horizon_start: str = Field(min_length=1, max_length=32)
    horizon_end: str = Field(min_length=1, max_length=32)
    order_ids: list[str] = Field(default_factory=list, max_length=500)
    respect_locked_tasks: Literal[True] = True
    solver: Literal["HEURISTIC", "CP_SAT", "AUTO"] = "HEURISTIC"
    time_limit_seconds: int = Field(default=10, ge=1, le=30)
    objective_weights: InjectionSchedulingObjectiveWeights = Field(
        default_factory=InjectionSchedulingObjectiveWeights
    )
    scenario_group_id: str = Field(default="", max_length=96)
    scenario_name: str = Field(default="方案 A", min_length=1, max_length=128)
    alternative_no: int = Field(default=1, ge=1, le=9)
    replay_of_run_id: str | None = Field(default=None, max_length=96)

    @field_validator(
        "factory_id",
        "plan_id",
        "scenario_group_id",
        "scenario_name",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("replay_of_run_id")
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
    def validate_horizon(self):
        try:
            start = datetime.fromisoformat(self.horizon_start)
            end = datetime.fromisoformat(self.horizon_end)
        except ValueError as exc:
            raise ValueError("排期范围必须是 ISO 8601 时间") from exc
        if start >= end:
            raise ValueError("排期开始时间必须早于结束时间")
        return self


class InjectionSchedulingRunApply(StrictWriteModel):
    factory_id: str
    expected_plan_revision: int = Field(ge=1)
    expected_rule_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    review_override_reason: str = Field(default="", max_length=2000)

    @field_validator("factory_id", "request_id", "review_override_reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingRunAssignmentOut(BaseModel):
    id: str
    order_id: str
    existing_task_id: str | None
    mold_id: str | None
    mold_copy_no: int
    machine_id: str | None
    sequence_no: int | None
    planned_start: str
    planned_finish: str
    setup_minutes: int
    production_minutes: int
    planned_downtime_minutes: int
    changeover_type: str
    decision: Literal["PASS", "REVIEW_REQUIRED", "UNASSIGNED"]
    score: float | None
    explanation: dict[str, Any]
    unassigned_reason_code: str


class InjectionSchedulingRunOut(BaseModel):
    id: str
    factory_id: str
    plan_id: str
    expected_plan_revision: int
    rule_set_id: str
    rule_revision: int
    mode: Literal["PREVIEW"]
    solver_type: Literal["HEURISTIC", "CP_SAT"]
    solver_version: str
    requested_solver: Literal["HEURISTIC", "CP_SAT", "AUTO"]
    solver_status: Literal[
        "NOT_RUN",
        "HEURISTIC",
        "OPTIMAL",
        "FEASIBLE",
        "INFEASIBLE",
        "TIME_LIMIT",
        "UNAVAILABLE",
    ]
    fallback_used: bool
    fallback_reason: str
    scenario_group_id: str
    scenario_name: str
    alternative_no: int
    replay_of_run_id: str | None
    status: Literal[
        "CREATED",
        "VALIDATING",
        "GENERATING_CANDIDATES",
        "SOLVING",
        "SUCCEEDED",
        "PARTIAL",
        "FAILED",
        "CANCELLED",
        "APPLIED",
    ]
    horizon_start: str
    horizon_end: str
    objective_config: dict[str, Any]
    summary: dict[str, Any]
    error_detail: str
    started_at: str
    finished_at: str
    applied_at: str
    created_by: str
    created_by_name: str
    applied_by: str
    applied_by_name: str
    created_at: str
    revision: int
    assignments: list[InjectionSchedulingRunAssignmentOut]


class InjectionSchedulingRunListOut(BaseModel):
    factory_id: str
    items: list[InjectionSchedulingRunOut]


class InjectionSchedulingRunApplyOut(BaseModel):
    run: InjectionSchedulingRunOut
    plan: InjectionSchedulingPlanOut
    audit_sequence: int
    idempotent_replay: bool = False
