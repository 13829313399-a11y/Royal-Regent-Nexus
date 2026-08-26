import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ai.preview import AIPreviewManifestV1


class AIWorkbookSourceLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file_name: str = Field(min_length=1, max_length=255)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(gt=0)
    detected_format: Literal["XLSX", "XLSM"]
    inspector_version: Literal["workbook-semantic-snapshot-v1"]
    artifact_id: str | None = Field(
        default=None,
        pattern=r"^aiart-[0-9a-f]{32}$",
    )


class AIWorkbookHeaderCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1, max_length=4)
    header_text: str = Field(min_length=1, max_length=160)
    normalized_header: str = Field(min_length=1, max_length=160)


class AIWorkbookHeaderCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    cells: list[AIWorkbookHeaderCell] = Field(max_length=40)


class AIWorkbookRedactedSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_ref: str = Field(min_length=1, max_length=16)
    header_text: str = Field(default="", max_length=160)
    value_kind: Literal["TEXT", "NUMBER", "DATE", "BOOLEAN", "FORMULA", "BLANK"]
    raw_sample: str = Field(max_length=200)
    display_sample: str = Field(max_length=200)
    formula_shape: str = Field(default="", max_length=200)
    leading_zero: bool = False


class AIWorkbookSheetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    state: Literal["visible", "hidden", "veryHidden"]
    max_row: int = Field(ge=1)
    max_column: int = Field(ge=1)
    dimension: str = Field(min_length=1, max_length=64)
    merged_region_count: int = Field(ge=0)
    merged_regions: list[str] = Field(max_length=100)
    hidden_row_count: int = Field(ge=0)
    hidden_column_count: int = Field(ge=0)
    formula_cell_count: int = Field(ge=0)
    candidate_headers: list[AIWorkbookHeaderCandidate] = Field(max_length=3)
    redacted_samples: list[AIWorkbookRedactedSample] = Field(max_length=36)


class AIWorkbookSemanticSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workbook-semantic-snapshot-v1"] = (
        "workbook-semantic-snapshot-v1"
    )
    tool_name: Literal["workbook.inspect"] = "workbook.inspect"
    risk_level: Literal["PREVIEW_WITH_AUDIT"] = "PREVIEW_WITH_AUDIT"
    source_type: Literal["USER_PROVIDED"] = "USER_PROVIDED"
    factory_id: str = Field(min_length=1, max_length=64)
    source_lineage: AIWorkbookSourceLineage
    sheet_count: int = Field(ge=1, le=50)
    formula_cell_count: int = Field(ge=0)
    hidden_sheet_count: int = Field(ge=0)
    has_macros: bool
    has_drawings: bool
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sheets: list[AIWorkbookSheetSnapshot] = Field(min_length=1, max_length=50)
    warnings: list[str] = Field(max_length=20)


class AIWorkbookMappingFieldProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_field: str = Field(min_length=1, max_length=128)
    source_header: str = Field(min_length=1, max_length=160)
    source_sheet: str = Field(min_length=1, max_length=128)
    source_column: str = Field(min_length=1, max_length=4)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=4, max_length=500)
    transformer: str = Field(min_length=1, max_length=64)
    required: bool
    canonical_type: str = Field(min_length=1, max_length=64)
    authority: str = Field(min_length=1, max_length=64)


class AIWorkbookMappingProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workbook-mapping-proposal-v1"] = (
        "workbook-mapping-proposal-v1"
    )
    result_type: Literal["workbook.mapping_proposal"] = "workbook.mapping_proposal"
    source_type: Literal["MODEL_INFERENCE"] = "MODEL_INFERENCE"
    risk_level: Literal["PREVIEW_WITH_AUDIT"] = "PREVIEW_WITH_AUDIT"
    factory_id: str = Field(min_length=1, max_length=64)
    document_kind: Literal[
        "DEMAND_ORDER", "PLANNED_SCHEDULE", "SYSTEM_ROUND_TRIP", "MASTER_DATA"
    ]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_by_model: str = Field(min_length=1, max_length=128)
    profile_registry: Literal["injection_scheduling_import_profiles"] = (
        "injection_scheduling_import_profiles"
    )
    target_status: Literal["PROFILE_DRAFT"] = "PROFILE_DRAFT"
    approval_required: Literal[True] = True
    known_profile_id: str | None = Field(default=None, max_length=96)
    proposal: list[AIWorkbookMappingFieldProposal] = Field(max_length=100)
    missing_required_fields: list[str] = Field(max_length=100)
    warnings: list[str] = Field(max_length=30)
    stale_guards: dict[str, str] = Field(max_length=8)
    preview_manifest: AIPreviewManifestV1 | None = None


class AIModelMappingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_field: str = Field(min_length=1, max_length=128)
    source_header: str = Field(min_length=1, max_length=160)
    source_sheet: str = Field(min_length=1, max_length=128)
    source_column: str = Field(min_length=1, max_length=4)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=4, max_length=500)
    transformer: str = Field(min_length=1, max_length=64)


class AIModelMappingProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[AIModelMappingItem] = Field(max_length=100)
    warnings: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def unique_sources_and_targets(self):
        targets = [item.canonical_field for item in self.mappings]
        sources = [
            (item.source_sheet, item.source_column, item.source_header)
            for item in self.mappings
        ]
        if len(targets) != len(set(targets)) or len(sources) != len(set(sources)):
            raise ValueError("映射来源和目标不能重复")
        return self


AI_INJECTION_PLAN_CANONICAL_FIELDS = frozenset(
    {
        "machine_code",
        "item_no",
        "legacy_machine_class_text",
        "mold_no",
        "product_name",
        "order_no",
        "warehouse_text",
        "set_quantity",
        "order_quantity",
        "completed_quantity",
        "daily_target_quantity",
        "shift_target_quantity",
        "material_name",
        "sprue_ratio",
        "color_name",
        "color_powder_code",
        "whole_shot_net_weight_g",
        "whole_shot_gross_weight_g",
        "order_date",
        "delivery_start_date",
        "delivery_due_date",
        "planned_start",
        "planned_finish",
        "requires_spray_paint",
        "remark",
        "required_arm_type",
        "required_fixture_type",
        "automation_mode",
        "legacy_marker",
        "material_weight_kg",
        "unit_price",
        "outsource_price",
        "price_ratio",
        "ship_date",
        "legacy_mold_change",
        "legacy_color_change",
        "legacy_setup",
        "legacy_downtime",
        "source_outstanding_quantity",
        "source_plan_month",
        "source_delivery_slack",
        "source_production_days",
        "source_warehouse_date",
        "source_machine_finish",
    }
)
AI_INJECTION_PLAN_REQUIRED_FIELDS = frozenset(
    {
        "machine_code",
        "mold_no",
        "order_no",
        "order_quantity",
        "completed_quantity",
        "planned_start",
        "planned_finish",
    }
)
_CELL_REF_PATTERN = re.compile(r"^([A-Z]{1,4})([1-9][0-9]{0,6})$")


class AIWorkbookRecognitionSourceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, max_length=255)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    detected_format: Literal["XLSX", "XLSM"]


class AIWorkbookRecognitionCellV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_ref: str = Field(pattern=r"^[A-Z]{1,4}[1-9][0-9]{0,6}$")
    raw_value: str | int | float | bool | None = None
    display_value: str = Field(default="", max_length=240)
    value_kind: Literal[
        "TEXT", "NUMBER", "DATE", "BOOLEAN", "FORMULA", "ERROR", "BLANK"
    ]
    formula: str | None = Field(default=None, max_length=2_000)
    formula_cache_status: Literal["NOT_FORMULA", "PRESENT", "MISSING", "ERROR"]


class AIWorkbookRecognitionRowV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=1, le=1_000_000)
    cells: list[AIWorkbookRecognitionCellV1] = Field(max_length=160)


class AIWorkbookRecognitionHeaderRegionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_row: int = Field(ge=1, le=1_000_000)
    end_row: int = Field(ge=1, le=1_000_000)
    cells: list[AIWorkbookRecognitionCellV1] = Field(max_length=3_200)

    @model_validator(mode="after")
    def valid_row_range(self):
        if self.start_row > self.end_row:
            raise ValueError("表头区域起始行不能晚于结束行")
        return self


class AIWorkbookRecognitionColumnProfileV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(pattern=r"^[A-Z]{1,4}$")
    non_empty_count: int = Field(ge=0, le=1_000_000)
    formula_count: int = Field(ge=0, le=1_000_000)
    formula_cache_missing_count: int = Field(ge=0, le=1_000_000)
    sample_values: list[str] = Field(max_length=6)


