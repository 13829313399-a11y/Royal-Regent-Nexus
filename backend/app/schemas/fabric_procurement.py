"""Reserved authenticated purchase-feed contract; no Kingdee credentials or fetcher."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class PurchaseSourceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_line_id: str = Field(min_length=1, max_length=128)
    warehouse_line_id: str = Field(default="", max_length=64)
    expected_line_revision: int | None = Field(default=None, ge=1)
    status: Literal["PENDING", "RETURNED"]
    source_category: Literal["PURCHASE", "SUPPLEMENT"] = "PURCHASE"
    supplement_no: str = Field(default="", max_length=128)
    style_no: str = Field(default="", max_length=255)
    workshop_group: str = Field(default="", max_length=255)
    release_date: str = Field(default="", max_length=32)
    order_no: str = Field(min_length=1, max_length=128)
    supplier: str = Field(min_length=1, max_length=255)
    production_no: str = Field(default="", max_length=255)
    plan_no: str = Field(default="", max_length=255)
    material_code: str = Field(min_length=1, max_length=128)
    material_name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=32)
    ordered_quantity: str = Field(max_length=32)
    reported_received_quantity: str | None = Field(default=None, max_length=32)
    unit_price: str | None = Field(default=None, max_length=32)
    order_date: str = Field(default="", max_length=32)
    contract_no: str = Field(default="", max_length=255)
    supplier_reply: str = Field(default="", max_length=255)
    second_reply: str = Field(default="", max_length=255)
    old_material_code: str = Field(default="", max_length=128)
    delivery_detail: str = Field(default="", max_length=10000)
    delivery_note_no: str = Field(default="", max_length=255)
    delivery_note_date: str = Field(default="", max_length=32)
    reported_receipt_date: str = Field(default="", max_length=32)
    note: str = Field(default="", max_length=10000)
    warehouse_note: str = Field(default="", max_length=10000)


class PurchaseFeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_system: Literal["KINGDEE"]
    snapshot_id: str = Field(min_length=1, max_length=128)
    lines: list[PurchaseSourceLine] = Field(min_length=1, max_length=5000)


class SourcePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Literal["huakang-c"]
    feed: PurchaseFeed


class SourceApplyRequest(SourcePreviewRequest):
    preview_token: str = Field(min_length=64, max_length=64)
    request_id: UUID
    confirmed: bool = False
    acknowledge_excluded: bool = False


class ReviewChangesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Literal["huakang-c"]
    expected_revision: int = Field(ge=1)


class WithdrawImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Literal["huakang-c"]
    preview_token: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=500)
    confirmed: bool = False
