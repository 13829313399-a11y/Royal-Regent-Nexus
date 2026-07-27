from __future__ import annotations

from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MachineStatus = Literal["available", "maintenance", "stopped", "retired"]
OrderStatus = Literal["open", "completed", "canceled"]
PriorityCode = Literal["P0", "P1", "P2", "P3"]
VersionStatus = Literal["draft", "published", "superseded"]
CommandType = Literal[
    "assign",
    "move",
    "reorder",
    "lock",
    "unlock",
    "split",
    "refresh_masters",
]


def reject_explicit_null(model: BaseModel, field_names: set[str]) -> None:
    supplied_nulls = sorted(
        field_name
        for field_name in field_names
        if field_name in model.model_fields_set
        and getattr(model, field_name) is None
    )
    if supplied_nulls:
        raise ValueError(
            f"以下字段不能显式设置为空：{', '.join(supplied_nulls)}"
        )


class InjectionImportConfirmRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    mode: Literal["merge"] = "merge"
    business_date: str = Field(min_length=10, max_length=10)
    reason: str = Field(min_length=4, max_length=2000)
    resolutions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("business_date")
    @classmethod
    def validate_business_date(cls, value: str) -> str:
        from datetime import date

        normalized = value.strip()
        date.fromisoformat(normalized)
        return normalized

    @field_validator("reason")
    @classmethod
    def strip_confirm_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 4:
            raise ValueError("确认原因至少填写 4 个字符")
        return normalized


class InjectionImportRejectRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("拒绝原因不能为空")
        return normalized


class InjectionImportIssueOut(BaseModel):
    id: str
    factory_id: str
    batch_id: str
    source_sheet: str
    source_row: int
    severity: str
    code: str
    field_name: str
    blocking: bool
    raw_value: str
    message: str


class InjectionImportBatchOut(BaseModel):
    id: str
    factory_id: str
    source_file_name: str
    source_content_type: str
    source_size_bytes: int
    source_sha256: str
    parser_version: str
    detected_sheets: list[str]
    status: str
    revision: int
    business_date: str
    draft_version_id: str
    summary: dict[str, Any]
    preview: dict[str, Any]
    issues: list[InjectionImportIssueOut] = Field(default_factory=list)
    created_by: str
    created_by_name: str
    created_at: str
    confirmed_by: str
    confirmed_by_name: str
    confirmed_at: str
    confirm_reason: str
    rejected_by: str
    rejected_by_name: str
    rejected_at: str
    rejection_reason: str


class InjectionMachineFields(BaseModel):
    machine_name: str = Field(default="", max_length=128)
    workshop: str = Field(default="", max_length=64)
    machine_class: str = Field(default="", max_length=128)
    tonnage_t: float | None = Field(default=None, gt=0)
    process_type: str = Field(default="", max_length=64)
    screw_type: str = Field(default="", max_length=64)
    robot_type: str = Field(default="", max_length=64)
    fixture_type: str = Field(default="", max_length=64)
    max_shot_weight_g: float | None = Field(default=None, gt=0)
    tie_bar_x_mm: float | None = Field(default=None, gt=0)
    tie_bar_y_mm: float | None = Field(default=None, gt=0)
    mold_thickness_min_mm: float | None = Field(default=None, ge=0)
    mold_thickness_max_mm: float | None = Field(default=None, gt=0)
    opening_stroke_mm: float | None = Field(default=None, gt=0)
    ejector_stroke_mm: float | None = Field(default=None, gt=0)
    status: MachineStatus = "available"
    available_at: str = Field(default="", max_length=32)
    capabilities: list[str] = Field(default_factory=list)
    material_rules: list[str] = Field(default_factory=list)
    quality_status: str = Field(default="verified", max_length=32)


class InjectionMachineCreateRequest(InjectionMachineFields):
    machine_code: str = Field(min_length=1, max_length=64)

    @field_validator("machine_code")
    @classmethod
    def strip_machine_code(cls, value: str) -> str:
        return value.strip()


class InjectionMachineUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    machine_name: str | None = Field(default=None, max_length=128)
    workshop: str | None = Field(default=None, max_length=64)
    machine_class: str | None = Field(default=None, max_length=128)
    tonnage_t: float | None = Field(default=None, gt=0)
    process_type: str | None = Field(default=None, max_length=64)
    screw_type: str | None = Field(default=None, max_length=64)
    robot_type: str | None = Field(default=None, max_length=64)
    fixture_type: str | None = Field(default=None, max_length=64)
    max_shot_weight_g: float | None = Field(default=None, gt=0)
    tie_bar_x_mm: float | None = Field(default=None, gt=0)
    tie_bar_y_mm: float | None = Field(default=None, gt=0)
    mold_thickness_min_mm: float | None = Field(default=None, ge=0)
    mold_thickness_max_mm: float | None = Field(default=None, gt=0)
    opening_stroke_mm: float | None = Field(default=None, gt=0)
    ejector_stroke_mm: float | None = Field(default=None, gt=0)
    status: MachineStatus | None = None
    available_at: str | None = Field(default=None, max_length=32)
    capabilities: list[str] | None = None
    material_rules: list[str] | None = None
    quality_status: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def reject_null_non_nullable_fields(self):
        reject_explicit_null(
            self,
            {
                "machine_name",
                "workshop",
                "machine_class",
                "process_type",
                "screw_type",
                "robot_type",
                "fixture_type",
                "status",
                "available_at",
                "capabilities",
                "material_rules",
                "quality_status",
            },
        )
        return self


class InjectionMachineOut(InjectionMachineFields):
    id: str
    factory_id: str
    machine_code: str
    provenance: dict[str, Any]
    source_batch_id: str
    revision: int
    created_by: str
    created_at: str
    updated_by: str
    updated_at: str


class InjectionMoldFields(BaseModel):
    mold_name: str = Field(default="", max_length=255)
    machine_class: str = Field(default="", max_length=128)
    robot_type: str = Field(default="", max_length=64)
    fixture_type: str = Field(default="", max_length=64)
    length_mm: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    mold_weight_kg: float | None = Field(default=None, gt=0)
    gross_shot_weight_g: float | None = Field(default=None, gt=0)
    mold_thickness_mm: float | None = Field(default=None, gt=0)
    required_opening_stroke_mm: float | None = Field(default=None, gt=0)
    required_screw_type: str = Field(default="", max_length=64)
    cavities: int | None = Field(default=None, gt=0)
    cycle_seconds: float | None = Field(default=None, gt=0)
    required_capabilities: list[str] = Field(default_factory=list)
    material_rules: list[str] = Field(default_factory=list)
    quality_status: str = Field(default="verified", max_length=32)


class InjectionMoldCreateRequest(InjectionMoldFields):
    mold_code: str = Field(min_length=1, max_length=128)

    @field_validator("mold_code")
    @classmethod
    def strip_mold_code(cls, value: str) -> str:
        return value.strip()


class InjectionMoldUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    mold_name: str | None = Field(default=None, max_length=255)
    machine_class: str | None = Field(default=None, max_length=128)
    robot_type: str | None = Field(default=None, max_length=64)
    fixture_type: str | None = Field(default=None, max_length=64)
    length_mm: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    mold_weight_kg: float | None = Field(default=None, gt=0)
    gross_shot_weight_g: float | None = Field(default=None, gt=0)
    mold_thickness_mm: float | None = Field(default=None, gt=0)
    required_opening_stroke_mm: float | None = Field(default=None, gt=0)
    required_screw_type: str | None = Field(default=None, max_length=64)
    cavities: int | None = Field(default=None, gt=0)
    cycle_seconds: float | None = Field(default=None, gt=0)
    required_capabilities: list[str] | None = None
    material_rules: list[str] | None = None
    quality_status: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def reject_null_non_nullable_fields(self):
        reject_explicit_null(
            self,
            {
                "mold_name",
                "machine_class",
                "robot_type",
                "fixture_type",
                "required_screw_type",
                "required_capabilities",
                "material_rules",
                "quality_status",
            },
        )
        return self


class InjectionMoldOut(InjectionMoldFields):
    id: str
    factory_id: str
    mold_code: str
    normalized_mold_code: str
    provenance: dict[str, Any]
    source_batch_id: str
    revision: int
    created_by: str
    created_at: str
    updated_by: str
    updated_at: str