class AIWorkbookRecognitionSheetV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    state: Literal["visible", "hidden", "veryHidden"]
    dimension: str = Field(min_length=1, max_length=64)
    max_row: int = Field(ge=1, le=1_000_000)
    max_column: int = Field(ge=1, le=16_384)
    effective_max_row: int = Field(ge=1, le=1_000_000)
    merged_regions: list[str] = Field(max_length=200)
    header_region: AIWorkbookRecognitionHeaderRegionV1
    representative_rows: list[AIWorkbookRecognitionRowV1] = Field(max_length=24)
    column_profiles: list[AIWorkbookRecognitionColumnProfileV1] = Field(
        max_length=1_024
    )


class AIWorkbookRecognitionPacketV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workbook-recognition-packet-v1"] = (
        "workbook-recognition-packet-v1"
    )
    factory_id: str = Field(min_length=1, max_length=64)
    business_date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    untrusted_content: Literal[True] = True
    source: AIWorkbookRecognitionSourceV1
    sheets: list[AIWorkbookRecognitionSheetV1] = Field(min_length=1, max_length=50)
    packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AIInjectionPlanSheetLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet_name: str = Field(min_length=1, max_length=128)
    header_rows: list[int] = Field(min_length=1, max_length=20)
    data_start_row: int = Field(ge=1, le=1_000_000)
    data_end_row: int = Field(ge=1, le=1_000_000)

    @model_validator(mode="after")
    def valid_rows(self):
        if len(self.header_rows) != len(set(self.header_rows)):
            raise ValueError("表头行不能重复")
        if self.data_start_row > self.data_end_row:
            raise ValueError("数据起始行不能晚于结束行")
        if max(self.header_rows) >= self.data_start_row:
            raise ValueError("表头行必须早于数据起始行")
        return self


class AIInjectionPlanFieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_field: str = Field(min_length=1, max_length=128)
    source_column: str = Field(pattern=r"^[A-Z]{1,4}$")
    header_cell: str = Field(pattern=r"^[A-Z]{1,4}[1-9][0-9]{0,6}$")
    transformer: Literal[
        "trim", "identifier", "number", "date", "datetime", "percent", "text"
    ]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("canonical_field")
    @classmethod
    def known_canonical_field(cls, value: str) -> str:
        if value not in AI_INJECTION_PLAN_CANONICAL_FIELDS:
            raise ValueError("布局包含未批准的规范字段")
        return value

    @model_validator(mode="after")
    def header_column_matches(self):
        match = _CELL_REF_PATTERN.fullmatch(self.header_cell)
        if match is None or match.group(1) != self.source_column:
            raise ValueError("header_cell 必须位于 source_column")
        return self


class AIInjectionPlanRowLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_type: Literal["GROUPED_BY_MACHINE", "FLAT_ROWS"]
    machine_code_strategy: Literal[
        "CURRENT_ROW", "INHERIT_FROM_HEADER", "CURRENT_OR_INHERITED"
    ]
    machine_header_rule: Literal[
        "SAME_VALUE_IN_TWO_COLUMNS", "MACHINE_CODE_WITHOUT_BUSINESS_IDENTITY", "NONE"
    ]
    machine_header_columns: list[str] = Field(max_length=2)
    task_identity_fields: list[str] = Field(min_length=1, max_length=5)
    backlog_rule: Literal[
        "BUSINESS_ROW_WITHOUT_MACHINE", "EXPLICIT_BACKLOG_SECTION", "NONE"
    ]

    @field_validator("machine_header_columns")
    @classmethod
    def valid_machine_columns(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            re.fullmatch(r"[A-Z]{1,4}", value) is None for value in values
        ):
            raise ValueError("机台标题列必须是唯一的 Excel 列")
        return values

    @field_validator("task_identity_fields")
    @classmethod
    def valid_identity_fields(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            value not in AI_INJECTION_PLAN_CANONICAL_FIELDS for value in values
        ):
            raise ValueError("任务身份字段必须来自受控规范字段")
        return values

    @model_validator(mode="after")
    def valid_header_rule(self):
        if self.layout_type == "FLAT_ROWS" and self.machine_header_rule != "NONE":
            raise ValueError("FLAT_ROWS 不允许机台标题规则")
        if (
            self.machine_header_rule == "SAME_VALUE_IN_TWO_COLUMNS"
            and len(self.machine_header_columns) != 2
        ):
            raise ValueError("双列相等规则必须提供两列")
        if self.machine_header_rule == "NONE" and self.machine_header_columns:
            raise ValueError("NONE 规则不能提供机台标题列")
        return self


