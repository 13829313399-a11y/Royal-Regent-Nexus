from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictWriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InjectionSchedulingImportIssueOut(BaseModel):
    id: str
    severity: Literal["ERROR", "WARNING"]
    code: str
    message: str
    sheet_name: str
    source_row: int | None
    field_name: str
    cell_ref: str
    raw_value: str
    formula_text: str
    blocking: bool


class InjectionSchedulingImportTaskPreview(BaseModel):
    machine_code: str
    sequence_no: int
    execution_status: str
    status_inferred: bool
    legacy_marker: str
    mold_no: str
    product_name: str
    order_no: str
    item_no: str
    order_quantity: float | None
    completed_quantity: float | None
    shift_target_quantity: float
    delivery_due_date: str
    planned_start: str
    planned_finish: str
    priority_code: str
    source: dict[str, Any]


class InjectionSchedulingImportBatchOut(BaseModel):
    id: str
    factory_id: str
    source_file_name: str
    source_file_hash: str
    source_size_bytes: int
    parser_version: str
    preview_schema_version: str
    normalized_sha256: str
    batch_state: str
    profile: dict[str, Any] | None
    sheet_roles: list[dict[str, Any]]
    mapping: list[dict[str, Any]]
    mapping_fingerprint: str
    scheduled_baseline_tasks: list[dict[str, Any]]
    backlog_orders: list[dict[str, Any]]
    invalid_rows: list[dict[str, Any]]
    master_differences: list[dict[str, Any]]
    calculation_comparisons: list[dict[str, Any]]
    reconciliation_actions: list[dict[str, Any]]
    plan_context: dict[str, Any]
    action_fingerprint: str
    summary: dict[str, Any]
    status: Literal["PREVIEW", "CONFIRMED"]
    revision: int
    preview_request_id: str
    confirm_request_id: str | None
    confirm_mode: str
    confirmed_plan_id: str
    confirmed_plan_revision: int
    result: dict[str, Any]
    created_by: str
    created_by_name: str
    created_at: str
    confirmed_by: str
    confirmed_by_name: str
    confirmed_at: str
    issues: list[InjectionSchedulingImportIssueOut]
    tasks: list[InjectionSchedulingImportTaskPreview]
    idempotent_replay: bool = False


class InjectionSchedulingImportConfirm(StrictWriteModel):
    factory_id: str
    expected_revision: int = Field(ge=1)
    expected_plan_revision: int = Field(ge=0)
    request_id: str = Field(min_length=8, max_length=128)
    confirm_mode: Literal["create_draft", "merge_draft"]
    business_date: date
    acknowledged_blocking_issue_ids: list[str] = Field(default_factory=list)
    expected_action_fingerprint: str = Field(default="", max_length=64)
    action_reasons: dict[str, str] = Field(default_factory=dict)

    @field_validator("factory_id", "request_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("acknowledged_blocking_issue_ids")
    @classmethod
    def normalize_issue_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("确认的问题 ID 不能重复")
        return normalized

    @model_validator(mode="after")
    def validate_plan_revision_mode(self):
        if self.confirm_mode == "create_draft" and self.expected_plan_revision != 0:
            raise ValueError("创建新草案时 expected_plan_revision 必须为 0")
        if self.confirm_mode == "merge_draft" and self.expected_plan_revision < 1:
            raise ValueError("合并草案时 expected_plan_revision 必须大于 0")
        return self

    @field_validator("expected_action_fingerprint")
    @classmethod
    def strip_fingerprint(cls, value: str) -> str:
        return value.strip()

    @field_validator("action_reasons")
    @classmethod
    def validate_action_reasons(cls, values: dict[str, str]) -> dict[str, str]:
        normalized = {key.strip(): value.strip() for key, value in values.items()}
        if any(not key or not 4 <= len(value) <= 500 for key, value in normalized.items()):
            raise ValueError("受限对账动作原因必须为 4～500 个字符")
        return normalized


class InjectionSchedulingMasterApproval(StrictWriteModel):
    factory_id: str
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=4, max_length=500)
    differences: list[str] = Field(min_length=1, max_length=500)

    @field_validator("factory_id", "request_id", "reason")
    @classmethod
    def strip_approval_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("differences")
    @classmethod
    def normalize_differences(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(values) or len(normalized) != len(set(normalized)):
            raise ValueError("主数据差异键不能为空或重复")
        return normalized