class InjectionOrderFields(BaseModel):
    order_no: str = Field(default="", max_length=128)
    product_code: str = Field(default="", max_length=128)
    product_name: str = Field(default="", max_length=255)
    mold_code: str = Field(default="", max_length=128)
    color: str = Field(default="", max_length=128)
    pigment: str = Field(default="", max_length=128)
    material: str = Field(default="", max_length=255)
    machine_class: str = Field(default="", max_length=128)
    order_qty: float = Field(default=0, ge=0)
    produced_qty: float = Field(default=0, ge=0)
    daily_target_qty: float | None = Field(default=None, gt=0)
    delivery_due_date: str = Field(default="", max_length=20)
    priority_flag: str = Field(default="", max_length=32)
    color_rank: int | None = Field(default=None, ge=0, le=100)
    downstream_urgency: float | None = Field(default=None, ge=0, le=1)
    warehouse_buffer_hours: float = Field(default=0, ge=0, le=720)
    downstream_buffer_hours: float = Field(default=0, ge=0, le=720)
    special_handling_reason: str = Field(default="", max_length=2_000)
    status: OrderStatus = "open"
    imported_assigned_machine_code: str = Field(default="", max_length=64)
    quality_status: str = Field(default="verified", max_length=32)

    @field_validator("delivery_due_date")
    @classmethod
    def validate_delivery_due_date(cls, value: str) -> str:
        from datetime import date

        normalized = value.strip()
        if normalized:
            try:
                date.fromisoformat(normalized)
            except ValueError as error:
                raise ValueError("交期必须为 YYYY-MM-DD") from error
        return normalized


class InjectionOrderCreateRequest(InjectionOrderFields):
    natural_key: str | None = Field(default=None, max_length=256)


class InjectionOrderUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    order_no: str | None = Field(default=None, max_length=128)
    product_code: str | None = Field(default=None, max_length=128)
    product_name: str | None = Field(default=None, max_length=255)
    mold_code: str | None = Field(default=None, max_length=128)
    color: str | None = Field(default=None, max_length=128)
    pigment: str | None = Field(default=None, max_length=128)
    material: str | None = Field(default=None, max_length=255)
    machine_class: str | None = Field(default=None, max_length=128)
    order_qty: float | None = Field(default=None, ge=0)
    produced_qty: float | None = Field(default=None, ge=0)
    daily_target_qty: float | None = Field(default=None, gt=0)
    delivery_due_date: str | None = Field(default=None, max_length=20)
    priority_flag: str | None = Field(default=None, max_length=32)
    color_rank: int | None = Field(default=None, ge=0, le=100)
    downstream_urgency: float | None = Field(default=None, ge=0, le=1)
    warehouse_buffer_hours: float | None = Field(default=None, ge=0, le=720)
    downstream_buffer_hours: float | None = Field(default=None, ge=0, le=720)
    special_handling_reason: str | None = Field(default=None, max_length=2_000)
    status: OrderStatus | None = None
    imported_assigned_machine_code: str | None = Field(default=None, max_length=64)
    quality_status: str | None = Field(default=None, max_length=32)

    @field_validator("delivery_due_date")
    @classmethod
    def validate_delivery_due_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from datetime import date

        normalized = value.strip()
        if normalized:
            try:
                date.fromisoformat(normalized)
            except ValueError as error:
                raise ValueError("交期必须为 YYYY-MM-DD") from error
        return normalized

    @model_validator(mode="after")
    def reject_null_non_nullable_fields(self):
        reject_explicit_null(
            self,
            {
                "order_no",
                "product_code",
                "product_name",
                "mold_code",
                "color",
                "pigment",
                "material",
                "machine_class",
                "order_qty",
                "produced_qty",
                "delivery_due_date",
                "priority_flag",
                "warehouse_buffer_hours",
                "downstream_buffer_hours",
                "special_handling_reason",
                "status",
                "imported_assigned_machine_code",
                "quality_status",
            },
        )
        return self


class InjectionOrderOut(InjectionOrderFields):
    id: str
    factory_id: str
    natural_key: str
    outstanding_qty: float
    priority_code: PriorityCode
    imported_plan_start_at: str
    imported_plan_finish_at: str
    source_sheet: str
    source_row: int
    source_batch_id: str
    source_values: dict[str, Any]
    provenance: dict[str, Any]
    revision: int
    created_by: str
    created_at: str
    updated_by: str
    updated_at: str


class InjectionScheduleVersionCreateRequest(BaseModel):
    name: str = Field(default="", max_length=128)
    business_date: str = Field(default="", max_length=20)
    plan_base_at: str = Field(default="", max_length=32)
    base_version_id: str | None = Field(default=None, max_length=96)


class InjectionScheduleCloneRequest(BaseModel):
    name: str = Field(default="", max_length=128)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("复制原因不能为空")
        return normalized


class InjectionScheduleVersionOut(BaseModel):
    id: str
    factory_id: str
    version_no: int
    name: str
    status: VersionStatus
    revision: int
    business_date: str
    plan_base_at: str
    base_version_id: str | None
    source_batch_id: str
    rules_snapshot: dict[str, Any]
    rule_config_revision: int
    data_hash: str
    validation_hash: str
    summary: dict[str, Any]
    created_by: str
    created_by_name: str
    created_at: str
    updated_by: str
    updated_at: str
    published_by: str
    published_by_name: str
    published_at: str
    publish_reason: str
    superseded_at: str


