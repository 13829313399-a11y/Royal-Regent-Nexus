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
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class InjectionSchedulingPlanOut(BaseModel):
    id: str
    factory_id: str
    business_date: str
    status: PlanStatus
    revision: int
    rule_set_id: str
    rule_revision: int
    based_on_plan_id: str
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
    tasks: list[InjectionSchedulingTaskOut]


class InjectionSchedulingCurrentPlanOut(BaseModel):
    factory_id: str
    plan: InjectionSchedulingPlanOut | None
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
