from pydantic import BaseModel, ConfigDict


class InjectionScheduleImportSummary(BaseModel):
    machine_count: int = 0
    old_machine_count: int = 0
    new_machine_count: int = 0
    task_count: int = 0
    scheduled_task_count: int = 0
    pending_task_count: int = 0
    relative_task_count: int = 0
    no_plan_task_count: int = 0
    total_shortage_qty: float = 0
    overdue_count: int = 0
    missing_due_count: int = 0
    negative_or_zero_shortage_count: int = 0
    huge_negative_gap_count: int = 0
    external_formula_risk_count: int = 0
    date_axis_days: int = 0
    date_axis_shift_columns: int = 0
    business_date: str = ""


class InjectionScheduleImportBatchOut(BaseModel):
    id: str
    factory_id: str
    import_type: str
    source_file_name: str
    business_date: str
    status: str
    summary: InjectionScheduleImportSummary
    created_by: str
    created_at: str


class InjectionScheduleMachineOut(BaseModel):
    id: str
    batch_id: str
    factory_id: str
    machine_code: str
    workshop: str
    machine_spec_label: str
    machine_process_type: str
    robot_type: str
    status: str
    constraints: dict[str, object]
    source_row: int


class InjectionScheduleTaskOut(BaseModel):
    id: str
    batch_id: str
    factory_id: str
    source_row: int
    assigned_machine_code: str
    task_bucket: str
    mold_code: str
    product_name: str
    order_no: str
    product_code: str
    machine_model: str
    color: str
    pigment: str
    material: str
    order_qty: float | None = None
    produced_qty: float | None = None
    shortage_qty: float | None = None
    daily_target_qty: float | None = None
    delivery_due_date: str
    plan_start_at: str
    plan_finish_at: str
    warehouse_due_at: str
    delivery_gap_days: float | None = None
    priority_flag: str
    remark: str
    source_values: dict[str, object]


class InjectionScheduleImportIssueOut(BaseModel):
    id: str
    batch_id: str
    source_row: int
    severity: str
    issue_type: str
    field_name: str
    raw_value: str
    message: str


class InjectionScheduleImportPreviewResponse(BaseModel):
    batch_id: str
    factory_id: str
    source_file_name: str
    business_date: str
    status: str
    summary: InjectionScheduleImportSummary
    machines: list[InjectionScheduleMachineOut]
    tasks: list[InjectionScheduleTaskOut]
    issues: list[InjectionScheduleImportIssueOut]

    model_config = ConfigDict(from_attributes=True)
