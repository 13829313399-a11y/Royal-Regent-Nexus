from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AIWorkbookSourceLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file_name: str = Field(min_length=1, max_length=255)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(gt=0)
    detected_format: Literal["XLSX", "XLSM"]
    inspector_version: Literal["workbook-semantic-snapshot-v1"]


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
