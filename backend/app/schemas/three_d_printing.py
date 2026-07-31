from typing import Any, Literal

from pydantic import BaseModel, Field


class ThreeDSettingsUpdate(BaseModel):
    factory_id: str
    revision: int = Field(ge=1)
    machine_count: int = Field(ge=1, le=100)
    electricity_per_machine_day: float = Field(ge=0)
    labor_per_day: float = Field(ge=0)
    material_loss_rate: float = Field(gt=0, le=10)
    profit_rate_percent: float = Field(ge=0, le=1000)


class ThreeDSettingsOut(BaseModel):
    factory_id: str
    machine_count: int
    electricity_per_machine_day: float
    labor_per_day: float
    material_loss_rate: float
    profit_rate_percent: float
    revision: int
    updated_at: str


class ThreeDMaterialInput(BaseModel):
    factory_id: str
    name: str = Field(min_length=1, max_length=255)
    material_type: str = Field(default="", max_length=64)
    price_per_kg: float = Field(ge=0)


class ThreeDMaterialUpdate(ThreeDMaterialInput):
    revision: int = Field(ge=1)


class ThreeDMaterialOut(BaseModel):
    id: str
    factory_id: str
    legacy_id: str = ""
    name: str
    material_type: str
    price_per_kg: float
    is_active: bool
    revision: int
    created_at: str
    updated_at: str


class ThreeDProductInput(BaseModel):
    factory_id: str
    name: str = Field(min_length=1, max_length=255)
    customer: str = Field(default="", max_length=255)
    material_name: str = Field(default="", max_length=255)
    weight_g: float = Field(default=0, ge=0)
    duration_hours: float = Field(default=0, ge=0)
    default_quantity: int = Field(default=1, ge=1)
    quoted_price: float = Field(default=0, ge=0)


class ThreeDProductUpdate(ThreeDProductInput):
    revision: int = Field(ge=1)


class ThreeDProductOut(BaseModel):
    id: str
    factory_id: str
    legacy_id: str = ""
    name: str
    customer: str
    material_name: str
    weight_g: float
    duration_hours: float
    default_quantity: int
    quoted_price: float
    image_url: str = ""
    image_size_bytes: int = 0
    image_sha256: str = ""
    is_active: bool
    revision: int
    created_at: str
    updated_at: str


class ThreeDProductionRecordInput(BaseModel):
    factory_id: str
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    machine_no: int = Field(ge=1, le=100)
    status: Literal["running", "idle", "fault"]
    product_id: str = ""
    product_name: str = Field(default="", max_length=255)
    material_name: str = Field(default="", max_length=255)
    weight_g: float = Field(default=0, ge=0)
    quantity: int = Field(default=1, ge=0)
    duration_hours: float = Field(default=0, ge=0)
    design_fee: float = Field(default=0, ge=0)
    quoted_price: float = Field(default=0, ge=0)
    customer: str = Field(default="", max_length=255)
    remark: str = Field(default="", max_length=4000)


class ThreeDProductionRecordUpdate(ThreeDProductionRecordInput):
    revision: int = Field(ge=1)


class ThreeDProductionRecordOut(BaseModel):
    id: str
    factory_id: str
    legacy_id: str = ""
    business_date: str
    machine_no: int
    status: str
    product_id: str
    product_name: str
    material_name: str
    weight_g: float
    quantity: int
    duration_hours: float
    design_fee: float
    quoted_price: float
    customer: str
    remark: str
    auto_record: bool
    print_start_at: str
    print_end_at: str
    gcode_file: str
    revision: int
    created_at: str
    updated_at: str


class ThreeDDayStatusUpdate(BaseModel):
    factory_id: str
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_day_off: bool


class ThreeDInventoryOut(BaseModel):
    id: str
    factory_id: str
    material_name: str
    stock_g: float
    min_stock_g: float
    is_low: bool
    revision: int
    updated_at: str


class ThreeDInventoryAdjustment(BaseModel):
    factory_id: str
    material_name: str = Field(min_length=1, max_length=255)
    target_stock_g: float = Field(ge=0)
    min_stock_g: float | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class ThreeDStockInInput(BaseModel):
    factory_id: str
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    material_name: str = Field(min_length=1, max_length=255)
    amount_g: float = Field(gt=0)
    vendor: str = Field(default="", max_length=255)
    cost: float = Field(default=0, ge=0)
    remark: str = Field(default="", max_length=1000)


class ThreeDInventoryMovementOut(BaseModel):
    id: str
    factory_id: str
    material_name: str
    movement_type: str
    delta_g: float
    balance_after_g: float
    business_date: str
    vendor: str
    cost: float
    remark: str
    source_record_id: str
    created_at: str


class ThreeDScheduleInput(BaseModel):
    factory_id: str
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    product_id: str = ""
    product_name: str = Field(min_length=1, max_length=255)
    customer: str = Field(default="", max_length=255)
    material_name: str = Field(min_length=1, max_length=255)
    weight_g: float = Field(gt=0)
    quantity: int = Field(default=1, ge=1)
    machine_no: int = Field(default=0, ge=0, le=100)
    priority: Literal["high", "normal", "low"] = "normal"
    status: Literal["pending", "printing", "done", "cancelled"] = "pending"
    remark: str = Field(default="", max_length=2000)


