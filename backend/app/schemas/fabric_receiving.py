from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ReceiptBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: str = Field(min_length=1, max_length=32)
    location: str = Field(min_length=1, max_length=128)
    dye_lot: str = Field(default="", max_length=128)
    roll_no: str = Field(default="", max_length=128)


class ReceiveSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Literal["huakang-c"]
    request_id: UUID
    expected_source_revision: int = Field(ge=1)
    expected_receipt_count: int = Field(ge=0)
    receipt_date: date
    accounting_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    delivery_reference: str = Field(min_length=1, max_length=128)
    delivery_note_date: date | None = None
    material_category: Literal["FABRIC", "ACCESSORY", "THREAD"]
    prior_received_quantity: str | None = Field(default=None, min_length=1, max_length=32)
    difference_reason: str = Field(default="", max_length=1000)
    note: str = Field(default="", max_length=2000)
    batches: list[ReceiptBatchInput] = Field(min_length=1, max_length=200)
    confirmed: bool = False


class ReceiveSourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_line_id: str = Field(min_length=1, max_length=128)
    expected_source_revision: int = Field(ge=1)
    expected_receipt_count: int = Field(ge=0)
    material_category: Literal["FABRIC", "ACCESSORY", "THREAD"]
    difference_reason: str = Field(default="", max_length=1000)
    batches: list[ReceiptBatchInput] = Field(min_length=1, max_length=200)


class ReceiveSourcesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Literal["huakang-c"]
    request_id: UUID
    receipt_date: date
    delivery_reference: str = Field(min_length=1, max_length=128)
    delivery_note_date: date | None = None
    note: str = Field(default="", max_length=2000)
    items: list[ReceiveSourceItem] = Field(min_length=1, max_length=50)
    confirmed: bool = False
