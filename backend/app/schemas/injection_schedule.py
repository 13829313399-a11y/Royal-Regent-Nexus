from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class InjectionScheduleFactorySettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factory_id: str
    factory_name: str
    timezone: str
    business_date: str
    current_shift: str
    day_shift_start: str
    day_shift_end: str
    night_shift_start: str
    night_shift_end: str
    warehouse_buffer_days: int
    fallback_water_ratio: Decimal
    auto_schedule_mode: str
    ai_enabled: bool
    template_family: str
    template_version: str
    schedule_revision: int
    schedule_horizon_days: int
    freeze_hours: int
    effective_hours_per_day: Decimal


class InjectionScheduleCapabilitiesOut(BaseModel):
    can_read: bool
    can_edit: bool
    can_schedule: bool
    can_admin: bool
    phase: str = "LOCAL_ACCEPTANCE"


class InjectionScheduleKpiOut(BaseModel):
    active_order_count: int
    scheduled_order_count: int
    unscheduled_order_count: int
    in_production_order_count: int
    overdue_order_count: int


class InjectionScheduleOrderOut(BaseModel):
    id: str
    factory_id: str
    order_no: str
    product_code: str
    product_name: str
    mold_code: str
    quantity_sets: Decimal
    total_sets: Decimal | None
    order_shots: Decimal
    qualified_shots: Decimal
    remaining_shots: Decimal
    completion_percent: Decimal
    priority: str
    status: str
    delivery_due_date: str
    warehouse: str
    color: str
    pigment_code: str
    material_name: str
    material_status: str
    required_machine_a_label: str
    required_machine_a_value: Decimal | None
    daily_target: Decimal | None
    material_weight_kg: Decimal | None
    data_completeness_status: str
    remark: str
    version: int


class InjectionScheduleMachineOut(BaseModel):
    id: str
    factory_id: str
    machine_code: str
    position: str
    machine_name: str
    machine_a_label: str
    machine_ounce_capacity: Decimal | None
    tonnage: Decimal | None
    is_automatic: bool
    is_high_speed: bool
    robot_arm_type: str
    supports_core_pull: bool
    status: str
    available_from: str
    raw_remark: str
    version: int


class InjectionScheduleMoldOut(BaseModel):
    id: str
    factory_id: str
    mold_code: str
    product_code: str
    product_name: str
    required_machine_a_label: str
    mold_ounce_requirement: Decimal | None
    min_machine_ounce: Decimal | None
    max_machine_ounce: Decimal | None
    cavity_count: int | None
    pieces_per_shot: int | None
    shot_weight_g: Decimal | None
    recommended_tonnage: Decimal | None
    required_robot_arm: str
    status: str
    daily_target: Decimal | None
    remark: str
    version: int


class InjectionScheduleLineOut(BaseModel):
    id: str
    factory_id: str
    order_demand_id: str
    machine_id: str | None
    machine_code: str
    mold_id: str | None
    mold_code: str
    order_no: str
    product_code: str
    product_name: str
    color: str
    material_name: str
    sequence_no: Decimal | None
    status: str
    is_locked: bool
    priority: str
    planned_start_at: str
    planned_finish_at: str
    qualified_shots: Decimal
    remaining_shots: Decimal
    completion_percent: Decimal
    effective_daily_target: Decimal | None
    warehouse_date: str
    delivery_gap_days: Decimal | None
    schedule_revision: int
    schedule_source: str
    version: int


class InjectionScheduleOrderListOut(BaseModel):
    factory_id: str
    total: int
    items: list[InjectionScheduleOrderOut]


class InjectionScheduleMachineListOut(BaseModel):
    factory_id: str
    total: int
    items: list[InjectionScheduleMachineOut]


class InjectionScheduleMoldListOut(BaseModel):
    factory_id: str
    total: int
    items: list[InjectionScheduleMoldOut]


class InjectionScheduleBoardOut(BaseModel):
    factory_id: str
    start_date: str
    end_date: str
    schedule_revision: int
    kpis: InjectionScheduleKpiOut
    lines: list[InjectionScheduleLineOut]


