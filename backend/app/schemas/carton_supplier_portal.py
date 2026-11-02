from datetime import date
from decimal import Decimal
from typing import Literal
from app.schemas.carton_mark import CartonMarkAssetWorkflow, CartonMarkDocumentCheckResponse
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
    acknowledge_unaccepted: bool = False

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
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    free_confirmed: bool = False

class UnmatchedShipLine(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_sheet: str = Field(min_length=1, max_length=128)
    source_row: int = Field(ge=1)
    contract_no: str = Field(default="", max_length=128)
    item_no: str = Field(default="", max_length=128)
    packaging_type: str = Field(min_length=1, max_length=64)
    paper_quality: str = Field(min_length=1, max_length=128)
    specification: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit: str = Field(default="个", min_length=1, max_length=32)
    unit_price: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=6)

class ShipmentCreate(Payload):
    registration_mode: Literal["SHIPMENT", "EXISTING_RECEIPT"] = "SHIPMENT"
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
    close_remaining: bool = False
    replenishment_issue_id: str | None = Field(default=None, max_length=96)
    price_action: Literal["MATCH", "PENDING", "PROPOSE", "FREE"] = "MATCH"
    price_reason: str = Field(default="", max_length=1000)
    dimension_unit: Literal["cm", "in"] = "cm"
    zero_price_kind: Literal["FREE", "PENDING"] | None = None
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
    no_order_decision: Literal["", "SAMPLE", "GIFT", "MISC", "WRONG_DELIVERY", "UNORDERED"] = ""
    customer_code: str = Field(default="", max_length=64)
    workshop_id: str = Field(default="", max_length=96)
    sample_purpose: str = Field(default="", max_length=255)
    requested_by: str = Field(default="", max_length=128)
    unit: str = Field(default="", max_length=32)

    @model_validator(mode="after")
    def validate_zero_price(self):
        if self.price_action == "FREE" and self.unit_price != 0:
            raise ValueError("确认免费须填写零单价")
        if self.zero_price_kind and self.unit_price != 0:
            raise ValueError("免费赠送或暂未定价须明确填写零单价")
        return self

class ShipmentReceive(Payload):
    # Old clients explicitly completed a delivery. The current UI defaults WAIT.
    remaining_action: Literal["WAIT", "CLOSE"] = "CLOSE"
    new_delivery_confirmation: bool = False
    correction_reason: str = Field(default="", max_length=1000)
    split_confirmation: str = Field(default="", max_length=64)
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=1)
    acceptance_date: date
    lines: list[ReceiveLine] = Field(min_length=1, max_length=200)


class CancellationAcknowledge(Payload):
    issue_id: str = Field(min_length=1, max_length=96)
    expected_order_revision: int = Field(ge=1)


class RushAcknowledge(Payload):
    expected_rush_version: str | None = Field(default=None, min_length=64, max_length=64)


class ShipmentStatusChange(Payload):
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=1000)


class DeliveryRowSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_sheet: str = Field(min_length=1, max_length=128)
    source_row: int = Field(ge=1)
    order_line_id: str = Field(min_length=1, max_length=96)
    issue_id: str = Field(min_length=1, max_length=96)
    order_revision: int = Field(ge=1)
    source_kind: Literal['REGULAR', 'SPECIAL'] = 'REGULAR'
    special_request_id: str = Field(default='', max_length=96)
    free_confirmed: bool = False

    @model_validator(mode='after')
    def typed_source(self):
        if (self.source_kind == 'SPECIAL') != bool(self.special_request_id):
            raise ValueError('样板或杂单须保留原需求身份，正单不能携带特殊需求身份')
        if self.free_confirmed and self.source_kind != 'SPECIAL':
            raise ValueError('此确认仅用于原表中的样板或杂单免费纸品')
        return self


class ShipmentReceiptLink(Payload):
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=1)
    receipt_id: str = Field(min_length=1, max_length=96)
    expected_receipt_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=1000)


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
    issue_id: str
    customer_name: str
    contract_no: str
    customer_po: str
    item_no: str


