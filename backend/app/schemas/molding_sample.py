from typing import Literal

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MoldingSampleOrderIn(BaseModel):
    id: str
    factory_id: str = "huakang-a"
    production_factory_id: str | None = None
    production_assigned_at: str = ""
    production_assigned_by: str = ""
    production_assignment_version: int = 0
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


class MoldingSampleCreateOrderIn(MoldingSampleOrderIn):
    id: str = ""


class MoldingSampleOrderOut(MoldingSampleOrderIn):
    status: str = "待审核"

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleMaterialComponent(BaseModel):
    material: str = Field(min_length=1, max_length=255)
    ratio_percent: float = Field(gt=0, allow_inf_nan=False)
    source_type: Literal["virgin", "runner"]

    @field_validator("material")
    @classmethod
    def strip_material(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("原料成分名称不能为空")
        return value


class MoldingSampleMaterialCostComponent(BaseModel):
    material: str
    source_type: Literal["virgin", "runner"]
    ratio_percent: float
    weight_kg: float
    unit_price: float
    amount_hkd: float


class MoldingSampleItemIn(BaseModel):
    id: str
    order_id: str | None = None
    sort_order: int = 1
    mold_id: str = ""
    mold_name: str = ""
    mold_dimensions: str = ""
    mold_presence_status: Literal["unknown", "in_factory", "out_of_factory"] = "unknown"
    machine_type: str = ""
    production_machine: str = ""
    material: str = ""
    material_components: list[MoldingSampleMaterialComponent] = Field(default_factory=list)
    material_usage_type: Literal["production", "trial"] = "production"
    actual_material_cost_components: list[MoldingSampleMaterialCostComponent] = Field(default_factory=list)
    color: str = ""
    pigment_no: str = ""
    quantity: str = ""
    shoot_qty: int = 0
    quote_target_daily_qty: int | None = Field(default=None, gt=0, le=2147483647)
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

    @model_validator(mode="after")
    def validate_material_components(self):
        if not self.material_components:
            return self

        seen: set[tuple[str, str]] = set()
        total = Decimal("0")
        for component in self.material_components:
            key = (component.material.casefold(), component.source_type)
            if key in seen:
                raise ValueError("原料成分不可重复")
            seen.add(key)
            total += Decimal(str(component.ratio_percent))

        if abs(total - Decimal("100")) > Decimal("0.01"):
            raise ValueError("原料成分比例合计必须为 100%")
        return self


class MoldingSampleCreateItemIn(MoldingSampleItemIn):
    id: str = ""


class MoldingSampleItemOut(MoldingSampleItemIn):
    order_id: str

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleAuditLogOut(BaseModel):
    id: str
    order_id: str
    action: str
    actor_user_id: str = ""
    actor_name: str
    actor_role: str
    actor_roles: str = ""
    factory_scope: str = ""
    from_status: str
    to_status: str
    reason: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleDispatchLogOut(BaseModel):
    id: str
    order_id: str
    origin_factory_id: str
    from_production_factory_id: str | None = None
    to_production_factory_id: str
    action: str
    reason: str
    actor_user_id: str
    actor_name: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleNotificationOut(BaseModel):
    id: str
    order_id: str
    factory_id: str
    target_module: str
    target_role: str
    event_type: str
    title: str
    message: str
    from_status: str
    to_status: str
    status: str
    actor_name: str
    read_at: str
    handled_at: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleNotificationUpdateRequest(BaseModel):
    status: str


class MoldingSampleProblemOut(BaseModel):
    id: str
    factory_id: str
    order_type: str
    order_id: str
    order_number: str
    description: str
    reported_by: str
    status: str
    created_at: str
    resolved_at: str

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleProblemCreateRequest(BaseModel):
    order_id: str
    description: str
    reported_by: str = ""


class MoldingSampleProblemStatusRequest(BaseModel):
    status: str


class MoldingSampleTrialReportData(BaseModel):
    """Fields reproduced from the factory's paper trial-mold acceptance receipt."""

    mold_supplier: str = ""
    sample_category: str = ""
    material_name: str = ""
    material_shots: str = ""
    material_weight: str = ""
    color: str = ""
    color_code: str = ""
    color_shots: str = ""
    color_weight: str = ""
    virgin_material_shots: str = ""
    virgin_material_weight: str = ""
    runner_material_shots: str = ""
    runner_material_weight: str = ""
    water_ratio: str = ""
    water_shots: str = ""
    water_material_weight: str = ""
    water_weight: str = ""
    special_requirements: str = ""
    front_mold_water: str = ""
    rear_mold_water: str = ""
    other_trial_requirement: str = ""
    other_trial_requirement_note: str = ""
    baking_time_hours: str = ""
    mold_condition: str = ""
    expected_return_time: str = ""
    gross_weight: str = ""
    net_weight: str = ""
    plastic_model: str = ""
    machine_model: str = ""
    machine_no: str = ""
    cooling_time: str = ""
    holding_time: str = ""
    cycle_time: str = ""
    injection_speed: str = ""
    ejector_count: str = ""
    cushion_pressure: str = ""
    clamping_force: str = ""
    high_pressure: str = ""
    low_pressure: str = ""
    pressure_stage_1: str = ""
    pressure_stage_2: str = ""
    pressure_stage_3: str = ""
    pressure_stage_4: str = ""
    barrel_temperature_head: str = ""
    barrel_temperature_middle: str = ""
    barrel_temperature_end: str = ""
    molding_mode: str = ""
    mold_issues: list[str] = Field(default_factory=list)
    part_issues: list[str] = Field(default_factory=list)
    issue_notes: str = ""
    trial_summary: str = ""
    trial_round: str = ""
    verdict: str = ""
    tester_name: str = ""
    tester_date: str = ""
    molding_supervisor_name: str = ""
    molding_supervisor_date: str = ""
    engineer_name: str = ""
    engineer_date: str = ""


class MoldingSampleTrialReportUpsertRequest(BaseModel):
    data: MoldingSampleTrialReportData


class MoldingSampleTrialReportOut(BaseModel):
    id: str
    factory_id: str
    order_id: str
    item_id: str
    data: MoldingSampleTrialReportData
    created_by: str
    created_at: str
    updated_by: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class MoldingSampleCreateRequest(BaseModel):
    order: MoldingSampleCreateOrderIn
    items: list[MoldingSampleCreateItemIn] = Field(default_factory=list)


class MoldingSampleEditRequest(BaseModel):
    order: MoldingSampleOrderIn
    items: list[MoldingSampleItemIn] = Field(default_factory=list)


class MoldingSampleDetailResponse(BaseModel):
    order: MoldingSampleOrderOut
    items: list[MoldingSampleItemOut]
    audit_logs: list[MoldingSampleAuditLogOut] = Field(default_factory=list)
    dispatch_logs: list[MoldingSampleDispatchLogOut] = Field(default_factory=list)
    notifications: list[MoldingSampleNotificationOut] = Field(default_factory=list)
    problems: list[MoldingSampleProblemOut] = Field(default_factory=list)
    trial_reports: list[MoldingSampleTrialReportOut] = Field(default_factory=list)
    read_source: Literal["local", "cross", "cross_operate"] = "local"
    can_view_cost: bool = True


MoldingSampleBoardStatus = Literal[
    "待审核",
    "待生产",
    "生产中",
    "已完成",
    "已驳回",
    "已撤回",
]


class MoldingSampleBoardPageResponse(BaseModel):
    rows: list[MoldingSampleDetailResponse]
    total: int
    page: int
    page_size: int
    page_count: int


class MoldingSampleBoardSummaryResponse(BaseModel):
    total: int
    status_counts: dict[MoldingSampleBoardStatus, int]
    review_count: int
    production_count: int
    completed_count: int
    rejected_count: int
    withdrawn_count: int
    unresolved_problem_count: int
    production_data_pending_count: int


class MoldingSampleStatusRequest(BaseModel):
    action: str
    reason: str = ""
    today: str | None = None


class MoldingSampleProductionAssignmentRequest(BaseModel):
    production_factory_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)
    expected_assignment_version: int = Field(ge=0)