class InjectionScheduleBootstrapOut(BaseModel):
    factory_id: str
    settings: InjectionScheduleFactorySettingsOut
    capabilities: InjectionScheduleCapabilitiesOut
    supported_import_profiles: list[str]


class InjectionScheduleImportIssueOut(BaseModel):
    source_row: int | None
    field_name: str
    raw_value: str
    severity: str
    error_type: str
    message: str
    blocking: bool


class InjectionScheduleImportPreviewRowOut(BaseModel):
    factory_id: str
    source_sheet: str
    source_row: int
    demand_line_no: str
    business_key: str
    change_action: str = "CREATE"
    machine_code: str
    order_no: str
    product_code: str
    mold_code: str
    product_name: str
    quantity_sets: Decimal
    total_sets: Decimal | None
    order_shots: Decimal
    qualified_shots: Decimal
    priority: str
    order_date: str
    delivery_start_date: str
    delivery_due_date: str
    warehouse: str
    delivery_location: str
    ordered_by_name: str
    operator_name: str
    color: str
    pigment_code: str
    material_name: str
    water_ratio: Decimal | None
    net_weight_g: Decimal | None
    gross_weight_g: Decimal | None
    material_weight_kg: Decimal | None
    daily_target: Decimal | None
    required_machine_a_label: str
    required_machine_a_value: Decimal | None
    spray_required: bool
    data_completeness_status: str
    remark: str


class InjectionScheduleImportHistoryOutputOut(BaseModel):
    business_key: str
    source_row: int
    production_date: str
    shift: Literal["DAY", "NIGHT"]
    reported_shots: Decimal


class InjectionScheduleImportPreviewOut(BaseModel):
    batch_id: str
    factory_id: str
    status: str
    profile_code: str
    document_type: str
    source_file_name: str
    source_file_sha256: str
    source_size_bytes: int
    source_sheet: str
    header_row: int
    header: dict[str, str]
    column_mapping: dict[str, str]
    machines: list[dict[str, object]]
    rows: list[InjectionScheduleImportPreviewRowOut]
    history_outputs: list[InjectionScheduleImportHistoryOutputOut]
    issues: list[InjectionScheduleImportIssueOut]
    summary: dict[str, int]


class InjectionScheduleImportCommitRequest(BaseModel):
    factory_id: str
    request_id: str


class InjectionScheduleImportCommitOut(BaseModel):
    batch_id: str
    factory_id: str
    status: str
    created_count: int
    updated_count: int
    skipped_count: int
    history_created_count: int
    history_updated_count: int
    history_unchanged_count: int


class InjectionScheduleImportRejectRequest(BaseModel):
    factory_id: str
    reason: str = ""


class InjectionScheduleMoveRequest(BaseModel):
    factory_id: str
    target_machine_id: str
    planned_start_at: str
    planned_finish_at: str
    sequence_no: Decimal | None = None
    expected_line_version: int
    expected_schedule_revision: int
    validate_token: str = ""
    reason: str = ""


class InjectionScheduleLineActionRequest(BaseModel):
    factory_id: str
    expected_line_version: int
    expected_schedule_revision: int
    reason: str = ""


class InjectionScheduleShiftOutputRequest(BaseModel):
    factory_id: str
    reported_shots: Decimal
    defect_shots: Decimal = Decimal("0")
    downtime_minutes: int = 0
    downtime_reason: str = ""
    remark: str = ""
    version: int | None = None


class InjectionScheduleWindowCreateRequest(BaseModel):
    factory_id: str
    machine_id: str
    start_at: str
    end_at: str
    window_type: str
    reason: str = ""
    is_locked: bool = True


class InjectionScheduleWindowPatchRequest(BaseModel):
    factory_id: str
    version: int
    start_at: str
    end_at: str
    window_type: str
    reason: str = ""
    is_locked: bool = True