class ThreeDScheduleUpdate(ThreeDScheduleInput):
    revision: int = Field(ge=1)


class ThreeDScheduleStatusUpdate(BaseModel):
    factory_id: str
    revision: int = Field(ge=1)
    status: Literal["pending", "printing", "done", "cancelled"]


class ThreeDScheduleOut(BaseModel):
    id: str
    factory_id: str
    legacy_id: str = ""
    business_date: str
    product_id: str
    product_name: str
    customer: str
    material_name: str
    weight_g: float
    quantity: int
    machine_no: int
    priority: str
    status: str
    remark: str
    revision: int
    created_at: str
    updated_at: str


class ThreeDMaintenanceInput(BaseModel):
    factory_id: str
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    machine_no: int = Field(default=0, ge=0, le=100)
    maintenance_type: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=4000)
    cost: float = Field(default=0, ge=0)
    vendor: str = Field(default="", max_length=255)
    remark: str = Field(default="", max_length=2000)


class ThreeDMaintenanceUpdate(ThreeDMaintenanceInput):
    revision: int = Field(ge=1)


class ThreeDMaintenanceOut(BaseModel):
    id: str
    factory_id: str
    legacy_id: str = ""
    business_date: str
    machine_no: int
    maintenance_type: str
    description: str
    cost: float
    vendor: str
    remark: str
    revision: int
    created_at: str
    updated_at: str


class ThreeDPrinterOut(BaseModel):
    id: str
    factory_id: str
    machine_no: int
    name: str
    printer_type: str
    model: str
    enabled: bool
    connected: bool
    state: str
    current_file: str
    progress_percent: int
    remaining_minutes: int
    live_material: str
    nozzle_temperature: float
    bed_temperature: float
    error_text: str
    last_seen_at: str
    status_stale: bool


class ThreeDPrinterCommandCreate(BaseModel):
    factory_id: str
    action: Literal["pause", "resume"]
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ThreeDPrinterCommandOut(BaseModel):
    id: str
    factory_id: str
    printer_id: str
    action: str
    status: str
    reason: str
    requested_by_name: str
    requested_at: str
    expires_at: str
    claimed_at: str
    completed_at: str
    result_message: str


class ThreeDEdgeHeartbeat(BaseModel):
    factory_id: str
    agent_key: str = Field(min_length=1, max_length=96)
    name: str = Field(default="华康A 3D边缘代理", max_length=128)
    version: str = Field(default="", max_length=64)
    host_fingerprint: str = Field(default="", max_length=128)
    capabilities: list[str] = Field(default_factory=list)


class ThreeDEdgePrinterStatus(BaseModel):
    machine_no: int = Field(ge=1, le=100)
    name: str = Field(default="", max_length=128)
    printer_type: str = Field(default="bambu", max_length=64)
    model: str = Field(default="", max_length=128)
    connected: bool
    state: str = Field(default="UNKNOWN", max_length=32)
    current_file: str = Field(default="", max_length=512)
    progress_percent: int = Field(default=0, ge=0, le=100)
    remaining_minutes: int = Field(default=0, ge=0)
    live_material: str = Field(default="", max_length=255)
    nozzle_temperature: float = 0
    bed_temperature: float = 0
    error_text: str = Field(default="", max_length=4000)
    observed_at: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class ThreeDEdgeStatusBatch(BaseModel):
    factory_id: str
    agent_key: str = Field(min_length=1, max_length=96)
    statuses: list[ThreeDEdgePrinterStatus] = Field(max_length=100)


class ThreeDEdgeCommandClaim(BaseModel):
    factory_id: str
    agent_key: str = Field(min_length=1, max_length=96)
    limit: int = Field(default=10, ge=1, le=50)


class ThreeDEdgeCommandAck(BaseModel):
    factory_id: str
    agent_key: str = Field(min_length=1, max_length=96)
    status: Literal["succeeded", "failed"]
    message: str = Field(default="", max_length=4000)


class ThreeDAuditEventOut(BaseModel):
    id: str
    factory_id: str
    entity_type: str
    entity_id: str
    action: str
    detail: dict[str, Any]
    actor_name: str
    actor_type: str
    request_id: str
    created_at: str


class ThreeDDashboardOut(BaseModel):
    factory_id: str
    generated_at: str
    settings: ThreeDSettingsOut
    printers: list[ThreeDPrinterOut]
    materials: list[ThreeDMaterialOut]
    products: list[ThreeDProductOut]
    records: list[ThreeDProductionRecordOut]
    inventory: list[ThreeDInventoryOut]
    inventory_movements: list[ThreeDInventoryMovementOut]
    schedules: list[ThreeDScheduleOut]
    maintenance: list[ThreeDMaintenanceOut]
    day_off_dates: list[str]
    summary: dict[str, Any]
