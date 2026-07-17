from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


InitiatorDepartment = Literal["sales-business", "engineering"]
ReviewDecision = Literal["approve", "reject"]
InternalQuoteImportType = Literal["mold", "electronic", "painting", "sewing", "assembly"]


class InternalQuoteCreateRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    workshop_code: str = Field(default="huaxing-workshop", min_length=1, max_length=64)
    workshop_name: str = Field(default="华兴", min_length=1, max_length=128)
    quote_no: str = Field(min_length=1, max_length=128)
    product_name: str = Field(min_length=1, max_length=255)
    customer: str = Field(min_length=1, max_length=128)
    qty: int = Field(gt=0)
    version_label: str = Field(default="V1", min_length=1, max_length=64)
    initiator_department: InitiatorDepartment
    business_owner_id: str = Field(min_length=1, max_length=64)
    business_owner_name: str = Field(min_length=1, max_length=128)
    target_date: str = Field(default="", max_length=32)
    remark: str = Field(default="", max_length=4000)

    @field_validator(
        "factory_id",
        "workshop_code",
        "workshop_name",
        "quote_no",
        "product_name",
        "customer",
        "version_label",
        "business_owner_id",
        "business_owner_name",
        "target_date",
        "remark",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class InternalQuoteBusinessOwnerOut(BaseModel):
    id: str
    username: str
    display_name: str


class InternalQuoteCloneRequest(BaseModel):
    quote_no: str = Field(min_length=1, max_length=128)
    version_label: str = Field(min_length=1, max_length=64)
    business_owner_id: str = Field(min_length=1, max_length=64)
    business_owner_name: str = Field(min_length=1, max_length=128)
    target_date: str = Field(default="", max_length=32)
    remark: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "quote_no",
        "version_label",
        "business_owner_id",
        "business_owner_name",
        "target_date",
        "remark",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class InternalQuoteHeaderUpdateRequest(BaseModel):
    revision: int = Field(ge=1)
    product_name: str | None = Field(default=None, min_length=1, max_length=255)
    customer: str | None = Field(default=None, min_length=1, max_length=128)
    qty: int | None = Field(default=None, gt=0)
    business_owner_id: str | None = Field(default=None, min_length=1, max_length=64)
    business_owner_name: str | None = Field(default=None, min_length=1, max_length=128)
    target_date: str | None = Field(default=None, max_length=32)
    remark: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "product_name",
        "customer",
        "business_owner_id",
        "business_owner_name",
        "target_date",
        "remark",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_change(self):
        fields = self.model_dump(exclude={"revision"}, exclude_none=True)
        if not fields:
            raise ValueError("至少提交一个需要修改的字段")
        if (self.business_owner_id is None) != (self.business_owner_name is None):
            raise ValueError("业务负责人编号和姓名必须同时提交")
        return self


class InternalQuoteSectionSaveRequest(BaseModel):
    revision: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InternalQuoteRevisionRequest(BaseModel):
    revision: int = Field(ge=1)


class InternalQuoteReviewRequest(InternalQuoteRevisionRequest):
    decision: ReviewDecision
    reason: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_rejection_reason(self):
        if self.decision == "reject" and not self.reason:
            raise ValueError("退回时必须填写原因")
        return self


class InternalQuoteFinalReviewRequest(InternalQuoteRevisionRequest):
    decision: ReviewDecision
    reason: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_rejection_reason(self):
        if self.decision == "reject" and not self.reason:
            raise ValueError("最终放行退回时必须填写原因")
        return self


class InternalQuoteReasonRequest(InternalQuoteRevisionRequest):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InternalQuoteArchiveRequest(BaseModel):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InternalQuoteReferenceSyncRequest(BaseModel):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InternalQuoteSectionOut(BaseModel):
    id: str
    department: str
    department_name: str
    status: str
    payload: dict[str, Any]
    calculation: dict[str, Any]
    calculation_status: str
    calculation_hash: str
    calculation_formula_version: str
    calculation_reference_snapshot_id: str
    calculated_at: str
    dependency_hash: str
    dependency_status: str
    revision: int
    is_required: bool
    filled_by: str
    filled_at: str
    submitted_by: str
    submitted_by_id: str
    submitted_at: str
    reviewed_by: str
    reviewed_at: str
    review_comment: str
    updated_at: str


class InternalQuoteOut(BaseModel):
    id: str
    factory_id: str
    workshop_code: str
    workshop_name: str
    quote_no: str
    product_name: str
    customer: str
    qty: int
    version_label: str
    status: str
    initiator_department: str
    business_owner_id: str
    business_owner_name: str
    target_date: str
    remark: str
    module_version: str
    reference_snapshot_id: str
    formula_version: str
    header_revision: int
    cloned_from_quote_id: str
    archived_by: str
    archived_at: str
    archive_reason: str
    final_release_status: str
    final_submission_revision: int
    final_submission_manifest: dict[str, Any]
    final_submitted_by: str
    final_submitted_by_name: str
    final_submitted_at: str
    final_reviewed_by: str
    final_reviewed_by_name: str
    final_reviewed_at: str
    final_review_comment: str
    final_release_revision: int
    final_release_invalidated_at: str
    final_release_invalidation_reason: str
    created_by: str
    created_by_name: str
    created_at: str
    updated_at: str
    sections: list[InternalQuoteSectionOut] = Field(default_factory=list)


class InternalQuoteRevisionOut(BaseModel):
    id: str
    revision: int
    status: str
    payload: dict[str, Any]
    calculation: dict[str, Any]
    formula_version: str
    input_hash: str
    reference_snapshot_id: str
    dependency_hash: str
    warnings: list[dict[str, Any]]
    reason: str
    created_by: str
    created_by_name: str
    created_at: str


class InternalQuoteAuditOut(BaseModel):
    id: str
    department: str
    actor_id: str
    actor_name: str
    action: str
    detail: str
    old_revision: int | None
    new_revision: int | None
    reason: str
    created_at: str


class InternalQuoteTimelineOut(BaseModel):
    business_events: list[InternalQuoteAuditOut]
    view_records: list[InternalQuoteAuditOut]


class InternalQuoteReferenceSetOut(BaseModel):
    id: str
    quote_id: str
    factory_id: str
    version_label: str
    formula_version: str
    source_type: str
    source_revision: int
    snapshot: dict[str, Any]
    sha256: str
    is_current: bool
    created_by: str
    created_by_name: str
    created_at: str
    superseded_at: str


class InternalQuoteImportConfirmRequest(BaseModel):
    revision: int = Field(ge=1)
    mode: Literal["append", "replace"] = "append"


class InternalQuoteImportPreviewOut(BaseModel):
    batch_id: str
    quote_id: str
    import_type: InternalQuoteImportType
    target_department: str
    source_file_name: str
    source_sha256: str
    source_size_bytes: int
    preview_schema_version: str
    target_revision: int
    sheet_name: str
    header_row: int
    row_count: int
    payload_fragment: dict[str, Any]
    diff_summary: dict[str, Any]
    warnings: list[str]
    status: str
    created_by_name: str
    created_at: str
    confirm_mode: str = ""
    confirmed_revision: int = 0
    confirmed_by_name: str = ""
    confirmed_at: str = ""


class InternalQuoteImportConfirmOut(BaseModel):
    batch: InternalQuoteImportPreviewOut
    section: InternalQuoteSectionOut


class InternalQuoteAttachmentOut(BaseModel):
    id: str
    quote_id: str
    department: str
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: str
    uploaded_by_name: str
    uploaded_at: str


class InternalQuoteExportFileOut(BaseModel):
    id: str
    quote_id: str
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    section_revisions: dict[str, int]
    status: str
    template_version: str
    formula_version: str
    reference_snapshot_id: str
    header_revision: int
    release_stage: str
    export_manifest: dict[str, Any]
    exported_by: str
    exported_by_name: str
    exported_at: str
    superseded_at: str


class InternalQuoteFinalReviewOut(BaseModel):
    id: str
    quote_id: str
    submission_revision: int
    decision: str
    header_revision: int
    section_revisions: dict[str, int]
    release_manifest: dict[str, Any]
    release_manifest_sha256: str
    submitted_by: str
    submitted_by_name: str
    submitted_at: str
    actor_id: str
    actor_name: str
    reason: str
    created_at: str


class InternalQuoteFinalReleaseOut(BaseModel):
    quote: InternalQuoteOut
    review: InternalQuoteFinalReviewOut | None = None
    export: InternalQuoteExportFileOut | None = None


class InternalQuoteVersionCandidateOut(BaseModel):
    id: str
    quote_no: str
    version_label: str
    product_name: str
    customer: str
    status: str
    final_release_status: str
    final_release_revision: int
    updated_at: str


class InternalQuoteFieldChangeOut(BaseModel):
    path: str
    before: Any = None
    after: Any = None


class InternalQuoteSectionComparisonOut(BaseModel):
    section_code: str
    section_name: str
    before_status: str
    after_status: str
    before_revision: int
    after_revision: int
    before_total_hkd: str
    after_total_hkd: str
    delta_hkd: str
    payload_changes: list[InternalQuoteFieldChangeOut]


class InternalQuoteVersionComparisonOut(BaseModel):
    base: InternalQuoteVersionCandidateOut
    target: InternalQuoteVersionCandidateOut
    header_changes: list[InternalQuoteFieldChangeOut]
    sections: list[InternalQuoteSectionComparisonOut]
    total_before_hkd: str
    total_after_hkd: str
    total_delta_hkd: str


class InternalQuoteArtifactConsumeRequest(BaseModel):
    consumer_reference: str = Field(default="", max_length=128)

    @field_validator("consumer_reference")
    @classmethod
    def strip_reference(cls, value: str) -> str:
        return value.strip()


class InternalQuoteArtifactHandoffOut(BaseModel):
    id: str
    quote_id: str
    export_id: str
    factory_id: str
    customer: str
    quote_no: str
    version_label: str
    release_revision: int
    status: str
    artifact_manifest: dict[str, Any]
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_by: str
    created_by_name: str
    created_at: str
    consumed_by: str
    consumed_by_name: str
    consumed_at: str
    consumer_reference: str
    revoked_at: str
    revoke_reason: str