class InjectionScheduleVersionRequest(BaseModel):
    factory_id: str
    version: int
    reason: str = ""


class InjectionScheduleAutoPreviewRequest(BaseModel):
    factory_id: str
    request_id: str
    start_at: str
    end_at: str
    mode: str = "INCREMENTAL"
    selected_order_ids: list[str] = []
    affected_machine_ids: list[str] = []
    expected_schedule_revision: int


class InjectionScheduleProposalActionRequest(BaseModel):
    factory_id: str
    expected_schedule_revision: int
    reason: str = ""


class InjectionScheduleSavedViewCreateRequest(BaseModel):
    factory_id: str
    name: str
    scope: str = "PERSONAL"
    config: dict[str, object]
    is_default: bool = False


class InjectionScheduleSavedViewPatchRequest(BaseModel):
    factory_id: str
    version: int
    name: str
    config: dict[str, object]
    is_default: bool = False


class InjectionScheduleTableExportRequest(BaseModel):
    factory_id: str
    columns: list[str] = []
    search: str = ""
    status: str = ""
    priority: str = ""


class InjectionScheduleShiftMatrixExportRequest(BaseModel):
    factory_id: str
    start_date: str
    end_date: str


class InjectionScheduleAiRemarkRequest(BaseModel):
    factory_id: str
    remark: str


class InjectionScheduleAiFilterRequest(BaseModel):
    factory_id: str
    text: str


class InjectionScheduleAiExplainRequest(BaseModel):
    factory_id: str
    line_id: str


class InjectionScheduleAiAdjustmentRequest(BaseModel):
    factory_id: str
    text: str


class InjectionScheduleAiRemarkResult(BaseModel):
    spray_required: bool = False
    priority: str = "NORMAL"
    material_hint: str = ""
    structured_notes: list[str] = []


class InjectionScheduleAiFilterResult(BaseModel):
    search: str = ""
    status: str = ""
    priority: str = ""
    warnings: list[str] = []


class InjectionScheduleAiAdjustmentResult(BaseModel):
    action: str
    line_id: str = ""
    target_machine_id: str = ""
    reason: str
    requires_confirmation: bool = True


class InjectionScheduleAiExplainResult(BaseModel):
    summary: str
    reasons: list[str] = []
    risks: list[str] = []


class InjectionScheduleOrderPatchRequest(BaseModel):
    factory_id: str
    version: int
    priority: str | None = None
    delivery_due_date: str | None = None
    material_status: str | None = None
    required_machine_a_label: str | None = None
    required_machine_a_value: Decimal | None = None
    daily_target: Decimal | None = None
    remark: str | None = None
    reason: str = ""


class InjectionScheduleMachineCreateRequest(BaseModel):
    factory_id: str
    machine_code: str
    position: str = ""
    machine_name: str = ""
    machine_a_label: str
    machine_ounce_capacity: Decimal
    tonnage: Decimal | None = None
    is_automatic: bool = False
    is_high_speed: bool = False
    robot_arm_type: str = "UNKNOWN"
    supports_core_pull: bool = False
    status: str = "AVAILABLE"
    raw_remark: str = ""


class InjectionScheduleMachinePatchRequest(InjectionScheduleMachineCreateRequest):
    version: int
    reason: str = ""


class InjectionScheduleMoldCreateRequest(BaseModel):
    factory_id: str
    mold_code: str
    product_code: str
    product_name: str = ""
    required_machine_a_label: str
    mold_ounce_requirement: Decimal
    min_machine_ounce: Decimal | None = None
    max_machine_ounce: Decimal | None = None
    cavity_count: int | None = None
    pieces_per_shot: int | None = None
    shot_weight_g: Decimal | None = None
    recommended_tonnage: Decimal | None = None
    required_robot_arm: str = "UNKNOWN"
    daily_target: Decimal | None = None
    status: str = "ACTIVE"
    remark: str = ""


class InjectionScheduleMoldPatchRequest(InjectionScheduleMoldCreateRequest):
    version: int
    reason: str = ""
