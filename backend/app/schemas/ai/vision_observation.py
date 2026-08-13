from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.ai.evidence import AIEvidenceReferenceV1
from app.schemas.ai.scheduling import (
    AIInjectionSchedulingBacklogData,
    AIInjectionSchedulingBacklogItem,
)

SafeBusinessId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._/\-]+$",
    ),
]
SafeDateText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[0-9./\-]+$",
    ),
]
SafeQuantityText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[0-9,.\-]+$",
    ),
]

VisionObservedField = Literal[
    "order_no",
    "item_no",
    "mold_no",
    "delivery_due_date",
    "outstanding_quantity",
]


class AIVisionObservationRow(BaseModel):
    """One untrusted image row; identifiers stay strings to preserve leading zeroes."""

    model_config = ConfigDict(extra="forbid")

    row_index: int = Field(ge=1, le=200)
    order_no: SafeBusinessId | None = None
    order_no_confidence: float = Field(ge=0, le=1)
    item_no: SafeBusinessId | None = None
    item_no_confidence: float = Field(ge=0, le=1)
    mold_no: SafeBusinessId | None = None
    mold_no_confidence: float = Field(ge=0, le=1)
    delivery_due_date: SafeDateText | None = None
    delivery_due_date_confidence: float = Field(ge=0, le=1)
    outstanding_quantity: SafeQuantityText | None = None
    outstanding_quantity_confidence: float = Field(ge=0, le=1)
    row_confidence: float = Field(ge=0, le=1)
    uncertain_fields: tuple[VisionObservedField, ...] = Field(
        default=(), max_length=5
    )

    @field_validator("uncertain_fields")
    @classmethod
    def unique_uncertain_fields(
        cls, value: tuple[VisionObservedField, ...]
    ) -> tuple[VisionObservedField, ...]:
        if len(value) != len(set(value)):
            raise ValueError("uncertain fields must be unique")
        return value

    @model_validator(mode="after")
    def confidence_matches_presence(self) -> AIVisionObservationRow:
        for field_name in (
            "order_no",
            "item_no",
            "mold_no",
            "delivery_due_date",
            "outstanding_quantity",
        ):
            value = getattr(self, field_name)
            confidence = getattr(self, f"{field_name}_confidence")
            if value is None and confidence != 0:
                raise ValueError("missing observed fields must have zero confidence")
        return self


class AIVisionProviderObservation(BaseModel):
    """Strict Stage-A JSON returned by the multimodal Provider."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = "1"
    domain: Literal["INJECTION_SCHEDULING_BACKLOG"] = (
        "INJECTION_SCHEDULING_BACKLOG"
    )
    overall_confidence: float = Field(ge=0, le=1)
    instructions_detected: bool
    unreadable_region_count: int = Field(ge=0, le=100)
    rows: tuple[AIVisionObservationRow, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def reject_duplicate_rows(self) -> AIVisionProviderObservation:
        indexes = [row.row_index for row in self.rows]
        if len(indexes) != len(set(indexes)):
            raise ValueError("observation row indexes must be unique")
        exact_keys = [
            (row.order_no, row.item_no)
            for row in self.rows
            if row.order_no is not None and row.item_no is not None
        ]
        if len(exact_keys) != len(set(exact_keys)):
            raise ValueError("duplicate observed order/item rows are not allowed")
        return self


class AIVisionObservationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = "1"
    result_type: Literal["vision.injection_backlog_observation.v1"] = (
        "vision.injection_backlog_observation.v1"
    )
    source_type: Literal["USER_PROVIDED"] = "USER_PROVIDED"
    factory_id: str = Field(min_length=1, max_length=64)
    source_artifact_id: str = Field(pattern=r"^aiart-[0-9a-f]{32}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: str = Field(min_length=20, max_length=40)
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)
    provider_call_count: Literal[1] = 1
    tool_count: Literal[0] = 0
    low_confidence_threshold: Literal[0.8] = 0.8
    observation: AIVisionProviderObservation


class AIVisionFieldComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["mold_no", "delivery_due_date", "outstanding_quantity"]
    observed: str | None
    formal: str | None
    status: Literal["SAME", "DIFFERENT", "UNCONFIRMED"]


class AIVisionComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "MATCHED", "DIFFERENT", "IMAGE_ONLY", "FORMAL_ONLY", "UNCONFIRMED"
    ]
    observation: AIVisionObservationRow | None
    formal: AIInjectionSchedulingBacklogItem | None
    field_comparisons: tuple[AIVisionFieldComparison, ...] = Field(
        default=(), max_length=3
    )
    reason_code: Literal[
        "EXACT_ORDER_ITEM_MATCH",
        "FIELD_DIFFERENCE",
        "NOT_IN_RETURNED_FORMAL_PAGE",
        "NOT_IN_IMAGE_OBSERVATION",
        "LOW_CONFIDENCE",
        "MISSING_MATCH_KEY",
        "AMBIGUOUS_FORMAL_MATCH",
    ]


class AIVisionComparisonData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = "1"
    result_type: Literal["vision.injection_backlog_comparison.v1"] = (
        "vision.injection_backlog_comparison.v1"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str = Field(min_length=1, max_length=64)
    observation_task_id: str = Field(pattern=r"^aitask-[a-f0-9]{32}$")
    source_artifact_id: str = Field(pattern=r"^aiart-[0-9a-f]{32}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observation_evidence: AIEvidenceReferenceV1
    observation: AIVisionProviderObservation
    formal_backlog: AIInjectionSchedulingBacklogData
    comparison_rows: tuple[AIVisionComparisonRow, ...] = Field(max_length=70)
    matched_count: int = Field(ge=0, le=20)
    different_count: int = Field(ge=0, le=20)
    unconfirmed_count: int = Field(ge=0, le=20)
    image_only_count: int = Field(ge=0, le=20)
    formal_only_count: int = Field(ge=0, le=50)
    no_write_performed: Literal[True] = True