class InjectionScheduleTaskOut(BaseModel):
    id: str
    factory_id: str
    version_id: str
    order_id: str
    order_no: str
    product_code: str
    product_name: str
    delivery_due_date: str
    mold_id: str | None
    mold_code: str
    color: str
    color_rank: int | None
    material: str
    machine_id: str
    machine_code: str
    sequence_no: int
    planned_qty: float
    planned_start_at: str
    planned_finish_at: str
    setup_hours: float
    duration_hours: float
    locked: bool
    split_group_id: str
    parent_task_id: str
    source: Literal["import", "manual", "recommendation", "auto", "legacy"]
    execution_status: Literal["planned", "running", "completed", "cancelled"]
    protected: bool
    recommendation_score: float | None
    score_breakdown: list[dict[str, Any]]
    constraint_snapshot: list[dict[str, Any]]
    recommendation_context_hash: str
    risk_level: str
    risk_reasons: list[str]
    revision: int


class InjectionScheduleCommand(BaseModel):
    type: CommandType
    order_id: str | None = Field(default=None, max_length=96)
    task_id: str | None = Field(default=None, max_length=96)
    machine_id: str | None = Field(default=None, max_length=96)
    target_index: int | None = Field(default=None, ge=0)
    planned_qty: float | None = Field(default=None, gt=0)
    split_qty: float | None = Field(default=None, gt=0)
    manual_confirmation: bool = False
    manual_confirmation_reason: str = Field(default="", max_length=2000)
    recommendation_context_hash: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def validate_command_fields(self):
        if self.type == "assign" and (not self.order_id or not self.machine_id):
            raise ValueError("assign 命令必须提供 order_id 和 machine_id")
        if self.type in {"move", "reorder", "lock", "unlock", "split"} and not self.task_id:
            raise ValueError(f"{self.type} 命令必须提供 task_id")
        if self.type == "move" and not self.machine_id:
            raise ValueError("move 命令必须提供 machine_id")
        if self.type == "split" and self.split_qty is None:
            raise ValueError("split 命令必须提供 split_qty")
        if self.manual_confirmation and len(self.manual_confirmation_reason.strip()) < 4:
            raise ValueError("人工确认原因至少填写 4 个字符")
        if self.recommendation_context_hash and self.type != "assign":
            raise ValueError("只有 assign 命令可以引用推荐上下文")
        return self


class InjectionScheduleCommandRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(default="", max_length=128)
    commands: list[InjectionScheduleCommand] = Field(min_length=1, max_length=100)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("排程变更原因不能为空")
        return normalized

    @model_validator(mode="after")
    def recommendation_assign_must_be_atomic(self):
        if any(command.recommendation_context_hash for command in self.commands):
            if len(self.commands) != 1:
                raise ValueError("引用推荐上下文的 assign 必须作为单条原子命令提交")
        return self


class InjectionScheduleConflictOut(BaseModel):
    id: str
    run_id: str
    version_id: str
    task_id: str
    constraint_code: str
    status: Literal["pass", "fail", "unknown"]
    severity: str
    blocking: bool
    message: str
    details: dict[str, Any]


class InjectionScheduleValidationOut(BaseModel):
    id: str
    factory_id: str
    version_id: str
    version_revision: int
    data_hash: str
    result_hash: str
    status: Literal["passed", "blocked"]
    blocking_count: int
    warning_count: int
    created_by: str
    created_by_name: str
    created_at: str
    items: list[InjectionScheduleConflictOut]


class InjectionScheduleValidateRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class InjectionScheduleCommandResponse(BaseModel):
    version: InjectionScheduleVersionOut
    tasks: list[InjectionScheduleTaskOut]
    conflicts: list[InjectionScheduleConflictOut]
    affected_machine_ids: list[str]


class InjectionScheduleVersionDetailOut(BaseModel):
    version: InjectionScheduleVersionOut
    tasks: list[InjectionScheduleTaskOut]
    conflicts: list[InjectionScheduleConflictOut]


class InjectionSchedulePublishRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    validation_run_id: str | None = Field(default=None, max_length=96)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("发布原因不能为空")
        return normalized


