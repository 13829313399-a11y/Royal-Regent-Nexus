from datetime import date, timedelta
from decimal import Decimal
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CartonOrderStatus = Literal[
    "DRAFT",
    "PENDING_SUPPLIER",
    "CONFIRMED",
    "PARTIALLY_RECEIVED",
    "COMPLETED",
    "CANCELLED",
]
CartonReceiptStatus = Literal["DRAFT", "PENDING_CONFIRMATION", "POSTED", "REVERSED"]
CartonReceiptLineSourceType = Literal["FORMAL_ORDER", "AD_HOC"]
CartonMovementType = Literal["INBOUND", "OUTBOUND", "ADJUSTMENT", "REVERSAL"]
CartonClosingStatus = Literal["DRAFT", "PENDING", "CONFIRMED", "LOCKED"]
CartonCustomerStatus = Literal["ACTIVE", "INACTIVE"]
DEFAULT_CARTON_SAFETY_LEAD_DAYS = 3


BUSINESS_IDENTIFIER_RE = re.compile(
    r"^[0-9A-Za-z\u4e00-\u9fff][0-9A-Za-z\u4e00-\u9fff._/#()（）+& -]*[0-9A-Za-z\u4e00-\u9fff]$"
)


def _strip(value: str) -> str:
    return value.strip()


def _validate_iso_date(value: str) -> str:
    value = value.strip()
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc
    return value


def derive_carton_plan_due_date(
    order_date: str,
    customer_due_date: str,
    safety_lead_days: int = DEFAULT_CARTON_SAFETY_LEAD_DAYS,
) -> str:
    order_day = date.fromisoformat(order_date)
    customer_day = date.fromisoformat(customer_due_date)
    if customer_day < order_day:
        raise ValueError("客户交期不能早于下单日期")
    planned_day = customer_day - timedelta(days=safety_lead_days)
    return max(order_day, planned_day).isoformat()


def _validate_business_identifier(value: str, *, label: str) -> str:
    value = value.strip()
    if len(value) == 1 and re.fullmatch(r"[0-9A-Za-z\u4e00-\u9fff]", value):
        return value
    if not BUSINESS_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"{label}格式无效；仅允许中英文、数字、空格及 - _ . / # ( ) + &，且首尾必须为文字或数字"
        )
    return value


