from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EvalCategory = Literal[
    "CHINESE_LANGUAGE",
    "BUSINESS_GROUNDING",
    "FILE",
    "VISION",
    "SCHEDULING",
    "SECURITY",
    "RESILIENCE",
    "ACTION",
]


class AIEvalToolExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    required_arguments: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        max_length=16,
    )


class AIEvalExpected(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_id: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    tools: tuple[AIEvalToolExpectation, ...] = Field(default=(), max_length=6)
    evidence_levels: tuple[str, ...] = Field(default=(), max_length=5)
    required_answer_terms: tuple[str, ...] = Field(default=(), max_length=12)
    forbidden_answer_terms: tuple[str, ...] = Field(default=(), max_length=12)
    error_code: str = Field(default="", max_length=96)
    grounded_claim_count: int = Field(default=0, ge=0, le=32)
    citation_count: int = Field(default=0, ge=0, le=32)
    preview_state: Literal["NONE", "PREVIEW", "EXECUTED"] = "NONE"


class AIEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,127}$")
    category: EvalCategory
    user_text: str = Field(min_length=1, max_length=4000)
    factory_id: str = Field(default="", max_length=64)
    route_name: str = Field(default="", max_length=96)
    expected: AIEvalExpected
    tags: tuple[str, ...] = Field(default=(), max_length=12)

    @field_validator("user_text", "factory_id", "route_name")
    @classmethod
    def normalized_text(cls, value: str) -> str:
        return value.strip()


class AIEvalDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ai-eval-dataset-v1"] = "ai-eval-dataset-v1"
    suite_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,127}$")
    dataset_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    mode: Literal["OFFLINE_FAKE", "LIVE_PROVIDER"]
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    skill_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    prompt_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    cases: tuple[AIEvalCase, ...] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_case_ids(self) -> AIEvalDataset:
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Eval case ids must be unique")
        if any(case.expected.skill_id != self.skill_id for case in self.cases):
            raise ValueError("Eval case Skill must match dataset Skill")
        return self


class AIEvalToolObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    arguments: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        max_length=16,
    )


class AIEvalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_skill_id: str
    answer_text: str = Field(default="", max_length=16000)
    tool_calls: tuple[AIEvalToolObservation, ...] = Field(default=(), max_length=6)
    evidence_levels: tuple[str, ...] = Field(default=(), max_length=8)
    error_code: str = Field(default="", max_length=96)
    grounded_claims_with_evidence: int = Field(default=0, ge=0, le=32)
    correct_citations: int = Field(default=0, ge=0, le=32)
    preview_state: Literal["NONE", "PREVIEW", "EXECUTED"] = "NONE"
    unauthorized_action: bool = False
    cross_factory_leakage: bool = False


class AIEvalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    reason_codes: tuple[str, ...]
    tool_selection_correct: int
    tool_selection_actual: int
    tool_selection_expected: int
    tool_argument_correct: int
    tool_argument_expected: int
    grounded_claims_with_evidence: int
    grounded_claims_expected: int
    correct_citations: int
    citations_expected: int
    unauthorized_action: bool
    cross_factory_leakage: bool
    preview_executed_mislabel: bool


class AIEvalAggregateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_success_rate: float
    grounded_claim_rate: float | None
    citation_accuracy: float | None
    tool_selection_precision: float | None
    tool_argument_accuracy: float | None
    unauthorized_action_rate: float
    cross_factory_leakage_rate: float
    preview_executed_mislabel_rate: float


class AIEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ai-eval-report-v1"] = "ai-eval-report-v1"
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
    passed: bool
    results: tuple[AIEvalCaseResult, ...]
    metrics: AIEvalAggregateMetrics
    raw_prompt_recorded: Literal[False] = False
    raw_tool_result_recorded: Literal[False] = False
    chain_of_thought_recorded: Literal[False] = False