class SupplierMarkAssetClassification(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    status: Literal['DRAFT', 'PENDING']


class SupplierMarkAssetOut(BaseModel):
    can_classify: bool = False
    id: str
    revision: int
    file_name: str
    kind: str
    photo_group_id: str | None = None
    size_bytes: int
    contract_number: str
    created_at: str
    orders: list[SupplierMarkAssetOrderOut]
    workflow: CartonMarkAssetWorkflow = Field(default_factory=CartonMarkAssetWorkflow)
    sharing_mode: str = 'ORDER_BOUND'
    shared_supplier_id: str = ''
    shared_supplier_name: str = ''
    binding_status: str = 'UNBOUND'
    pending_bindings: list[dict] = Field(default_factory=list)
    special_orders: list[dict] = Field(default_factory=list)
    associations: list[dict] = Field(default_factory=list)


class SupplierMarkUploadOrderOut(SupplierMarkAssetOrderOut):
    document_no: str
    order_date: str


class SupplierMarkCheckOut(SupplierMarkTemplateOut):
    factory_id: str
    order_id: str
    issue_id: str
    excel_asset_id: str
    qc_ready: bool
    check_result: CartonMarkDocumentCheckResponse


class SupplierMarkAssetUploadOut(BaseModel):
    file_name: str
    status: Literal["created", "duplicate", "failed"]
    message: str = ""
    asset: SupplierMarkAssetOut | None = None


class SupplierMarkPdfRequest(Payload):
    order_id: str = Field(min_length=1, max_length=96)
    issue_id: str = Field(min_length=1, max_length=96)
    excel_asset_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=1)
    layout_id: str = Field(min_length=1, max_length=96)
    engine: Literal["customer_layout", "deepseek_zumiez"] = "customer_layout"
    ai_consent: bool = False
    supplements: dict[Literal["quantity", "carton_total", "dimensions", "gross_weight", "net_weight"], str] = Field(default_factory=dict)
    source_item: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def valid_supplements(self):
        import re
        if self.engine == "deepseek_zumiez" and not self.ai_consent:
            raise ValueError("使用DeepSeek须明确同意发送本单必要文字")
        if any(len(value) > 100 or not re.search(r"\d", value) for value in self.supplements.values()):
            raise ValueError("本单补齐内容须包含数值，最多100字符")
        return self


class MarkLayoutRegion(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=1000)
    y: float = Field(ge=0, le=1000)
    width: float = Field(gt=0, le=1000)
    height: float = Field(gt=0, le=1000)


class MarkLayoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    mode: Literal["front_side", "front_only", "separate_pages"] = "front_side"
    frame_style: Literal["plain", "original_red"] = "plain"
    series: Literal["standard", "zuru"] = "standard"
    paper: Literal["A4", "A3"] = "A4"
    font: Literal["Helvetica", "Courier", "ArialNarrow", "ArialNarrowBold"] = "Helvetica"
    font_size: float = Field(default=11, ge=7, le=16)
    front_percent: int = Field(default=55, ge=40, le=60)
    front_copies: int = Field(default=2, ge=1, le=4)
    side_copies: int = Field(default=2, ge=1, le=4)
    barcode: Literal["Code128", "ITF14", "none"] = "Code128"
    side_address: str = Field(default="", max_length=500)
    instructions: str = Field(default="", max_length=500)
    reference_page: int = Field(default=0, ge=0, le=19)
    logo_region: MarkLayoutRegion | None = None
    stamp_region: MarkLayoutRegion | None = None
    front_artwork_region: MarkLayoutRegion | None = None
    side_artwork_region: MarkLayoutRegion | None = None
    origin_artwork_region: MarkLayoutRegion | None = None
    field_cells: dict[Literal["item", "vendor", "product", "content", "gtin", "vendor_item", "dimensions", "gross_weight"], str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_cells(self):
        import re
        if any(not re.fullmatch(r"[A-Za-z]{1,3}[1-9][0-9]{0,4}", value) for value in self.field_cells.values() if value):
            raise ValueError("字段位置填写 Excel 单元格，如 C15")
        return self


class SupplierMarkLayoutOut(BaseModel):
    id: str
    factory_id: str
    customer_name: str
    name: str
    version: int
    reference_name: str
    created_at: str
    config: MarkLayoutConfig


class SupplierMarkPdfOut(BaseModel):
    asset: SupplierMarkAssetOut
    page_count: int
    warnings: list[str] = Field(default_factory=list)
    layout_id: str
    layout_name: str
    layout_version: int
