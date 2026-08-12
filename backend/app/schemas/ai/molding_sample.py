from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai.tool import StrictToolInput

# AI-B9 Molding Sample Field Policy v1. The AI boundary intentionally excludes
# materials, quantities, weights, costs, remarks, reasons, owners and reports.
MOLDING_SAMPLE_AI_SAFE_ITEM_FIELDS = frozenset(
    {
        "order_id",
        "order_number",
        "product_name",
        "client_name",
        "status",
        "stage",
        "order_date",
        "production_factory_id",
        "updated_at",
    }
)


class MoldingSampleSummaryListInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    status: str = Field(default="", max_length=32)
    keyword: str = Field(default="", max_length=64)
    limit: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10_000)

    @field_validator("status", "keyword")
    @classmethod
    def strip_filters(cls, value: str) -> str:
        return value.strip()


class AIMoldingSampleSummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    )
    order_number: str = Field(max_length=128)
    product_name: str = Field(max_length=255)
    client_name: str = Field(max_length=255)
    status: str = Field(max_length=32)
    stage: str = Field(max_length=20)
    order_date: str = Field(max_length=20)
    production_factory_id: str | None = Field(default=None, max_length=64)
    updated_at: str = Field(max_length=32)


class AIMoldingSampleSummaryListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["molding-sample-summary-v1"] = (
        "molding-sample-summary-v1"
    )
    result_type: Literal["molding_sample.summary_list"] = (
        "molding_sample.summary_list"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=40)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=10_000)
    returned: int = Field(ge=0, le=20)
    truncated: bool
    orders: list[AIMoldingSampleSummaryItem] = Field(max_length=20)
