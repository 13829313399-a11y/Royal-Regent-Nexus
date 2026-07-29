from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class InjectionSchedulingImportIssueOut(BaseModel):
    id: str
    severity: Literal["blocker", "warning"]
    code: str
    message: str
    sheet_name: str = ""
    source_row: int = 0
    field: str = ""
    source_value: str = ""


class InjectionSchedulingImportPreviewOut(BaseModel):
    batch_id: str
    factory_id: str
    source_file_name: str
    source_sha256: str
    business_date: str
    parser_version: str
    preview_revision: int
    status: str
    summary: dict[str, Any]
    issues: list[InjectionSchedulingImportIssueOut]
    created_at: str


class InjectionSchedulingImportConfirmRequest(BaseModel):
    factory_id: str
    preview_revision: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=1000)

    @field_validator("factory_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingImportConfirmOut(BaseModel):
    batch_id: str
    factory_id: str
    plan_id: str
    revision: int
    confirmed_at: str
    summary: dict[str, Any]
    snapshot: dict[str, Any]


class InjectionSchedulingMoveValidationRequest(BaseModel):
    factory_id: str
    revision: int = Field(ge=1)
    task_id: str | None = None
    backlog_id: str | None = None
    source_machine_id: str | None = None
    target_machine_id: str
    target_index: int | None = Field(default=None, ge=0)


class InjectionSchedulingMoveValidationOut(BaseModel):
    allowed: bool
    eligibility: dict[str, Any] | None = None
    reasons: list[str]
    affected_task_count: int


class InjectionSchedulingDraftSaveRequest(BaseModel):
    factory_id: str
    revision: int = Field(ge=1)
    snapshot: dict[str, Any]
    reason: str = Field(min_length=2, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingDraftSaveOut(BaseModel):
    plan_id: str
    revision: int
    saved_at: str
    snapshot_sha256: str


class InjectionSchedulingPublishRequest(BaseModel):
    factory_id: str
    revision: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingPublishOut(BaseModel):
    plan_id: str
    version: str
    plan_revision: int
    published_at: str
    snapshot_sha256: str


class InjectionSchedulingRollbackRequest(BaseModel):
    factory_id: str
    version: str
    revision: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=1000)

    @field_validator("version", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class InjectionSchedulingRollbackOut(BaseModel):
    plan_id: str
    revision: int
    rolled_back_from_version: str
    saved_at: str
    snapshot: dict[str, Any]


class InjectionSchedulingPlanEnvelope(BaseModel):
    plan_id: str
    factory_id: str
    revision: int
    snapshot: dict[str, Any]


class InjectionSchedulingPublishedEnvelope(BaseModel):
    snapshot_id: str
    plan_id: str
    factory_id: str
    version: str
    plan_revision: int
    published_at: str
    snapshot: dict[str, Any]