class AIInjectionPlanShiftGrid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    start_column: str = Field(default="", max_length=4)
    end_column: str = Field(default="", max_length=4)
    day_header_row: int | None = Field(default=None, ge=1, le=1_000_000)
    shift_header_row: int | None = Field(default=None, ge=1, le=1_000_000)
    calendar_month: str = Field(default="", pattern=r"^$|^[0-9]{4}-[0-9]{2}$")
    day_shift_aliases: dict[str, Literal["DAY", "NIGHT"]] = Field(max_length=12)
    quantity_semantics: Literal[
        "COMPLETED_OR_PLANNED_OUTPUT", "COMPLETED_OUTPUT", "PLANNED_OUTPUT"
    ]

    @model_validator(mode="after")
    def valid_grid(self):
        if self.enabled:
            if (
                re.fullmatch(r"[A-Z]{1,4}", self.start_column) is None
                or re.fullmatch(r"[A-Z]{1,4}", self.end_column) is None
                or self.day_header_row is None
                or self.shift_header_row is None
                or not self.calendar_month
            ):
                raise ValueError("启用班次矩阵时必须提供完整边界")
            if not self.day_shift_aliases:
                raise ValueError("启用班次矩阵时必须提供受控班次别名")
        elif self.start_column or self.end_column:
            raise ValueError("未启用班次矩阵时不能提供列边界")
        return self


class AIModelInjectionPlanLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["injection-plan-layout-recognition-v1"] = (
        "injection-plan-layout-recognition-v1"
    )
    document_kind: Literal["PLANNED_SCHEDULE"] = "PLANNED_SCHEDULE"
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sheet: AIInjectionPlanSheetLayout
    row_layout: AIInjectionPlanRowLayout
    field_mappings: list[AIInjectionPlanFieldMapping] = Field(
        min_length=7, max_length=100
    )
    shift_grid: AIInjectionPlanShiftGrid
    warnings: list[str] = Field(max_length=30)
    overall_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def unique_and_complete_mappings(self):
        targets = [item.canonical_field for item in self.field_mappings]
        sources = [item.source_column for item in self.field_mappings]
        if len(targets) != len(set(targets)):
            raise ValueError("规范字段不能重复映射")
        if len(sources) != len(set(sources)):
            raise ValueError("来源列不能重复映射")
        missing = AI_INJECTION_PLAN_REQUIRED_FIELDS - set(targets)
        if missing:
            raise ValueError(f"布局缺少必填字段: {','.join(sorted(missing))}")
        if not set(self.row_layout.task_identity_fields) <= set(targets):
            raise ValueError("任务身份字段必须已完成字段映射")
        return self


class AIInjectionPlanLayoutRecognitionV1(AIModelInjectionPlanLayout):
    generated_by_model: str = Field(min_length=1, max_length=128)
    prompt_version: Literal["injection-plan-layout-v1"] = "injection-plan-layout-v1"
    layout_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


AI_INJECTION_DEMAND_REQUIRED_FIELDS = frozenset(
    {"source_mold_no", "product_name", "order_quantity"}
)


class AIInjectionWorkbookSheetLayoutV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet_name: str = Field(min_length=1, max_length=128)
    header_rows: list[int] = Field(min_length=1, max_length=20)
    data_start_row: int = Field(ge=1, le=1_000_000)
    data_end_row: int = Field(ge=1, le=1_000_000)

    @model_validator(mode="after")
    def valid_rows(self):
        if len(self.header_rows) != len(set(self.header_rows)):
            raise ValueError("表头行不能重复")
        if self.data_start_row > self.data_end_row:
            raise ValueError("数据起始行不能晚于结束行")
        if max(self.header_rows) >= self.data_start_row:
            raise ValueError("表头行必须早于数据起始行")
        return self


class AIInjectionWorkbookTerminationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal[
        "END_OF_USED_RANGE", "FIRST_FOOTER_LABEL", "EMPTY_IDENTITY_STREAK"
    ] = "END_OF_USED_RANGE"
    footer_labels: list[str] = Field(default_factory=list, max_length=20)
    empty_identity_streak: int = Field(default=5, ge=1, le=100)

    @model_validator(mode="after")
    def valid_footer_mode(self):
        if self.mode == "FIRST_FOOTER_LABEL" and not self.footer_labels:
            raise ValueError("FIRST_FOOTER_LABEL 必须提供页脚标签")
        return self


class AIInjectionWorkbookRowLayoutV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_type: Literal["GROUPED_BY_MACHINE", "FLAT_ROWS"]
    machine_code_strategy: Literal[
        "NONE", "CURRENT_ROW", "INHERIT_FROM_HEADER", "CURRENT_OR_INHERITED"
    ]
    machine_header_rule: Literal[
        "NONE", "SAME_VALUE_IN_TWO_COLUMNS", "MACHINE_CODE_WITHOUT_BUSINESS_IDENTITY"
    ]
    machine_header_columns: list[str] = Field(default_factory=list, max_length=2)
    task_identity_fields: list[str] = Field(min_length=1, max_length=8)
    backlog_rule: Literal[
        "NONE", "BUSINESS_ROW_WITHOUT_MACHINE", "EXPLICIT_BACKLOG_SECTION"
    ] = "NONE"
    termination: AIInjectionWorkbookTerminationV1 = Field(
        default_factory=AIInjectionWorkbookTerminationV1
    )

    @field_validator("machine_header_columns")
    @classmethod
    def valid_machine_columns(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            re.fullmatch(r"[A-Z]{1,4}", value) is None for value in values
        ):
            raise ValueError("机台标题列必须是唯一的 Excel 列")
        return values

    @field_validator("task_identity_fields")
    @classmethod
    def valid_identity_fields(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            value not in CANONICAL_FIELD_NAMES for value in values
        ):
            raise ValueError("业务身份字段必须来自受控规范字段")
        return values

    @model_validator(mode="after")
    def valid_machine_contract(self):
        if self.machine_code_strategy == "NONE" and (
            self.machine_header_rule != "NONE" or self.machine_header_columns
        ):
            raise ValueError("无机台策略不能声明机台标题规则")
        if self.layout_type == "FLAT_ROWS" and self.machine_header_rule != "NONE":
            raise ValueError("FLAT_ROWS 不允许机台标题规则")
        if (
            self.machine_header_rule == "SAME_VALUE_IN_TWO_COLUMNS"
            and len(self.machine_header_columns) != 2
        ):
            raise ValueError("双列相等规则必须提供两列")
        if self.machine_header_rule == "NONE" and self.machine_header_columns:
            raise ValueError("NONE 规则不能提供机台标题列")
        return self


CANONICAL_FIELD_NAMES = frozenset(
    {
        *AI_INJECTION_PLAN_CANONICAL_FIELDS,
        "customer_name",
        "source_document_no",
        "source_mold_no",
        "product_group_no",
        "required_shots",
        "source_daily_capacity",
        "total_gross_weight",
        "total_net_weight",
        "source_mold_return_due",
    }
)


class AIInjectionWorkbookFieldMappingV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_field: str = Field(min_length=1, max_length=128)
    source_column: str = Field(pattern=r"^[A-Z]{1,4}$")
    header_cell: str = Field(pattern=r"^[A-Z]{1,4}[1-9][0-9]{0,6}$")
    transformer: Literal[
        "trim", "identifier", "number", "date", "datetime", "percent", "text"
    ]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("canonical_field")
    @classmethod
    def known_canonical_field(cls, value: str) -> str:
        if value not in CANONICAL_FIELD_NAMES:
            raise ValueError("映射包含未批准的规范字段")
        return value

    @model_validator(mode="after")
    def header_column_matches(self):
        match = _CELL_REF_PATTERN.fullmatch(self.header_cell)
        if match is None or match.group(1) != self.source_column:
            raise ValueError("header_cell 必须位于 source_column")
        return self


class AIInjectionWorkbookMetadataAnchorV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_field: str = Field(min_length=1, max_length=128)
    label_cell: str = Field(pattern=r"^[A-Z]{1,4}[1-9][0-9]{0,6}$")
    value_cell: str = Field(pattern=r"^[A-Z]{1,4}[1-9][0-9]{0,6}$")
    transformer: Literal[
        "trim", "identifier", "number", "date", "datetime", "percent", "text"
    ]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("canonical_field")
    @classmethod
    def known_canonical_field(cls, value: str) -> str:
        if value not in CANONICAL_FIELD_NAMES:
            raise ValueError("元数据锚点包含未批准的规范字段")
        return value


