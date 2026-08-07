from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PlanStatus = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
TaskStatus = Literal["QUEUED", "RUNNING", "BLOCKED", "COMPLETED", "CANCELLED"]
DraftTaskStatus = Literal["QUEUED", "BLOCKED"]
PriorityCode = Literal["NORMAL", "URGENT", "CRITICAL"]
MaterialReadinessStatus = Literal["unknown", "ready", "partial", "blocked"]
OrderStatus = Literal["BACKLOG", "SCHEDULED", "COMPLETED", "CANCELLED"]
ShiftCode = Literal["DAY", "NIGHT"]
QuantityMode = Literal["INCREMENTAL", "CUMULATIVE"]
FitDecision = Literal["PASS", "REVIEW_REQUIRED", "FAIL"]


class StrictWriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InjectionSchedulingOrderCreate(StrictWriteModel):
    factory_id: str
    expected_revision: Literal[0] = 0
    order_no: str = Field(min_length=1, max_length=128)
    item_no: str = Field(default="", max_length=128)
    product_name: str = Field(default="", max_length=255)
    mold_id: str | None = Field(default=None, max_length=96)
    order_quantity: float = Field(gt=0)
    source_completed_quantity: float = Field(default=0, ge=0)
    delivery_start_date: date | None = None
    delivery_due_date: date | None = None
    priority_code: PriorityCode = "NORMAL"
    material_readiness_status: MaterialReadinessStatus = "unknown"
    warehouse_text: str = Field(default="", max_length=255)
    remark: str = Field(default="", max_length=2000)
    source_ref: str = Field(default="", max_length=255)
    source_version: str = Field(default="", max_length=128)
    lineage: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "order_no",
        "item_no",
        "product_name",
        "warehouse_text",
        "remark",
        "source_ref",
        "source_version",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("mold_id")
    @classmethod
    def normalize_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_completed_quantity(self):
        if self.source_completed_quantity > self.order_quantity:
            raise ValueError("来源已完成数不能大于订单数量")
        if (
            self.delivery_start_date is not None
            and self.delivery_due_date is not None
            and self.delivery_start_date > self.delivery_due_date
        ):
            raise ValueError("开始交货期不能晚于交货完成期")
        return self


class InjectionSchedulingOrderUpdate(StrictWriteModel):
    factory_id: str
    expected_revision: int = Field(ge=1)
    warehouse_text: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=2000)

    @field_validator("warehouse_text", "remark")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_change(self):
        if self.warehouse_text is None and self.remark is None:
            raise ValueError("至少提交一个可编辑字段")
        return self


class InjectionSchedulingOrderOut(BaseModel):
    id: str
    factory_id: str
    order_no: str
    item_no: str
    product_name: str
    mold_id: str | None
    order_quantity: float
    source_completed_quantity: float
    completed_quantity: float
    outstanding_quantity: float
    completion_rate: float
    estimated_completion_at: str
    estimated_remaining_shifts: int
    delivery_slack_days: int | None
    delivery_start_date: str
    delivery_due_date: str
    priority_code: PriorityCode
    material_readiness_status: MaterialReadinessStatus
    warehouse_text: str
    remark: str
    source_type: str
    source_ref: str
    source_version: str
    lineage: dict[str, Any]
    status: OrderStatus
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class InjectionSchedulingBacklogOut(BaseModel):
    factory_id: str
    items: list[InjectionSchedulingOrderOut]


class InjectionSchedulingDraftCreate(StrictWriteModel):
    factory_id: str
    expected_revision: Literal[0] = 0
    business_date: date


class InjectionSchedulingTaskCreate(StrictWriteModel):
    factory_id: str
    expected_revision: int = Field(ge=1)
    machine_id: str = Field(min_length=1, max_length=96)
    order_id: str = Field(min_length=1, max_length=96)
    mold_id: str | None = Field(default=None, max_length=96)
    mold_copy_no: int = Field(default=1, ge=1, le=100)
    sequence_no: int = Field(default=0, ge=0)
    execution_status: DraftTaskStatus = "QUEUED"
    planned_start: str = Field(min_length=1, max_length=32)
    planned_finish: str = Field(min_length=1, max_length=32)
    shift_target_quantity: float = Field(default=0, ge=0)
    locked: bool = False
    manual_override_reason: str = Field(default="", max_length=2000)

    @field_validator("mold_id")
    @classmethod
    def normalize_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_window_and_override(self):
        start = _parse_datetime(self.planned_start, "计划开始时间")
        finish = _parse_datetime(self.planned_finish, "计划完成时间")
        if start >= finish:
            raise ValueError("计划开始时间必须早于计划完成时间")
        if self.locked and not self.manual_override_reason.strip():
            raise ValueError("锁定任务必须填写人工覆盖原因")
        self.manual_override_reason = self.manual_override_reason.strip()
        return self