class InjectionScheduleDiffItemOut(BaseModel):
    order_id: str
    order_no: str
    change_type: Literal["added", "removed", "moved", "rescheduled", "quantity_changed"]
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class InjectionScheduleDiffOut(BaseModel):
    version_id: str
    against_version_id: str | None
    summary: dict[str, int]
    items: list[InjectionScheduleDiffItemOut]


class InjectionScheduleScoringWeights(BaseModel):
    due_date: float = Field(default=35, ge=0, le=100)
    sequence_affinity: float = Field(default=15, ge=0, le=100)
    setup_efficiency: float = Field(default=15, ge=0, le=100)
    color_transition: float = Field(default=10, ge=0, le=100)
    load_balance: float = Field(default=10, ge=0, le=100)
    downstream_priority: float = Field(default=10, ge=0, le=100)
    exact_match: float = Field(default=5, ge=0, le=100)
    split_penalty: float = Field(default=12, ge=0, le=100)
    special_handling_penalty: float = Field(default=8, ge=0, le=100)

    @model_validator(mode="after")
    def reject_non_finite_values(self):
        for field_name in type(self).model_fields:
            if not isfinite(float(getattr(self, field_name))):
                raise ValueError(f"{field_name} 必须为有限数值")
        return self


class InjectionScheduleTransitionMatrixRow(BaseModel):
    from_code: str = Field(min_length=1, max_length=128)
    to_code: str = Field(min_length=1, max_length=128)
    minutes: float = Field(ge=0, le=1_440)

    @field_validator("from_code", "to_code")
    @classmethod
    def strip_transition_code(cls, value: str) -> str:
        return value.strip()

    @field_validator("minutes")
    @classmethod
    def finite_minutes(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("转换分钟必须为有限数值")
        return value


class InjectionScheduleSetupMinutesRow(BaseModel):
    machine_class: str = Field(min_length=1, max_length=128)
    same_mold_minutes: float = Field(default=0, ge=0, le=1_440)
    mold_change_minutes: float = Field(default=60, ge=0, le=1_440)

    @field_validator("machine_class")
    @classmethod
    def strip_machine_class(cls, value: str) -> str:
        return value.strip()

    @field_validator("same_mold_minutes", "mold_change_minutes")
    @classmethod
    def finite_setup_minutes(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("换模分钟必须为有限数值")
        return value


class InjectionScheduleUnavailableWindow(BaseModel):
    scope: Literal["factory", "machine"]
    machine_id: str = Field(default="", max_length=96)
    start_at: str = Field(min_length=1, max_length=32)
    end_at: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_window(self):
        from app.core.time import parse_business_timestamp

        if self.scope == "machine" and not self.machine_id.strip():
            raise ValueError("机台停机窗口必须提供 machine_id")
        if self.scope == "factory" and self.machine_id.strip():
            raise ValueError("厂区停机窗口不能提供 machine_id")
        start = parse_business_timestamp(self.start_at)
        end = parse_business_timestamp(self.end_at)
        if start is None or end is None:
            raise ValueError("停机窗口时间格式无效")
        if end <= start:
            raise ValueError("停机窗口结束时间必须晚于开始时间")
        self.machine_id = self.machine_id.strip()
        self.reason = self.reason.strip()
        return self


class InjectionScheduleRuleConfigDocument(BaseModel):
    schema_version: Literal[1] = 1
    shot_safety_factor: float = Field(default=0.85, gt=0, le=1)
    default_setup_hours: float = Field(default=1, ge=0, le=24)
    minimum_task_hours: float = Field(default=0.25, gt=0, le=24)
    allow_missing_data_in_draft_with_manual_confirmation: bool = True
    availability_calendar_verified_through: str = Field(default="", max_length=32)
    color_rank_dark_threshold: int = Field(default=5, ge=1, le=100)
    scoring_weights: InjectionScheduleScoringWeights = Field(
        default_factory=InjectionScheduleScoringWeights
    )
    color_transition_matrix: list[InjectionScheduleTransitionMatrixRow] = Field(
        min_length=1,
        max_length=500,
    )
    material_transition_matrix: list[InjectionScheduleTransitionMatrixRow] = Field(
        min_length=1,
        max_length=500,
    )
    setup_minutes: list[InjectionScheduleSetupMinutesRow] = Field(
        min_length=1,
        max_length=100,
    )
    unavailable_windows: list[InjectionScheduleUnavailableWindow] = Field(
        default_factory=list,
        max_length=2_000,
    )

    @field_validator(
        "shot_safety_factor",
        "default_setup_hours",
        "minimum_task_hours",
    )
    @classmethod
    def finite_rule_number(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("规则数值必须为有限数值")
        return value

    @field_validator("availability_calendar_verified_through")
    @classmethod
    def validate_calendar_horizon(cls, value: str) -> str:
        from app.core.time import parse_business_timestamp

        normalized = value.strip()
        if normalized and parse_business_timestamp(normalized) is None:
            raise ValueError("日历核验截止时间格式无效")
        return normalized

    @model_validator(mode="after")
    def validate_matrix_keys(self):
        for label, rows in (
            ("颜色转换矩阵", self.color_transition_matrix),
            ("材料转换矩阵", self.material_transition_matrix),
        ):
            keys = [(row.from_code.casefold(), row.to_code.casefold()) for row in rows]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{label}不能包含重复方向")
            if ("*", "*") not in keys:
                raise ValueError(f"{label}必须包含 */* 兜底行")
        setup_keys = [row.machine_class.casefold() for row in self.setup_minutes]
        if len(set(setup_keys)) != len(setup_keys):
            raise ValueError("换模时间不能包含重复机型")
        if "*" not in setup_keys:
            raise ValueError("换模时间必须包含 * 兜底行")
        return self


class InjectionScheduleRuleConfigUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=4, max_length=2_000)
    config: InjectionScheduleRuleConfigDocument

    @field_validator("reason")
    @classmethod
    def strip_rule_change_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 4:
            raise ValueError("规则变更原因至少填写 4 个字符")
        return normalized


class InjectionScheduleRuleConfigOut(BaseModel):
    factory_id: str
    config: InjectionScheduleRuleConfigDocument
    revision: int
    updated_by: str
    updated_at: str


class InjectionRecommendationHardConstraintOut(BaseModel):
    code: str
    status: Literal["pass", "fail", "unknown"]
    blocking: bool
    message: str
    details: dict[str, Any]


class InjectionRecommendationScoreBreakdownOut(BaseModel):
    code: str
    label: str
    weight: float
    raw_score: float
    weighted_score: float
    explanation: str


class InjectionRecommendationTransitionOut(BaseModel):
    previous_task_id: str
    next_task_id: str
    previous_mold_code: str
    next_mold_code: str
    previous_color: str
    previous_color_rank: int | None
    target_color: str
    target_color_rank: int | None
    next_color: str
    next_color_rank: int | None
    previous_material: str
    next_material: str
    same_mold: bool
    color_minutes: float | None
    material_minutes: float | None
    after_color_minutes: float | None
    after_material_minutes: float | None
    replaced_color_minutes: float | None
    replaced_material_minutes: float | None
    setup_minutes_before: float
    setup_minutes_after: float
    replaced_setup_minutes: float
    setup_minutes_delta: float
    color_matrix_match: str
    material_matrix_match: str
    after_color_matrix_match: str
    after_material_matrix_match: str
    replaced_color_matrix_match: str
    replaced_material_matrix_match: str


class InjectionRecommendationEstimateOut(BaseModel):
    slot_start_at: str
    production_start_at: str
    finish_at: str
    duration_hours: float
    delivery_slack_hours: float | None
    downstream_shift_minutes: float
    skipped_unavailable_windows: list[dict[str, str]]
    skipped_unavailable_window_count: int


class InjectionRecommendationScoreOut(BaseModel):
    total: float
    max_total: float
    advisory: bool
    breakdown: list[InjectionRecommendationScoreBreakdownOut]
    transition: InjectionRecommendationTransitionOut
    estimated: InjectionRecommendationEstimateOut


class InjectionMachineRecommendationOut(BaseModel):
    rank: int | None
    advisory_rank: int | None
    machine_id: str
    machine_code: str
    machine_name: str
    target_index: int
    status: Literal["eligible", "manual_review", "blocked"]
    eligible: bool
    requires_manual_confirmation: bool
    auto_publish_allowed: bool
    hard_constraints: list[InjectionRecommendationHardConstraintOut]
    score: InjectionRecommendationScoreOut | None
    recommendation_context_hash: str


class InjectionOrderRecommendationsOut(BaseModel):
    factory_id: str
    version_id: str
    version_revision: int
    order_id: str
    order_revision: int
    planned_qty: float
    rule_config_revision: int
    current_rule_config_revision: int
    rule_config_hash: str
    uses_version_rule_snapshot: Literal[True] = True
    generated_at: str
    total_candidates: int
    eligible_count: int
    manual_review_count: int
    blocked_count: int
    candidates: list[InjectionMachineRecommendationOut]


class InjectionScheduleWorkspaceOut(BaseModel):
    factory_id: str
    mode: Literal["formal"] = "formal"
    active_version: InjectionScheduleVersionOut | None
    versions: list[InjectionScheduleVersionOut]
    machines: list[InjectionMachineOut]
    molds: list[InjectionMoldOut]
    orders: list[InjectionOrderOut]
    tasks: list[InjectionScheduleTaskOut]
    conflicts: list[InjectionScheduleConflictOut]
    rule_config: InjectionScheduleRuleConfigOut
    workspace_revision: int


class InjectionScheduleAuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    entity_type: str
    entity_id: str
    action: str
    actor_id: str
    actor_name: str
    request_id: str
    ip_address: str
    reason: str
    old_revision: int | None
    new_revision: int | None
    before: dict[str, Any]
    after: dict[str, Any]
    created_at: str


class InjectionScheduleAutoDraftRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)
    name: str = Field(default="", max_length=128)
    order_ids: list[str] = Field(default_factory=list, max_length=1_500)
    planning_horizon_end_at: str = Field(default="", max_length=32)
    request_id: str = Field(default="", max_length=128)
    dry_run: bool = False
    expected_context_hash: str = Field(default="", max_length=64)

    @field_validator("reason")
    @classmethod
    def strip_auto_draft_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("自动排程原因不能为空")
        return normalized

    @field_validator("order_ids")
    @classmethod
    def unique_order_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(set(normalized)) != len(normalized):
            raise ValueError("order_ids 不能重复")
        return normalized

    @field_validator("planning_horizon_end_at")
    @classmethod
    def validate_planning_horizon(cls, value: str) -> str:
        normalized = value.strip()
        if normalized:
            from app.core.time import parse_business_timestamp

            if parse_business_timestamp(normalized) is None:
                raise ValueError("planning_horizon_end_at 不是有效时间")
        return normalized


class InjectionScheduleReplanTrigger(BaseModel):
    type: Literal["urgent_order", "machine_downtime"]
    order_id: str = Field(default="", max_length=96)
    machine_id: str = Field(default="", max_length=96)
    start_at: str = Field(default="", max_length=32)
    end_at: str = Field(default="", max_length=32)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_trigger_fields(self):
        from app.core.time import parse_business_timestamp

        if self.type == "urgent_order":
            if not self.order_id.strip():
                raise ValueError("急单重排必须提供 order_id")
            if self.machine_id or self.start_at or self.end_at:
                raise ValueError("急单重排不能提供停机字段")
        else:
            if not self.machine_id.strip():
                raise ValueError("停机重排必须提供 machine_id")
            start = parse_business_timestamp(self.start_at)
            end = parse_business_timestamp(self.end_at)
            if start is None or end is None or end <= start:
                raise ValueError("停机开始/结束时间无效")
            if self.order_id:
                raise ValueError("停机重排不能提供 order_id")
        self.order_id = self.order_id.strip()
        self.machine_id = self.machine_id.strip()
        self.start_at = self.start_at.strip()
        self.end_at = self.end_at.strip()
        self.reason = self.reason.strip()
        return self


class InjectionScheduleReplanScope(BaseModel):
    freeze_before_at: str = Field(default="", max_length=32)
    max_affected_machines: int = Field(default=10, ge=1, le=76)
    max_affected_tasks: int = Field(default=500, ge=1, le=1_500)

    @field_validator("freeze_before_at")
    @classmethod
    def validate_freeze_before_at(cls, value: str) -> str:
        normalized = value.strip()
        if normalized:
            from app.core.time import parse_business_timestamp

            if parse_business_timestamp(normalized) is None:
                raise ValueError("freeze_before_at 不是有效时间")
        return normalized


class InjectionScheduleReplanRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    trigger: InjectionScheduleReplanTrigger
    scope: InjectionScheduleReplanScope = Field(
        default_factory=InjectionScheduleReplanScope
    )
    reason: str = Field(min_length=1, max_length=2_000)
    name: str = Field(default="", max_length=128)
    request_id: str = Field(default="", max_length=128)
    dry_run: bool = False
    expected_context_hash: str = Field(default="", max_length=64)

    @field_validator("reason")
    @classmethod
    def strip_replan_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("局部重排原因不能为空")
        return normalized


class InjectionScheduleReplanRunOut(BaseModel):
    id: str
    factory_id: str
    source_version_id: str
    result_version_id: str
    trigger_type: Literal[
        "auto_draft",
        "urgent_order",
        "machine_downtime",
        "shift_actual",
    ]
    status: Literal["previewed", "applied"]
    source_revision: int
    result_revision: int
    context_hash: str
    reason: str
    request_id: str
    affected_machine_ids: list[str]
    affected_order_ids: list[str]
    affected_task_ids: list[str]
    impact: dict[str, Any]
    created_by: str
    created_by_name: str
    created_at: str


class InjectionScheduleReplanResponse(BaseModel):
    version: InjectionScheduleVersionOut
    tasks: list[InjectionScheduleTaskOut]
    conflicts: list[InjectionScheduleConflictOut]
    affected_machine_ids: list[str]
    affected_order_ids: list[str]
    affected_task_ids: list[str]
    run: InjectionScheduleReplanRunOut


class InjectionScheduleShiftActualCreateRequest(BaseModel):
    version_id: str = Field(min_length=1, max_length=96)
    task_id: str = Field(min_length=1, max_length=96)
    order_id: str = Field(min_length=1, max_length=96)
    machine_id: str = Field(min_length=1, max_length=96)
    shift_date: str = Field(min_length=10, max_length=10)
    shift: Literal["day", "night"]
    source: Literal["manual", "workbook"] = "manual"
    legacy_shift_code: Literal["", "A", "B"] = ""
    target_qty: float | None = Field(default=None, ge=0)
    actual_qty: float = Field(ge=0)
    variance_reason: str = Field(default="", max_length=2_000)
    expected_version_revision: int = Field(ge=1)
    expected_order_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)
    request_id: str = Field(min_length=1, max_length=128)

    @field_validator("shift_date")
    @classmethod
    def validate_shift_date(cls, value: str) -> str:
        from datetime import date

        normalized = value.strip()
        date.fromisoformat(normalized)
        return normalized

    @field_validator("actual_qty")
    @classmethod
    def finite_actual_qty(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("actual_qty 必须为有限数值")
        return value

    @field_validator("reason")
    @classmethod
    def strip_actual_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("实绩回写原因不能为空")
        return normalized

    @field_validator("request_id")
    @classmethod
    def strip_actual_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("实绩回写 request_id 不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_legacy_shift_code(self):
        expected = "A" if self.shift == "day" else "B"
        if self.legacy_shift_code and self.legacy_shift_code != expected:
            raise ValueError("A 班必须对应白班，B 班必须对应夜班")
        if not self.legacy_shift_code:
            self.legacy_shift_code = expected
        return self


class InjectionScheduleShiftActualCorrectionRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    expected_version_revision: int = Field(ge=1)
    expected_order_revision: int = Field(ge=1)
    actual_qty: float = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2_000)
    request_id: str = Field(min_length=1, max_length=128)

    @field_validator("actual_qty")
    @classmethod
    def finite_corrected_qty(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("actual_qty 必须为有限数值")
        return value

    @field_validator("reason")
    @classmethod
    def strip_correction_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("实绩更正原因不能为空")
        return normalized

    @field_validator("request_id")
    @classmethod
    def strip_correction_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("实绩更正 request_id 不能为空")
        return normalized


class InjectionScheduleShiftActualOut(BaseModel):
    id: str
    factory_id: str
    version_id: str
    task_id: str
    source_version_id: str
    source_task_id: str
    lineage_sequence: int
    order_id: str
    machine_id: str
    shift_date: str
    shift: Literal["day", "night"]
    source: Literal["manual", "workbook"]
    legacy_shift_code: str
    target_qty: float | None
    actual_qty: float
    variance_qty: float | None
    variance_reason: str
    produced_baseline_qty: float
    outstanding_qty_before: float
    outstanding_qty_after: float
    shortage_qty: float
    request_id: str
    revision: int
    correction_count: int
    created_by: str
    created_by_name: str
    created_at: str
    corrected_by: str
    corrected_by_name: str
    corrected_at: str


class InjectionScheduleActualProjectionOut(BaseModel):
    task_id: str
    order_id: str
    machine_id: str
    machine_code: str
    planned_qty_before: float
    planned_qty_after: float
    planned_finish_at_before: str
    planned_finish_at_after: str
    eta_shift_minutes: float
    shortage_qty: float


class InjectionScheduleShiftActualResponse(BaseModel):
    actual: InjectionScheduleShiftActualOut
    updated_order: InjectionOrderOut
    version: InjectionScheduleVersionOut
    tasks: list[InjectionScheduleTaskOut]
    projections: list[InjectionScheduleActualProjectionOut]
    affected_machine_ids: list[str]
    idempotent_replay: bool
