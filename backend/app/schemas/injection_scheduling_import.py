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
