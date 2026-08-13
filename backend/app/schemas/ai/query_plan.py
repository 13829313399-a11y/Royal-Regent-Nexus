from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai.tool import StrictToolInput


class AIQueryOperation(StrEnum):
    LIST = "LIST"
    GET = "GET"


class AIQueryOperator(StrEnum):
    EQ = "EQ"
    CONTAINS = "CONTAINS"
    GTE = "GTE"
    LTE = "LTE"


class AIQuerySortDirection(StrEnum):
    ASC = "ASC"
    DESC = "DESC"


class AIQueryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    operator: AIQueryOperator
    # Values remain strings so business identifiers such as 000123 never lose
    # leading zeroes during model validation.
    value: str = Field(min_length=1, max_length=128)


class AIQuerySort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    direction: AIQuerySortDirection


class AIQueryPlan(BaseModel):
    """Closed, single-domain query intent. It has no SQL representation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9_]*$")
    operation: AIQueryOperation
    factory_scope: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...] = (
        Field(default=(), max_length=1)
    )
    filters: tuple[AIQueryFilter, ...] = Field(default=(), max_length=8)
    sort: tuple[AIQuerySort, ...] = Field(default=(), max_length=2)
    page_size: int = Field(default=20, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10_000)
    metric_ids: tuple[
        Annotated[
            str,
            Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9_.]*$"),
        ],
        ...,
    ] = Field(default=(), max_length=4)


class SemanticSchedulingBacklogInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    due_date_eq: str = Field(default="", max_length=10)
    due_date_gte: str = Field(default="", max_length=10)
    due_date_lte: str = Field(default="", max_length=10)
    order_no: str = Field(default="", max_length=128)
    item_no: str = Field(default="", max_length=128)
    mold_no: str = Field(default="", max_length=128)
    priority_code: str = Field(default="", pattern=r"^(?:|NORMAL|URGENT|CRITICAL)$")
    sort_direction: AIQuerySortDirection = AIQuerySortDirection.ASC
    limit: int = Field(default=20, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10_000)
