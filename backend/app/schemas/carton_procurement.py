from datetime import date
from decimal import Decimal
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
CartonMovementType = Literal["INBOUND", "OUTBOUND", "ADJUSTMENT", "REVERSAL"]
CartonClosingStatus = Literal["DRAFT", "PENDING", "CONFIRMED", "LOCKED"]
CartonCustomerStatus = Literal["ACTIVE", "INACTIVE"]


def _strip(value: str) -> str:
    return value.strip()


def _validate_iso_date(value: str) -> str:
    value = value.strip()
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc
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

    @field_validator("order_date", "due_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        return _validate_iso_date(value)

    @model_validator(mode="after")
    def validate_due_date(self):
        if self.due_date < self.order_date:
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

    @field_validator("order_date", "due_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        return _validate_iso_date(value)

    @model_validator(mode="after")
    def validate_due_date(self):
        if self.due_date < self.order_date:
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
    lines: list[CartonOrderLineOut]


class CartonOrderListOut(BaseModel):
    factory_id: str
    total: int
    limit: int
    offset: int
    items: list[CartonOrderOut]


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
    order_line_id: str = Field(min_length=1, max_length=96)
    delivered_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    received_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    damaged_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unusable_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    location: str = Field(default="", max_length=128)
    feedback_note: str = Field(default="", max_length=2000)

    @field_validator("order_line_id", "location", "feedback_note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_effective_quantity(self):
        unusable = self.damaged_quantity + self.rejected_quantity + self.unusable_quantity
        if unusable > self.received_quantity:
            raise ValueError("破损、拒收和其他不可用数量之和不能大于实收数量")
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
    order_line_id: str
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
    latest_movement_at: str


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


class CartonDashboardOut(BaseModel):
    factory_id: str
    open_order_count: int
    partial_order_count: int
    pending_receipt_count: int
    inventory_balance: Decimal
    unlocked_closing_count: int
    open_exception_count: int
