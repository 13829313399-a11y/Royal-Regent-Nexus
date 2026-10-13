from datetime import date
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class IssuerInput(Strict):
    factory_id: Literal['huakang-c']
    name: str = Field(default='', max_length=255)
    supplier_id: str = Field(default='', max_length=64)
    request_id: UUID = Field(default_factory=uuid4)
    kind: Literal['SUPPLIER', 'REQUESTOR']
    valid_days: int = Field(default=30, ge=1, le=365)


class IssuerRevoke(Strict):
    factory_id: Literal['huakang-c']
    expected_revision: int = Field(ge=1)
    request_id: UUID = Field(default_factory=uuid4)


class IssuerRenew(IssuerRevoke):
    valid_days: int = Field(default=365, ge=1, le=365)


class IssuerBind(IssuerRevoke):
    supplier_id: str = Field(min_length=1, max_length=64)


class HandoverLine(Strict):
    id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    source_line: str = Field(default='', max_length=128)
    item_code: str = Field(default='', max_length=128)
    item_name: str = Field(default='', max_length=255)
    specification: str = Field(default='', max_length=255)
    color: str = Field(default='', max_length=128)
    quantity: str = Field(default='', max_length=32, pattern=r'^(?:|[0-9]+(?:\.[0-9]{1,6})?)$')
    unit: str = Field(default='', max_length=32)
    material_category: Literal['FABRIC', 'ACCESSORY', 'THREAD'] = 'FABRIC'
    lot: str = Field(default='', max_length=128)
    roll_no: str = Field(default='', max_length=128)
    roll_quantities: str = Field(default='', max_length=2000)
    contract_no: str = Field(default='', max_length=128)
    production_no: str = Field(default='', max_length=128)
    product_no: str = Field(default='', max_length=128)
    note: str = Field(default='', max_length=1000)
    unit_price: str = Field(default='', max_length=32, pattern=r'^(?:|[0-9]+(?:\.[0-9]{1,6})?)$')
    price_unit: str = Field(default='', max_length=32)
    currency: Literal['', 'CNY', 'HKD', 'USD', 'EUR'] = ''
    price_note: str = Field(default='', max_length=1000)


class HandoverData(Strict):
    kind: Literal['DELIVERY', 'ISSUE'] = 'DELIVERY'
    source_no: str = Field(default='', max_length=128)
    document_date: date | None = None
    counterparty: str = Field(default='', max_length=255)
    supplier_id: str = Field(default='', max_length=64)
    contract_no: str = Field(default='', max_length=128)
    production_no: str = Field(default='', max_length=128)
    product_no: str = Field(default='', max_length=128)
    note: str = Field(default='', max_length=1000)
    lines: list[HandoverLine] = Field(default_factory=list, max_length=200)


class DocumentSave(Strict):
    request_id: UUID
    expected_revision: int = Field(ge=1)
    data: HandoverData


class DocumentAction(Strict):
    request_id: UUID
    expected_revision: int = Field(ge=1)
    acknowledge_warnings: bool = False
    reason: str = Field(default='', max_length=1000)
    data: HandoverData | None = None


class ScanInput(Strict):
    factory_id: Literal['huakang-c']
    code: str = Field(min_length=1, max_length=160)


class PostingLine(Strict):
    line_id: str = Field(min_length=1, max_length=64)
    quantity: str = Field(min_length=1, max_length=32)
    batch_id: str = Field(default='', max_length=64)
    location_id: str = Field(default='', max_length=64)
    lot: str = Field(default='', max_length=128)
    roll_no: str = Field(default='', max_length=128)
    purchase_source_id: str = Field(default='', max_length=64)
    expected_source_revision: int | None = Field(default=None, ge=1)
    expected_receipt_count: int | None = Field(default=None, ge=0)
    difference_reason: str = Field(default='', max_length=1000)


class PostingInput(Strict):
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=1)
    expected_inventory_revision: int = Field(ge=0)
    code_version: int = Field(ge=1)
    business_date: date
    lines: list[PostingLine] = Field(min_length=1, max_length=100)