class AIInjectionWorkbookShiftGridV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    start_column: str = Field(default="", max_length=4)
    end_column: str = Field(default="", max_length=4)
    date_header_row: int | None = Field(default=None, ge=1, le=1_000_000)
    shift_header_row: int | None = Field(default=None, ge=1, le=1_000_000)
    date_header_mode: Literal["NONE", "DAY_OF_MONTH", "EXCEL_DATE", "MIXED"] = "NONE"
    day_shift_aliases: dict[str, Literal["DAY", "NIGHT"]] = Field(
        default_factory=dict, max_length=12
    )
    quantity_semantics: Literal["COMPLETED_OUTPUT"] = "COMPLETED_OUTPUT"

    @model_validator(mode="after")
    def valid_grid(self):
        if self.enabled:
            if (
                re.fullmatch(r"[A-Z]{1,4}", self.start_column) is None
                or re.fullmatch(r"[A-Z]{1,4}", self.end_column) is None
                or self.date_header_row is None
                or self.shift_header_row is None
                or self.date_header_mode == "NONE"
                or not self.day_shift_aliases
            ):
                raise ValueError("启用班次矩阵时必须提供完整边界")
        elif (
            self.start_column
            or self.end_column
            or self.date_header_row is not None
            or self.shift_header_row is not None
            or self.date_header_mode != "NONE"
            or self.day_shift_aliases
        ):
            raise ValueError("未启用班次矩阵时不能提供矩阵边界")
        return self


class AIModelInjectionWorkbookMappingV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["injection-workbook-mapping-v1"] = (
        "injection-workbook-mapping-v1"
    )
    document_kind: Literal["DEMAND_ORDER", "PLANNED_SCHEDULE"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sheet: AIInjectionWorkbookSheetLayoutV1
    row_layout: AIInjectionWorkbookRowLayoutV1
    field_mappings: list[AIInjectionWorkbookFieldMappingV1] = Field(
        min_length=3, max_length=100
    )
    metadata_anchors: list[AIInjectionWorkbookMetadataAnchorV1] = Field(
        default_factory=list, max_length=20
    )
    shift_grid: AIInjectionWorkbookShiftGridV1
    warnings: list[str] = Field(default_factory=list, max_length=30)
    overall_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_document_contract(self):
        targets = [item.canonical_field for item in self.field_mappings]
        sources = [item.source_column for item in self.field_mappings]
        anchor_targets = [item.canonical_field for item in self.metadata_anchors]
        if len(targets) != len(set(targets)):
            raise ValueError("规范字段不能重复映射")
        if len(sources) != len(set(sources)):
            raise ValueError("来源列不能重复映射")
        if len(anchor_targets) != len(set(anchor_targets)):
            raise ValueError("元数据锚点不能重复")
        if not set(self.row_layout.task_identity_fields) <= set(targets):
            raise ValueError("业务身份字段必须已完成字段映射")
        if self.document_kind == "DEMAND_ORDER":
            if (
                self.row_layout.machine_code_strategy != "NONE"
                or self.row_layout.machine_header_rule != "NONE"
                or self.shift_grid.enabled
            ):
                raise ValueError("需求单不能声明机台继承或班次矩阵")
            missing = AI_INJECTION_DEMAND_REQUIRED_FIELDS - set(targets)
        else:
            if self.row_layout.machine_code_strategy == "NONE":
                raise ValueError("计划表必须声明机台读取策略")
            missing = AI_INJECTION_PLAN_REQUIRED_FIELDS - set(targets)
        if missing:
            raise ValueError(f"布局缺少必填字段: {','.join(sorted(missing))}")
        return self


class AIInjectionWorkbookMappingV1(AIModelInjectionWorkbookMappingV1):
    generated_by_model: str = Field(min_length=1, max_length=128)
    skill_id: Literal["injection_scheduling.workbook_mapping"] = (
        "injection_scheduling.workbook_mapping"
    )
    skill_version: Literal["1.0.0"] = "1.0.0"
    prompt_version: Literal["1.0.0"] = "1.0.0"
    mapping_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
