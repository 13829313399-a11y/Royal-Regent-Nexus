from datetime import date
from typing import Annotated, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.fabric_receiving import ReceiptCounts


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
    material_category: Literal['', 'FABRIC', 'ACCESSORY', 'THREAD'] = 'FABRIC'
    lot: str = Field(default='', max_length=128)
    roll_no: str = Field(default='', max_length=128)
    roll_quantities: str = Field(default='', max_length=2000)
    purchase_detail_id: str = Field(default='', max_length=128)
    purchase_order_no: str = Field(default='', max_length=128)
    ordered_quantity: str = Field(default='', max_length=32, pattern=r'^(?:|[0-9]+(?:\.[0-9]{1,6})?)$')
    contract_no: str = Field(default='', max_length=128)
    production_no: str = Field(default='', max_length=128)
    plan_no: str = Field(default='', max_length=255)
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
    purchase_order_no: str = Field(default='', max_length=128)
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


class ReceiptLinkInput(Strict):
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=1)
    line_id: str = Field(min_length=1, max_length=64)
    receipt_id: str = Field(min_length=1, max_length=64)


class ReceiptUnlinkInput(Strict):
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=1)
    expected_processed: str = Field(pattern=r'^[0-9]{1,12}(?:\.[0-9]{1,6})?$')
    link_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)


class RejectionFollowupInput(Strict):
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=1)
    observation_request_id: UUID
    line_id: str = Field(min_length=1, max_length=64)
    status: Literal['PENDING_REDELIVERY', 'RESOLVED']
    reason: str = Field(min_length=1, max_length=1000)


class ReceiptPurchaseLinkInput(Strict):
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=1)
    operation_ids: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(min_length=1, max_length=200)
    purchase_source_id: str = Field(min_length=1, max_length=64)
    expected_source_revision: int = Field(ge=1)
    expected_receipt_count: int = Field(ge=0)
    difference_reason: str = Field(default='', max_length=1000)


class PostingLine(Strict):
    line_id: str = Field(min_length=1, max_length=64)
    quantity: str = Field(min_length=1, max_length=32)
    batch_id: str = Field(default='', max_length=64)
    location_id: str = Field(default='', max_length=64)
    lot: str = Field(default='', max_length=128)
    roll_no: str = Field(default='', max_length=128)
    roll_no_is_blank: bool = False
    purchase_source_id: str = Field(default='', max_length=64)
    expected_source_revision: int | None = Field(default=None, ge=1)
    expected_receipt_count: int | None = Field(default=None, ge=0)
    difference_reason: str = Field(default='', max_length=1000)
    procurement_pending_reason: str = Field(default='', max_length=1000)
    receipt_counts: ReceiptCounts | None = None


class PostingInput(Strict):
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=1)
    expected_inventory_revision: int = Field(ge=0)
    code_version: int = Field(ge=1)
    business_date: date
    lines: list[PostingLine] = Field(min_length=1, max_length=100)
    delivery_quantities: dict[
        Annotated[str, Field(min_length=1, max_length=64)],
        Annotated[str, Field(min_length=1, max_length=32)],
    ] = Field(default_factory=dict, max_length=100)
    manual_receipt_reviews: dict[
        Annotated[str, Field(min_length=1, max_length=64)],
        Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')],
    ] = Field(default_factory=dict, max_length=100)
