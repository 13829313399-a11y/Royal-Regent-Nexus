from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.carton_procurement import CartonLocationAllocation

class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)

class SupplierMarkTemplateOut(BaseModel):
    id: str
    customer_name: str
    po: str
    item: str
    contract_number: str
    version: int
    check_status: str
    manual_released: bool
    excel_file_name: str
    pdf_file_name: str
    created_at: str

class CommitmentSave(Payload):
    issue_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=0)
    promised_date: date


class BatchCommitmentLine(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    order_line_id: str = Field(min_length=1, max_length=96)
    issue_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=0)
    promised_date: date


class BatchCommitmentSave(Payload):
    lines: list[BatchCommitmentLine] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.order_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("批量接单不能重复引用同一纸品")
        return self


class SupplierDocumentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    kind: Literal["PURCHASE", "DELIVERY"]
    id: str = Field(min_length=1, max_length=96)


class SupplierDocumentExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[SupplierDocumentSelection] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_documents(self):
        keys = {(item.factory_id, item.kind, item.id) for item in self.documents}
        if len(keys) != len(self.documents):
            raise ValueError("导出单据不能重复")
        return self

class ShipLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_line_id: str = Field(min_length=1, max_length=96)
    issue_id: str = Field(min_length=1, max_length=96)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)

class UnmatchedShipLine(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_sheet: str = Field(min_length=1, max_length=128)
    source_row: int = Field(ge=1)
    contract_no: str = Field(default="", max_length=128)
    item_no: str = Field(min_length=1, max_length=128)
    packaging_type: str = Field(min_length=1, max_length=64)
    paper_quality: str = Field(min_length=1, max_length=128)
    specification: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit: str = Field(default="个", min_length=1, max_length=32)
    unit_price: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=6)

class ShipmentCreate(Payload):
    request_id: str = Field(min_length=8, max_length=128)
    delivery_note_no: str = Field(min_length=1, max_length=128)
    delivery_date: date
    lines: list[ShipLine] = Field(default_factory=list, max_length=200)
    unmatched_lines: list[UnmatchedShipLine] = Field(default_factory=list, max_length=200)
    @model_validator(mode="after")
    def unique_lines(self):
        if not self.lines and not self.unmatched_lines or len(self.lines) + len(self.unmatched_lines) > 200:
            raise ValueError("送货单须有 1 至 200 行纸品")
        if len({line.order_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("同一发货单不能重复引用同一纸品明细")
        if len({(line.source_sheet, line.source_row) for line in self.unmatched_lines}) != len(self.unmatched_lines):
            raise ValueError("同一发货单不能重复引用原表行")
        return self

class ReceiveLine(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    shipment_line_id: str = Field(min_length=1, max_length=96)
    received_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    damaged_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unusable_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    paper_quality: str = Field(default="", max_length=128)
    specification: str = Field(default="", max_length=255)
    location_allocations: list[CartonLocationAllocation] = Field(default_factory=list, max_length=100)
    difference_reason: str = Field(default="", max_length=1000)
    no_order_decision: Literal["", "SAMPLE", "WRONG_DELIVERY"] = ""
    customer_code: str = Field(default="", max_length=64)
    sample_purpose: str = Field(default="", max_length=255)
    requested_by: str = Field(default="", max_length=128)
    unit: str = Field(default="", max_length=32)

class ShipmentReceive(Payload):
    correction_reason: str = Field(default="", max_length=1000)
    split_confirmation: str = Field(default="", max_length=64)
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=1)
    acceptance_date: date
    lines: list[ReceiveLine] = Field(min_length=1, max_length=200)


class SampleReceiptLink(Payload):
    order_line_id: str = Field(min_length=1, max_length=96)
    expected_order_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=1000)


class ShipmentLineLink(Payload):
    order_line_id: str = Field(min_length=1, max_length=96)
    customer_code: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    expected_order_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=1000)


class SupplierMarkAssetOrderOut(BaseModel):
    id: str
    customer_name: str
    contract_no: str
    customer_po: str
    item_no: str


class SupplierMarkAssetOut(BaseModel):
    id: str
    file_name: str
    kind: str
    size_bytes: int
    contract_number: str
    created_at: str
    orders: list[SupplierMarkAssetOrderOut]
