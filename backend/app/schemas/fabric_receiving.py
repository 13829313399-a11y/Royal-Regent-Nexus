from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReceiptBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: str = Field(min_length=1, max_length=32)
    location: str = Field(min_length=1, max_length=128)
    location_id: str = Field(default='', max_length=64)
    dye_lot: str = Field(default="", max_length=128)
    roll_no: str = Field(default="", max_length=128)


class ReceiptPriceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_price: str = Field(default='', max_length=32)
    price_unit: str = Field(default='', max_length=32)
    currency: Literal['', 'CNY', 'HKD', 'USD', 'EUR'] = ''

    @field_validator('unit_price', 'price_unit')
    @classmethod
    def strip_price_fields(cls, value):
        return value.strip()


class ReceiveSourceRequest(ReceiptPriceInput):
    model_config = ConfigDict(extra="forbid")
    delivery_quantity: str = Field(default='', max_length=32)
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


class ReverseReceiptRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=0)
    business_date: date
    reason: str = Field(min_length=1, max_length=1000)
    confirmed: bool = False


class ReceiveSourceItem(ReceiptPriceInput):
    model_config = ConfigDict(extra="forbid")
    delivery_quantity: str = Field(default='', max_length=32)
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
