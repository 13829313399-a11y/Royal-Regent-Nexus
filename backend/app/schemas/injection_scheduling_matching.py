from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.injection_scheduling_execution import InjectionSchedulingPlanOut


class StrictWriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InjectionSchedulingMatchEvaluate(StrictWriteModel):
    factory_id: str
    order_id: str = Field(min_length=1, max_length=96)
    machine_ids: list[str] = Field(default_factory=list, max_length=200)
    allow_scheduled: bool = False

    @field_validator("factory_id", "order_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("machine_ids")
    @classmethod
    def normalize_machine_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("候选机台 ID 不能重复")
        return normalized


class InjectionSchedulingMatchReasonOut(BaseModel):
    rule_code: str
    label: str
    detail: str


class InjectionSchedulingScoreBreakdownOut(BaseModel):
    rule_code: str
    label: str
    delta: float
    explanation: str


class InjectionSchedulingMachineMatchOut(BaseModel):
    machine_id: str
    machine_code: str
    decision: Literal["PASS", "REVIEW_REQUIRED", "FAIL"]
    score: float | None
    hard_failures: list[InjectionSchedulingMatchReasonOut]
    warnings: list[InjectionSchedulingMatchReasonOut]
    advisories: list[InjectionSchedulingMatchReasonOut] = Field(default_factory=list)
    score_breakdown: list[InjectionSchedulingScoreBreakdownOut]
    explanation: str
    rule_set_id: str
    rule_set_revision: int


class InjectionSchedulingMatchEvaluationOut(BaseModel):
    factory_id: str
    order_id: str
    mold_id: str
    rule_set_id: str
    rule_set_revision: int
    results: list[InjectionSchedulingMachineMatchOut]


class InjectionSchedulingSuggestionConfirm(StrictWriteModel):
    factory_id: str
    order_id: str = Field(min_length=1, max_length=96)
    machine_id: str = Field(min_length=1, max_length=96)
    expected_plan_revision: int = Field(ge=1)
    expected_rule_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    override_reason: str = Field(default="", max_length=2000)

    @field_validator(
        "factory_id",
        "order_id",
        "machine_id",
        "request_id",
        "override_reason",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingSuggestionOut(BaseModel):
    plan: InjectionSchedulingPlanOut
    match: InjectionSchedulingMachineMatchOut
    audit_sequence: int