class InjectionSchedulingTaskUpdate(StrictWriteModel):
    factory_id: str
    expected_revision: int = Field(ge=1)
    expected_plan_revision: int = Field(ge=1)
    machine_id: str | None = Field(default=None, min_length=1, max_length=96)
    order_id: str | None = Field(default=None, min_length=1, max_length=96)
    mold_id: str | None = Field(default=None, max_length=96)
    mold_copy_no: int | None = Field(default=None, ge=1, le=100)
    sequence_no: int | None = Field(default=None, ge=0)
    execution_status: DraftTaskStatus | None = None
    planned_start: str | None = Field(default=None, min_length=1, max_length=32)
    planned_finish: str | None = Field(default=None, min_length=1, max_length=32)
    shift_target_quantity: float | None = Field(default=None, ge=0)
    locked: bool | None = None
    manual_override_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_optional_window(self):
        if self.planned_start is not None:
            _parse_datetime(self.planned_start, "计划开始时间")
        if self.planned_finish is not None:
            _parse_datetime(self.planned_finish, "计划完成时间")
        if self.manual_override_reason is not None:
            self.manual_override_reason = self.manual_override_reason.strip()
        return self


class InjectionSchedulingTaskMove(StrictWriteModel):
    task_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=1)
    machine_id: str = Field(min_length=1, max_length=96)
    sequence_no: int = Field(ge=0)
    planned_start: str = Field(min_length=1, max_length=32)
    planned_finish: str = Field(min_length=1, max_length=32)
    override_reason: str = Field(default="", max_length=2000)

    @field_validator("task_id", "machine_id", "override_reason")
    @classmethod
    def strip_move_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_window(self):
        start = _parse_datetime(self.planned_start, "计划开始时间")
        finish = _parse_datetime(self.planned_finish, "计划完成时间")
        if start >= finish:
            raise ValueError("计划开始时间必须早于计划完成时间")
        return self


class InjectionSchedulingTaskBulkMove(StrictWriteModel):
    factory_id: str
    expected_plan_revision: int = Field(ge=1)
    expected_rule_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    moves: list[InjectionSchedulingTaskMove] = Field(min_length=1, max_length=100)

    @field_validator("factory_id", "request_id")
    @classmethod
    def strip_bulk_move_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("moves")
    @classmethod
    def unique_tasks(cls, value: list[InjectionSchedulingTaskMove]):
        task_ids = [item.task_id for item in value]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("同一次移动中任务 ID 不能重复")
        return value


