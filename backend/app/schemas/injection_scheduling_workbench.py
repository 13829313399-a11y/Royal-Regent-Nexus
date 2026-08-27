from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WorkbenchJobStatus = Literal[
    "UNPLANNED",
    "PLANNED",
    "RUNNING",
    "PAUSED",
    "DONE",
]


class InjectionSchedulingWorkbenchMachineOut(BaseModel):
    id: str
    factory_id: str
    code: str
    position: str
    area: str
    a_class: float | None
    tonnage: float | None
    arm_capabilities: list[str]
    fixture_capabilities: list[str]
    process_restrictions: list[str]
    status: str
    available_for_auto_schedule: bool
    remark: str
    parsed_constraint_summary: str
    revision: int


class InjectionSchedulingWorkbenchJobOut(BaseModel):
    id: str
    factory_id: str
    plan_id: str | None
    task_id: str | None
    order_id: str
    machine_id: str | None
    machine_code: str
    sequence_no: int | None
    status: WorkbenchJobStatus
    order_no: str
    item_no: str
    product_name: str
    warehouse_text: str
    set_quantity: float | None
    order_quantity: float
    opening_completed_quantity: float
    reported_quantity: float
    completed_quantity: float
    outstanding_quantity: float
    completion_rate: float
    mold_id: str | None
    mold_no: str
    mold_name: str
    required_machine_a: float | None
    material_name: str
    sprue_ratio: float | None
    color_name: str
    color_powder_code: str
    net_weight_g: float | None
    gross_weight_g: float | None
    material_weight_kg: float | None
    unit_price: float | None
    spray_required: bool | None
    arm_requirement: str
    fixture_requirement: str
    order_date: str
    delivery_start_date: str
    delivery_due_date: str
    priority: str
    planned_start: str
    planned_finish: str
    estimated_finish: str
    delivery_slack_days: int | None
    shift_target_quantity: float
    today_day_quantity: float
    today_night_quantity: float
    downtime_minutes: int
    locked: bool
    manual_override_reason: str
    order_remark: str
    machine_remark: str
    parsed_constraint_summary: str
    suggestion_reason: str
    material_readiness_status: str
    mold_enrichment_status: str
    source_batch_id: str | None
    source_sheet_name: str
    source_row_number: int | None
    source_line_key: str
    task_revision: int | None
    order_revision: int
    plan_revision: int | None
    updated_by_name: str
    updated_at: str
    lineage: dict[str, Any]


class InjectionSchedulingWorkbenchSummaryOut(BaseModel):
    unplanned_count: int
    overdue_count: int
    conflict_count: int
    running_count: int
    today_day_quantity: float
    today_night_quantity: float


class InjectionSchedulingWorkbenchOut(BaseModel):
    factory_id: str
    business_date: str
    plan_id: str | None
    plan_revision: int | None
    rule_revision: int | None
    plan_mode: Literal["PLANNING", "EXECUTION", "EMPTY"]
    polling_revision: int
    machines: list[InjectionSchedulingWorkbenchMachineOut]
    jobs: list[InjectionSchedulingWorkbenchJobOut]
    summary: InjectionSchedulingWorkbenchSummaryOut


class InjectionSchedulingWorkbenchJobChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=128)
    expected_task_revision: int | None = Field(default=None, ge=1)
    expected_order_revision: int = Field(ge=1)
    field: Literal[
        "status",
        "shift_target_quantity",
        "planned_start",
        "planned_finish",
        "machine_id",
        "sequence_no",
        "locked",
        "manual_override_reason",
        "warehouse_text",
        "order_remark",
    ]
    value: str | float | int | bool

    @field_validator("job_id")
    @classmethod
    def strip_job_id(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_task_revision_for_task_field(self):
        if (
            self.field not in {"warehouse_text", "order_remark"}
            and self.expected_task_revision is None
        ):
            raise ValueError("任务字段修改必须提交任务版本")
        return self


class InjectionSchedulingWorkbenchBulkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_id: str
    expected_plan_revision: int | None = Field(default=None, ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    changes: list[InjectionSchedulingWorkbenchJobChange] = Field(
        min_length=1,
        max_length=200,
    )

    @field_validator("factory_id", "request_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()