class MoldingSampleFactoryCapabilityOut(BaseModel):
    factory_id: str
    has_molding_department: bool
    allowed_production_factory_ids: list[str]
    suggested_production_factory_id: str


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


class RequisitionCreateRequest(BaseModel):
    date: str
    order_id: str
    material: str
    requested_weight_kg: float
    applicant: str = ""
    notes: str = ""


class RequisitionStatusRequest(BaseModel):
    status: str
    issued_at: str = ""
    inventory_batch_id: str = ""


class RequisitionOut(BaseModel):
    id: str
    factory_id: str
    req_number: str
    date: str
    order_id: str
    order_number: str
    material: str
    requested_weight_kg: float
    applicant: str
    notes: str
    inventory_batch_id: str
    inventory_batch_no: str
    status: str
    issued_at: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class InventoryBatchCreateRequest(BaseModel):
    factory_id: str = ""
    material: str
    batch_no: str
    location: str = ""
    initial_weight_kg: float


class InventoryBatchOut(BaseModel):
    id: str
    factory_id: str
    material: str
    batch_no: str
    location: str
    initial_weight_kg: float
    available_weight_kg: float
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class InventoryMovementOut(BaseModel):
    id: int
    factory_id: str
    batch_id: str
    batch_no: str
    requisition_id: str
    req_number: str
    material: str
    movement_type: str
    quantity_kg: float
    before_weight_kg: float
    after_weight_kg: float
    actor_name: str
    reason: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class SensitiveAuditLogOut(BaseModel):
    id: int
    action: str
    actor_user_id: str = ""
    actor_name: str
    actor_role: str
    actor_roles: str = ""
    factory_scope: str = ""
    target_type: str
    target_name: str
    detail: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)