class CartonCustomerCreate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    customer_code: str = Field(default="", max_length=64)
    customer_name: str = Field(min_length=1, max_length=255)
    country_region: str = Field(default="", max_length=128)
    contact_name: str = Field(default="", max_length=128)
    contact_phone: str = Field(default="", max_length=64)
    note: str = Field(default="", max_length=2000)
    status: CartonCustomerStatus = "ACTIVE"

    @field_validator(
        "factory_id",
        "customer_code",
        "customer_name",
        "country_region",
        "contact_name",
        "contact_phone",
        "note",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class CartonCustomerUpdate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    customer_code: str | None = Field(default=None, min_length=1, max_length=64)
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    country_region: str | None = Field(default=None, max_length=128)
    contact_name: str | None = Field(default=None, max_length=128)
    contact_phone: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)
    status: CartonCustomerStatus | None = None

    @field_validator(
        "factory_id",
        "customer_code",
        "customer_name",
        "country_region",
        "contact_name",
        "contact_phone",
        "note",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None

    @model_validator(mode="after")
    def validate_change(self):
        if not any(
            getattr(self, field) is not None
            for field in (
                "customer_code",
                "customer_name",
                "country_region",
                "contact_name",
                "contact_phone",
                "note",
                "status",
            )
        ):
            raise ValueError("至少需要提交一项客户资料变更")
        return self


class CartonCustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    customer_code: str
    customer_name: str
    country_region: str
    contact_name: str
    contact_phone: str
    note: str
    status: CartonCustomerStatus
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class CartonCustomerListOut(BaseModel):
    factory_id: str
    total: int
    items: list[CartonCustomerOut]


class CartonOrderLineCreate(BaseModel):
    packaging_type: str = Field(min_length=1, max_length=64)
    paper_quality: str = Field(min_length=1, max_length=128)
    specification: str = Field(min_length=1, max_length=255)
    dimension_unit: str = Field(default="", max_length=16)
    usage_quantity: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=8,
        description="每箱个数；纸箱数量按产品订单数量除以每箱个数并向上取整",
    )
    unit: str = Field(min_length=1, max_length=32)
    unit_price: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=6)
    currency: str = Field(default="CNY", min_length=3, max_length=8)
    price_source: str = Field(default="manual", max_length=128)
    note: str = Field(default="", max_length=2000)

    @field_validator(
        "packaging_type",
        "paper_quality",
        "specification",
        "dimension_unit",
        "unit",
        "currency",
        "price_source",
        "note",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class CartonOrderCreate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    customer_code: str = Field(min_length=1, max_length=64)
    customer_name: str = Field(min_length=1, max_length=255)
    supplier_id: str | None = Field(default=None, max_length=96)
    contract_no: str = Field(min_length=1, max_length=128)
    item_no: str = Field(min_length=1, max_length=128)
    product_name: str = Field(default="", max_length=255)
    product_order_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    order_date: str
    customer_due_date: str | None = None
    due_date: str
    status: Literal["DRAFT", "PENDING_SUPPLIER", "CONFIRMED"] = "CONFIRMED"
    note: str = Field(default="", max_length=4000)
    lines: list[CartonOrderLineCreate] = Field(min_length=1, max_length=50)

    @field_validator(
        "factory_id",
        "customer_code",
        "customer_name",
        "contract_no",
        "item_no",
        "product_name",
        "note",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("contract_no")
    @classmethod
    def validate_contract_no(cls, value: str) -> str:
        return _validate_business_identifier(value, label="合同号")

    @field_validator("item_no")
    @classmethod
    def validate_item_no(cls, value: str) -> str:
        return _validate_business_identifier(value, label="货号")

    @field_validator("order_date", "due_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        return _validate_iso_date(value)

    @field_validator("customer_due_date")
    @classmethod
    def validate_optional_customer_due_date(cls, value: str | None) -> str | None:
        return _validate_iso_date(value) if value is not None else None

    @model_validator(mode="after")
    def validate_due_date(self):
        if self.customer_due_date is not None:
            self.due_date = derive_carton_plan_due_date(
                self.order_date,
                self.customer_due_date,
            )
        elif self.due_date < self.order_date:
            raise ValueError("计划交期不能早于下单日期")
        return self


class CartonOrderUpdate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)
    customer_code: str = Field(min_length=1, max_length=64)
    customer_name: str = Field(min_length=1, max_length=255)
    supplier_id: str | None = Field(default=None, max_length=96)
    contract_no: str = Field(min_length=1, max_length=128)
    item_no: str = Field(min_length=1, max_length=128)
    product_name: str = Field(default="", max_length=255)
    product_order_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    order_date: str
    customer_due_date: str | None = None
    due_date: str
    note: str = Field(default="", max_length=4000)
    lines: list[CartonOrderLineCreate] = Field(min_length=1, max_length=50)

    @field_validator(
        "factory_id",
        "reason",
        "customer_code",
        "customer_name",
        "contract_no",
        "item_no",
        "product_name",
        "note",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("contract_no")
    @classmethod
    def validate_contract_no(cls, value: str) -> str:
        return _validate_business_identifier(value, label="合同号")

    @field_validator("item_no")
    @classmethod
    def validate_item_no(cls, value: str) -> str:
        return _validate_business_identifier(value, label="货号")

    @field_validator("order_date", "due_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        return _validate_iso_date(value)

    @field_validator("customer_due_date")
    @classmethod
    def validate_optional_customer_due_date(cls, value: str | None) -> str | None:
        return _validate_iso_date(value) if value is not None else None

    @model_validator(mode="after")
    def validate_due_date(self):
        if self.customer_due_date is not None:
            self.due_date = derive_carton_plan_due_date(
                self.order_date,
                self.customer_due_date,
            )
        elif self.due_date < self.order_date:
            raise ValueError("计划交期不能早于下单日期")
        return self


class CartonOrderCancelRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("factory_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class CartonOrderSubmitRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)

    @field_validator("factory_id")
    @classmethod
    def strip_factory_id(cls, value: str) -> str:
        return _strip(value)


class CartonOrderAppendRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    additional_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    reason: str = Field(default="客人追加订单", min_length=4, max_length=500)
    customer_due_date: str | None = None
    due_date: str | None = None

    @field_validator("factory_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("reason", mode="before")
    @classmethod
    def default_reason(cls, value: object) -> str:
        return _strip(value) if isinstance(value, str) and value.strip() else "客人追加订单"

    @field_validator("customer_due_date", "due_date")
    @classmethod
    def validate_optional_date(cls, value: str | None) -> str | None:
        return _validate_iso_date(value) if value is not None else None


class CartonOrderReduceRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    reduction_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    reason: str = Field(default="客人退单", min_length=4, max_length=500)

    @field_validator("factory_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("reason", mode="before")
    @classmethod
    def default_reason(cls, value: object) -> str:
        return _strip(value) if isinstance(value, str) and value.strip() else "客人退单"


class CartonOrderActionItem(BaseModel):
    order_no: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)

    @field_validator("order_no")
    @classmethod
    def strip_order_no(cls, value: str) -> str:
        return _strip(value)


class CartonOrderBulkSubmitRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    items: list[CartonOrderActionItem] = Field(min_length=1, max_length=100)

    @field_validator("factory_id")
    @classmethod
    def strip_factory_id(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_unique_orders(self):
        order_nos = [item.order_no for item in self.items]
        if len(order_nos) != len(set(order_nos)):
            raise ValueError("批量操作不能重复选择同一张订单")
        return self


class CartonOrderBulkCancelRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=4, max_length=500)
    items: list[CartonOrderActionItem] = Field(min_length=1, max_length=100)

    @field_validator("factory_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_unique_orders(self):
        order_nos = [item.order_no for item in self.items]
        if len(order_nos) != len(set(order_nos)):
            raise ValueError("批量操作不能重复选择同一张订单")
        return self


class CartonOrderSelectionRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    order_nos: list[str] = Field(min_length=1, max_length=100)

    @field_validator("factory_id")
    @classmethod
    def strip_factory_id(cls, value: str) -> str:
        return _strip(value)

    @field_validator("order_nos")
    @classmethod
    def normalize_order_nos(cls, values: list[str]) -> list[str]:
        normalized = [_strip(value) for value in values]
        if any(not value for value in normalized):
            raise ValueError("订单编号不能为空")
        if len(normalized) != len(set(normalized)):
            raise ValueError("不能重复选择同一张订单")
        return normalized


class CartonOrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    line_no: int
    packaging_type: str
    paper_quality: str
    specification: str
    dimension_unit: str
    usage_quantity: Decimal
    required_quantity: Decimal
    received_quantity: Decimal
    remaining_quantity: Decimal
    unit: str
    unit_price: Decimal
    currency: str
    price_source: str
    note: str


class CartonOrderHistoryLineOut(BaseModel):
    line_no: int
    packaging_type: str
    paper_quality: str
    specification: str
    dimension_unit: str
    usage_quantity: Decimal
    unit: str
    unit_price: Decimal
    currency: str
    price_source: str
    note: str


class CartonOrderHistorySuggestionOut(BaseModel):
    item_no: str
    customer_code: str
    customer_name: str
    product_name: str
    latest_order_no: str
    latest_contract_no: str
    latest_order_date: str
    latest_product_order_quantity: Decimal
    order_count: int
    match_type: Literal["EXACT", "PREFIX", "CONTAINS", "SIMILAR"]
    match_score: int
    lines: list[CartonOrderHistoryLineOut]


class CartonOrderHistorySuggestionListOut(BaseModel):
    factory_id: str
    query: str
    total: int
    items: list[CartonOrderHistorySuggestionOut]


class CartonOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    order_no: str
    customer_code: str
    customer_name: str
    supplier_id: str
    supplier_name: str
    contract_no: str
    item_no: str
    product_name: str
    product_order_quantity: Decimal
    order_date: str
    customer_due_date: str | None
    safety_lead_days: int
    due_date: str
    status: CartonOrderStatus
    note: str
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str
    maximum_reducible_quantity: Decimal
    lines: list[CartonOrderLineOut]


class CartonOrderListOut(BaseModel):
    factory_id: str
    total: int
    limit: int
    offset: int
    items: list[CartonOrderOut]


CartonPurchaseOrderDocumentType = Literal[
    "LEGACY_BASELINE", "INITIAL", "APPEND", "REDUCE", "ADJUSTMENT"
]


class CartonPurchaseOrderIssueCreate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)

    @field_validator("factory_id")
    @classmethod
    def strip_factory_id(cls, value: str) -> str:
        return _strip(value)


class CartonPurchaseOrderIssueOut(BaseModel):
    id: str
    factory_id: str
    order_no: str
    document_no: str
    document_type: CartonPurchaseOrderDocumentType
    issue_sequence: int
    source_order_revision: int
    before_product_quantity: Decimal
    after_product_quantity: Decimal
    product_quantity_delta: Decimal
    generated_by: str
    generated_by_name: str
    generated_at: str


class CartonPurchaseOrderContextOut(BaseModel):
    factory_id: str
    order_no: str
    order_revision: int
    pending_type: Literal["NONE", "INITIAL", "APPEND", "REDUCE", "ADJUSTMENT"]
    pending_product_quantity: Decimal
    pending_line_count: int
    can_generate: bool
    latest_document_no: str
    historical_baseline: bool
    issues: list[CartonPurchaseOrderIssueOut] = Field(default_factory=list)


class CartonHistoryOrderImportOut(BaseModel):
    factory_id: str
    original_filename: str
    row_count: int
    group_count: int
    imported_count: int
    imported_line_count: int
    skipped_count: int
    imported_orders: list[str] = Field(default_factory=list)
    skipped_orders: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CartonReceiptLineCreate(BaseModel):
    source_type: CartonReceiptLineSourceType = "FORMAL_ORDER"
    order_line_id: str | None = Field(default=None, min_length=1, max_length=96)
    customer_code: str = Field(default="", max_length=64)
    contract_no: str = Field(default="", max_length=128)
    item_no: str = Field(default="", max_length=128)
    packaging_type: str = Field(default="", max_length=64)
    paper_quality: str = Field(default="", max_length=128)
    specification: str = Field(default="", max_length=255)
    unit: str = Field(default="个", min_length=1, max_length=32)
    currency: str = Field(default="CNY", min_length=1, max_length=8)
    delivered_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    received_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    damaged_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unusable_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    location: str = Field(default="", max_length=128)
    feedback_note: str = Field(default="", max_length=2000)

    @field_validator(
        "customer_code",
        "contract_no",
        "item_no",
        "packaging_type",
        "paper_quality",
        "specification",
        "unit",
        "currency",
        "location",
        "feedback_note",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("order_line_id")
    @classmethod
    def strip_order_line_id(cls, value: str | None) -> str | None:
        value = _strip(value or "")
        return value or None

    @model_validator(mode="after")
    def validate_effective_quantity(self):
        unusable = self.damaged_quantity + self.rejected_quantity + self.unusable_quantity
        if unusable > self.received_quantity:
            raise ValueError("破损、拒收和其他不可用数量之和不能大于实收数量")
        if self.received_quantity > self.delivered_quantity:
            raise ValueError("实收数量不能大于送货数量")
        if self.source_type == "FORMAL_ORDER":
            if not self.order_line_id:
                raise ValueError("正式订单收料必须关联订单明细")
            return self
        if self.order_line_id:
            raise ValueError("非正式收料不能伪造正式订单明细关联")
        missing = [
            label
            for label, value in (
                ("客户", self.customer_code),
                ("货号", self.item_no),
                ("纸品类型", self.packaging_type),
                ("纸质", self.paper_quality),
                ("规格", self.specification),
                ("单位", self.unit),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"非正式收料必须补齐：{'、'.join(missing)}")
        if self.received_quantity - unusable <= 0:
            raise ValueError("非正式收料的有效收料数量必须大于 0")
        return self


class CartonReceiptCreate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    delivery_note_no: str = Field(min_length=1, max_length=128)
    delivery_date: str
    supplier_id: str | None = Field(default=None, max_length=96)
    import_batch_id: str | None = Field(default=None, max_length=96)
    note: str = Field(default="", max_length=4000)
    lines: list[CartonReceiptLineCreate] = Field(min_length=1, max_length=200)

    @field_validator("factory_id", "delivery_note_no", "note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("delivery_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _validate_iso_date(value)


class CartonReceiptLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    line_no: int
    source_type: CartonReceiptLineSourceType
    order_line_id: str | None
    customer_code: str
    customer_name: str
    contract_no: str
    item_no: str
    packaging_type: str
    paper_quality: str
    specification: str
    delivered_quantity: Decimal
    received_quantity: Decimal
    damaged_quantity: Decimal
    rejected_quantity: Decimal
    unusable_quantity: Decimal
    effective_quantity: Decimal
    unit: str
    unit_price: Decimal
    currency: str
    location: str
    feedback_note: str


class CartonReceiptOut(BaseModel):
    id: str
    factory_id: str
    receipt_no: str
    delivery_note_no: str
    delivery_date: str
    supplier_id: str
    supplier_name: str
    import_batch_id: str | None
    status: CartonReceiptStatus
    note: str
    revision: int
    created_by: str
    created_by_name: str
    confirmed_by: str
    confirmed_by_name: str
    created_at: str
    updated_at: str
    confirmed_at: str
    lines: list[CartonReceiptLineOut]


class CartonReceiptListOut(BaseModel):
    factory_id: str
    total: int
    limit: int
    offset: int
    items: list[CartonReceiptOut]


class CartonReceiptConfirmRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)


class CartonInventoryRelocateRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    reference_movement_id: str = Field(min_length=1, max_length=96)
    expected_location_revision: int = Field(ge=0)
    location: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=2000)

    @field_validator("factory_id", "reference_movement_id", "location", "note", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class CartonInventoryMovementCreate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    order_line_id: str | None = Field(default=None, min_length=1, max_length=96)
    reference_movement_id: str | None = Field(default=None, min_length=1, max_length=96)
    movement_type: Literal["OUTBOUND", "ADJUSTMENT"]
    quantity: Decimal = Field(max_digits=18, decimal_places=4)
    location: str = Field(default="", max_length=128)
    document_no: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("factory_id", "location", "document_no", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("order_line_id", "reference_movement_id")
    @classmethod
    def strip_optional_id(cls, value: str | None) -> str | None:
        normalized = _strip(value or "")
        return normalized or None

    @model_validator(mode="after")
    def validate_quantity(self):
        if not self.order_line_id and not self.reference_movement_id:
            raise ValueError("必须选择一条库存结存记录")
        if self.movement_type == "OUTBOUND" and self.quantity <= 0:
            raise ValueError("出库数量必须大于 0")
        if self.movement_type == "ADJUSTMENT" and self.quantity == 0:
            raise ValueError("调整数量不能为 0")
        return self


class CartonInventoryBulkItem(BaseModel):
    order_line_id: str | None = Field(default=None, min_length=1, max_length=96)
    reference_movement_id: str | None = Field(default=None, min_length=1, max_length=96)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    location: str = Field(default="", max_length=128)

    @field_validator("order_line_id", "reference_movement_id")
    @classmethod
    def strip_optional_id(cls, value: str | None) -> str | None:
        normalized = _strip(value or "")
        return normalized or None

    @field_validator("location")
    @classmethod
    def strip_location(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_target(self):
        if bool(self.order_line_id) == bool(self.reference_movement_id):
            raise ValueError("每条批量出库记录必须且只能选择一个库存结存来源")
        return self


class CartonInventoryBulkCreate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    document_no: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="客户要货", min_length=1, max_length=2000)
    items: list[CartonInventoryBulkItem] = Field(min_length=1, max_length=100)

    @field_validator("factory_id", "document_no", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_unique_targets(self):
        targets = [item.order_line_id or item.reference_movement_id for item in self.items]
        if len(targets) != len(set(targets)):
            raise ValueError("批量出库不能重复选择同一条库存结存")
        return self


class CartonInventoryReversalRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("factory_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class CartonInventoryMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    order_line_id: str | None
    customer_code: str
    customer_name: str
    contract_no: str
    item_no: str
    packaging_type: str
    paper_quality: str
    specification: str
    movement_type: CartonMovementType
    quantity: Decimal
    balance: Decimal
    unit: str
    unit_price: Decimal
    currency: str
    location: str
    document_no: str
    source_type: str
    source_id: str
    source_line_id: str
    reversal_of_movement_id: str | None
    reason: str
    actor_user_id: str
    actor_name: str
    occurred_at: str


class CartonInventoryMovementListOut(BaseModel):
    factory_id: str
    total: int
    limit: int
    offset: int
    items: list[CartonInventoryMovementOut]


class CartonInventoryFlowSummaryOut(BaseModel):
    business_date: str
    customer_code: str
    customer_name: str
    movement_type: Literal["INBOUND", "OUTBOUND"]
    document_count: int
    line_count: int
    quantity: Decimal


class CartonHistoryInventoryImportOut(BaseModel):
    factory_id: str
    original_filename: str
    row_count: int
    imported_count: int
    skipped_count: int
    matched_order_line_count: int
    standalone_count: int
    total_quantity: Decimal
    duplicate: bool = False
    movement_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CartonInventoryBalanceOut(BaseModel):
    factory_id: str
    customer_code: str
    customer_name: str
    contract_no: str
    item_no: str
    order_line_id: str | None
    packaging_type: str
    paper_quality: str
    specification: str
    unit: str
    balance: Decimal
    latest_location: str
    latest_movement_id: str
    latest_document_no: str
    latest_movement_at: str
    latest_inbound_at: str | None = None
    location_revision: int = 0


class CartonClosingGenerateRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    customer_code: str | None = Field(default=None, max_length=64)

    @field_validator("factory_id")
    @classmethod
    def strip_factory(cls, value: str) -> str:
        return _strip(value)

    @field_validator("customer_code")
    @classmethod
    def strip_customer(cls, value: str | None) -> str | None:
        value = _strip(value or "")
        return value or None


class CartonClosingStatusRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    status: Literal["PENDING", "CONFIRMED", "LOCKED"]


class CartonClosingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    period: str
    customer_code: str
    customer_name: str
    opening_quantity: Decimal
    inbound_quantity: Decimal
    outbound_quantity: Decimal
    adjustment_quantity: Decimal
    ending_quantity: Decimal
    ending_amount: Decimal
    currency: str
    status: CartonClosingStatus
    revision: int
    generated_by: str
    generated_by_name: str
    generated_at: str
    confirmed_by: str
    confirmed_at: str
    locked_by: str
    locked_at: str


class CartonImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    import_type: Literal["DELIVERY_NOTE", "WEEKLY_SCHEDULE", "INSPECTION_SCHEDULE"]
    original_filename: str
    source_sha256: str
    import_profile: str
    content_type: str
    source_size_bytes: int
    status: Literal["REQUIRES_REVIEW", "CONFIRMED", "REJECTED"]
    imported_by: str
    imported_by_name: str
    created_at: str
    parse_summary: dict[str, object] = Field(default_factory=dict)
    duplicate: bool = False


class CartonImportBatchListOut(BaseModel):
    factory_id: str
    total: int
    limit: int
    offset: int
    items: list[CartonImportBatchOut]


class CartonExceptionUpdate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]
    owner_department: str = Field(default="", max_length=128)
    resolution_note: str = Field(default="", max_length=4000)

    @field_validator("factory_id", "owner_department", "resolution_note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_resolution(self):
        if self.status in {"RESOLVED", "CLOSED"} and len(self.resolution_note) < 4:
            raise ValueError("解决或关闭异常时必须填写至少 4 个字符的处理说明")
        return self


class CartonExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    exception_no: str
    source_type: str
    source_id: str
    category: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    customer_code: str
    customer_name: str
    contract_no: str
    item_no: str
    title: str
    description: str
    owner_department: str
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]
    resolution_note: str
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str
    resolved_by: str
    resolved_by_name: str
    resolved_at: str


class CartonExceptionListOut(BaseModel):
    factory_id: str
    total: int
    limit: int
    offset: int
    items: list[CartonExceptionOut]


class CartonAuditEventOut(BaseModel):
    sequence: int
    id: str
    factory_id: str
    event_type: str
    entity_type: str
    entity_id: str
    detail: dict[str, object]
    actor_user_id: str
    actor_name: str
    created_at: str


class CartonAuditEventListOut(BaseModel):
    factory_id: str
    total: int
    limit: int
    offset: int
    items: list[CartonAuditEventOut]


class CartonDashboardOut(BaseModel):
    factory_id: str
    open_order_count: int
    partial_order_count: int
    pending_receipt_count: int
    inventory_balance: Decimal
    unlocked_closing_count: int
    open_exception_count: int