class InjectionSchedulingManualAppendPreviewRequest(StrictWriteModel):
    factory_id: str
    order_id: str = Field(min_length=1, max_length=96)
    machine_id: str = Field(min_length=1, max_length=96)
    expected_plan_revision: int = Field(ge=1)
    expected_order_revision: int = Field(ge=1)
    expected_rule_revision: int = Field(ge=1)

    @field_validator("factory_id", "order_id", "machine_id")
    @classmethod
    def strip_manual_append_preview_text(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingManualAppendConfirm(
    InjectionSchedulingManualAppendPreviewRequest
):
    request_id: str = Field(min_length=8, max_length=128)
    expected_input_fingerprint: str = Field(min_length=64, max_length=64)
    override_reason: str = Field(default="", max_length=2000)

    @field_validator("request_id", "expected_input_fingerprint", "override_reason")
    @classmethod
    def strip_manual_append_confirm_text(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingManualAppendPreview(BaseModel):
    factory_id: str
    plan_id: str
    plan_revision: int
    order_id: str
    order_revision: int
    machine_id: str
    sequence_no: int
    decision: FitDecision
    hard_failures: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    advisories: list[dict[str, Any]]
    planned_quantity: float
    shift_target_quantity: float
    planned_start: str
    planned_finish: str
    continuation_anchor: dict[str, Any]
    calculation: dict[str, Any]
    rule_set_id: str
    rule_revision: int
    input_fingerprint: str


class InjectionSchedulingTaskOut(BaseModel):
    id: str
    factory_id: str
    plan_id: str
    machine_id: str
    order_id: str
    mold_id: str | None
    mold_copy_no: int
    sequence_no: int
    execution_status: TaskStatus
    planned_start: str
    planned_finish: str
    shift_target_quantity: float
    reported_quantity: float
    estimated_start: str
    estimated_finish: str
    estimated_remaining_shifts: int
    delivery_slack_days: int | None
    locked: bool
    manual_override_reason: str
    active_execution: bool
    import_batch_id: str | None
    source_sheet_name: str
    source_row: int | None
    source_file_hash: str
    allocated_quantity: float
    takeover_source_completed_quantity: float
    origin: str
    stable_order_key: str
    stable_row_key: str
    source_task_id: str | None
    inherited_report_counter: float
    completed_at_clone: float
    report_event_watermark: int
    profile_id: str | None
    profile_revision: int | None
    setup_minutes: int
    production_minutes: int
    planned_downtime_minutes: int
    changeover_type: str
    auto_schedule_run_id: str | None
    auto_score: float | None
    auto_explanation: dict[str, Any]
    manual_adjusted: bool
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class InjectionSchedulingManualAppendResult(BaseModel):
    plan_id: str
    plan_revision: int
    task: InjectionSchedulingTaskOut
    decision: FitDecision
    calculation: dict[str, Any]
    audit_sequence: int
    input_fingerprint: str


class InjectionSchedulingPlanOrderStateOut(BaseModel):
    id: str
    factory_id: str
    plan_id: str
    order_id: str
    stable_order_key: str
    order_quantity: float
    delivery_start_date: str
    delivery_due_date: str
    takeover_source_completed_quantity: float
    report_increment_total: float
    progress_adjustment_total: float
    completed_quantity: float
    outstanding_quantity: float
    status: OrderStatus
    quantity_scope: Literal["ORDER_CUMULATIVE", "SPLIT_CUMULATIVE"]
    source_batch_id: str | None
    source_sheet_name: str
    source_row: int | None
    source_profile_id: str | None
    source_profile_revision: int | None
    source_lineage: dict[str, Any]
    revision: int


class InjectionSchedulingPlanOut(BaseModel):
    id: str
    factory_id: str
    business_date: str
    status: PlanStatus
    revision: int
    rule_set_id: str
    rule_revision: int
    based_on_plan_id: str
    based_on_event_sequence: int
    based_on_report_watermark: int
    export_profile_id: str | None
    export_profile_revision: int | None
    export_profile_family: str
    export_renderer_code: str
    export_binding_source: str
    calculation_version: str
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    published_by: str
    published_by_name: str
    created_at: str
    updated_at: str
    published_at: str
    archived_at: str
    orders: list[InjectionSchedulingOrderOut]
    plan_order_states: list[InjectionSchedulingPlanOrderStateOut]
    tasks: list[InjectionSchedulingTaskOut]


class InjectionSchedulingTaskMoveResult(BaseModel):
    task_id: str
    from_machine_id: str
    to_machine_id: str
    from_sequence_no: int
    to_sequence_no: int
    previous_start: str
    previous_finish: str
    planned_start: str
    planned_finish: str
    match: dict[str, Any]


class InjectionSchedulingTaskBulkMoveResult(BaseModel):
    plan: InjectionSchedulingPlanOut
    moves: list[InjectionSchedulingTaskMoveResult]
    audit_sequence: int
    idempotent_replay: bool = False


class InjectionSchedulingCurrentPlanOut(BaseModel):
    factory_id: str
    plan: InjectionSchedulingPlanOut | None
    polling_revision: int


class InjectionSchedulingPlanContextOut(BaseModel):
    factory_id: str
    execution_published_plan: InjectionSchedulingPlanOut | None
    planning_draft_plan: InjectionSchedulingPlanOut | None
    polling_revision: int


class InjectionSchedulingPublishInput(StrictWriteModel):
    factory_id: str
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)

    @field_validator("request_id")
    @classmethod
    def strip_request_id(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingRollbackInput(InjectionSchedulingPublishInput):
    business_date: date | None = None


class InjectionSchedulingPlanOperationOut(BaseModel):
    plan: InjectionSchedulingPlanOut
    snapshot_id: str
    audit_sequence: int
    idempotent_replay: bool = False


class InjectionSchedulingShiftReportCreate(StrictWriteModel):
    factory_id: str
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    business_date: date
    shift_code: ShiftCode
    quantity_mode: QuantityMode
    reported_quantity: float = Field(ge=0)
    shift_target_quantity: float = Field(default=0, ge=0)
    downtime_minutes: int = Field(default=0, ge=0, le=1440)
    exception_code: str = Field(default="", max_length=64)
    exception_detail: str = Field(default="", max_length=2000)
    reported_status: Literal["QUEUED", "RUNNING", "BLOCKED", "COMPLETED"] = (
        "RUNNING"
    )

    @field_validator("request_id", "exception_code", "exception_detail")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingShiftReportOut(BaseModel):
    id: str
    factory_id: str
    task_id: str
    order_id: str
    business_date: str
    shift_code: ShiftCode
    quantity_mode: QuantityMode
    reported_quantity: float
    normalized_increment_quantity: float
    shift_target_quantity: float
    downtime_minutes: int
    exception_code: str
    exception_detail: str
    reported_status: str
    request_id: str
    reported_by: str
    reported_by_name: str
    created_at: str


class InjectionSchedulingShiftReportResult(BaseModel):
    report: InjectionSchedulingShiftReportOut
    task: InjectionSchedulingTaskOut
    order: InjectionSchedulingOrderOut
    audit_sequence: int
    idempotent_replay: bool = False


class InjectionSchedulingShiftReportBulkItem(StrictWriteModel):
    task_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    business_date: date
    shift_code: ShiftCode
    quantity_mode: QuantityMode
    reported_quantity: float = Field(ge=0)
    shift_target_quantity: float = Field(default=0, ge=0)
    downtime_minutes: int = Field(default=0, ge=0, le=1440)
    exception_code: str = Field(default="", max_length=64)
    exception_detail: str = Field(default="", max_length=2000)
    reported_status: Literal["QUEUED", "RUNNING", "BLOCKED", "COMPLETED"] = (
        "RUNNING"
    )

    @field_validator("task_id", "request_id", "exception_code", "exception_detail")
    @classmethod
    def strip_bulk_report_text(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingShiftReportBulkCreate(StrictWriteModel):
    factory_id: str
    reports: list[InjectionSchedulingShiftReportBulkItem] = Field(
        min_length=1,
        max_length=100,
    )

    @field_validator("factory_id")
    @classmethod
    def strip_bulk_report_factory(cls, value: str) -> str:
        return value.strip()

    @field_validator("reports")
    @classmethod
    def unique_report_requests(cls, value: list[InjectionSchedulingShiftReportBulkItem]):
        request_ids = [item.request_id for item in value]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("批量回报 request_id 不能重复")
        task_ids = [item.task_id for item in value]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("同一次批量回报中任务 ID 不能重复")
        return value


class InjectionSchedulingShiftReportBulkResult(BaseModel):
    results: list[InjectionSchedulingShiftReportResult]
    latest_sequence: int


class InjectionSchedulingProgressAdjustmentCreate(StrictWriteModel):
    factory_id: str
    plan_id: str = Field(min_length=1, max_length=96)
    order_id: str = Field(min_length=1, max_length=96)
    task_id: str | None = Field(default=None, max_length=96)
    expected_state_revision: int = Field(ge=1)
    signed_quantity: float
    reason: str = Field(min_length=4, max_length=500)
    request_id: str = Field(min_length=8, max_length=128)

    @field_validator("factory_id", "plan_id", "order_id", "reason", "request_id")
    @classmethod
    def strip_adjustment_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("task_id")
    @classmethod
    def strip_adjustment_task(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @model_validator(mode="after")
    def require_nonzero_adjustment(self):
        if self.signed_quantity == 0:
            raise ValueError("进度更正数量不能为 0")
        return self


class InjectionSchedulingProgressAdjustmentOut(BaseModel):
    id: str
    factory_id: str
    plan_id: str
    order_id: str
    task_id: str | None
    signed_quantity: float
    before_quantity: float
    after_quantity: float
    reason: str
    source_kind: str
    source_batch_id: str | None
    source_sheet_name: str
    source_row: int | None
    request_id: str
    adjusted_by: str
    adjusted_by_name: str
    created_at: str


class InjectionSchedulingProgressAdjustmentResult(BaseModel):
    adjustment: InjectionSchedulingProgressAdjustmentOut
    state: InjectionSchedulingPlanOrderStateOut
    audit_sequence: int
    idempotent_replay: bool = False


class InjectionSchedulingEventOut(BaseModel):
    sequence: int
    id: str
    factory_id: str
    event_type: str
    entity_type: str
    entity_id: str
    entity_revision: int
    request_id: str
    detail: dict[str, Any]
    actor_user_id: str
    actor_name: str
    created_at: str


class InjectionSchedulingEventsOut(BaseModel):
    factory_id: str
    after_sequence: int
    latest_sequence: int
    retry_after_seconds: int = 12
    events: list[InjectionSchedulingEventOut]


def _parse_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}格式无效") from exc
    if parsed.tzinfo is not None:
        raise ValueError(f"{label}必须使用厂区本地时间且不带时区")
    return parsed
