from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai.tool import StrictToolInput

# AI-B9 Carton Procurement Field Policy v1 excludes suppliers, quantities,
# prices, currencies, lines, notes, receipts, inventory values and closings.
CARTON_PROCUREMENT_AI_SAFE_ITEM_FIELDS = frozenset(
    {
        "order_id",
        "order_no",
        "customer_name",
        "contract_no",
        "item_no",
        "product_name",
        "order_date",
        "due_date",
        "status",
        "revision",
        "updated_at",
    }
)


class CartonProcurementSummaryListInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    status: Literal[
        "",
        "DRAFT",
        "PENDING_SUPPLIER",
        "CONFIRMED",
        "PARTIALLY_RECEIVED",
        "COMPLETED",
        "CANCELLED",
    ] = ""
    keyword: str = Field(default="", max_length=64)
    limit: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10_000)

    @field_validator("keyword")
    @classmethod
    def strip_keyword(cls, value: str) -> str:
        return value.strip()


class AICartonProcurementSummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$",
    )
    order_no: str = Field(min_length=1, max_length=64)
    customer_name: str = Field(max_length=255)
    contract_no: str = Field(max_length=128)
    item_no: str = Field(max_length=128)
    product_name: str = Field(max_length=255)
    order_date: str = Field(max_length=10)
    due_date: str = Field(max_length=10)
    status: str = Field(max_length=32)
    revision: int = Field(ge=1)
    updated_at: str = Field(max_length=40)


class AICartonProcurementSummaryListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["carton-procurement-summary-v1"] = (
        "carton-procurement-summary-v1"
    )
    result_type: Literal["carton_procurement.summary_list"] = (
        "carton_procurement.summary_list"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=40)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=10_000)
    returned: int = Field(ge=0, le=20)
    truncated: bool
    orders: list[AICartonProcurementSummaryItem] = Field(max_length=20)
