from pydantic import BaseModel, ConfigDict, Field


class MoldingSampleOrderIn(BaseModel):
    id: str
    factory_id: str = "huakang-a"
    order_number: str = ""
    doc_number: str = ""
    product_name: str
    client_name: str = ""
    date: str
    stage: str = ""
    order_type: str = "啤办"
    workshop: str = "A车间"
    send_to: str = ""
    supervisor: str = ""
    eng_name: str = ""
    reason: str = ""
    status: str | None = None
    reject_reason: str = ""
    completed_date: str = ""
    created_at: str = ""
    updated_at: str = ""


class MoldingSampleOrderOut(MoldingSampleOrderIn):
    status: str = "待审核"

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleItemIn(BaseModel):
    id: str
    order_id: str | None = None
    sort_order: int = 1
    mold_id: str = ""
    mold_name: str = ""
    machine_type: str = ""
    material: str = ""
    color: str = ""
    pigment_no: str = ""
    quantity: str = ""
    shoot_qty: int = 0
    gross_weight_g: float | None = None
    required_material_kg: float | None = None
    mold_return_time: str = ""
    completion_time: str = ""
    notes: str = ""
    receipt_no: str = ""
    collected_weight_kg: float | None = None
    actual_weight_kg: float | None = None
    actual_amount_hkd: float | None = None
    injection_cost: float | None = None
    injection_cost_hkd: float | None = None
    exchange_rate_at_save: float | None = None


class MoldingSampleItemOut(MoldingSampleItemIn):
    order_id: str

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleAuditLogOut(BaseModel):
    id: str
    order_id: str
    action: str
    actor_name: str
    actor_role: str
    from_status: str
    to_status: str
    reason: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleCreateRequest(BaseModel):
    order: MoldingSampleOrderIn
    items: list[MoldingSampleItemIn] = Field(default_factory=list)


class MoldingSampleEditRequest(MoldingSampleCreateRequest):
    actor_name: str
    actor_role: str
    pin: str = ""


class MoldingSampleDetailResponse(BaseModel):
    order: MoldingSampleOrderOut
    items: list[MoldingSampleItemOut]
    audit_logs: list[MoldingSampleAuditLogOut] = Field(default_factory=list)


class MoldingSampleStatusRequest(BaseModel):
    action: str
    reviewer_name: str
    reviewer_role: str
    pin: str = ""
    reason: str = ""
    today: str | None = None


class MoldingSampleItemsPatchRequest(BaseModel):
    items: list[MoldingSampleItemIn]


class MaterialPriceIn(BaseModel):
    material: str
    unit_price: float
    notes: str = ""


class MaterialPriceOut(MaterialPriceIn):
    model_config = ConfigDict(from_attributes=True)


class MaterialPricesResponse(BaseModel):
    prices: list[MaterialPriceOut]
    rmb_to_hkd_rate: float


class MaterialPricesUpdateRequest(BaseModel):
    prices: list[MaterialPriceIn]
    rmb_to_hkd_rate: float
    manager_name: str = ""
    manager_pin: str = ""


class TotalCostSummary(BaseModel):
    order_id: str
    order_number: str
    doc_number: str
    product_name: str
    client_name: str
    completed_date: str
    workshop: str
    send_to: str
    status: str
    total_material_cost: float
    total_injection_cost: float
    total_cost: float
    has_missing_price: bool
    has_missing_injection_cost: bool
    item_rows: list[dict]


class PinVerifyRequest(BaseModel):
    name: str
    role: str
    pin: str


class PinChangeRequest(BaseModel):
    name: str
    role: str
    old_pin: str
    new_pin: str


class PinVerifyResponse(BaseModel):
    valid: bool
    name: str
    role: str
    must_change: bool


class RoleEntry(BaseModel):
    name: str
    role: str
    must_change: bool


class RolesResponse(BaseModel):
    supervisors: list[RoleEntry]
    managers: list[RoleEntry]
