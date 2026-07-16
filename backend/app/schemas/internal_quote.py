from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


InternalQuoteStatus = Literal["drafting", "fully_approved", "exported", "reopened", "archived"]
InternalQuoteSectionStatus = Literal["draft", "pending_review", "approved", "rejected"]
InternalQuoteDepartment = Literal[
    "sales",
    "engineering",
    "electronic",
    "molding",
    "painting",
    "slush",
    "sewing",
    "assembly",
]
InternalQuoteImportType = Literal["mold", "electronic", "sewing", "assembly", "painting"]


class InternalQuoteWorkshopOut(BaseModel):
    code: str
    name: str


class InternalQuoteCostLine(BaseModel):
    id: str = Field(default="", max_length=64)
    category: str = Field(default="", max_length=128)
    item_name: str = Field(default="", max_length=255)
    specification: str = Field(default="", max_length=255)
    quantity: float = Field(default=0, ge=0)
    unit_price_hkd: float = Field(default=0, ge=0)
    amount_hkd: float = Field(default=0, ge=0)
    note: str = Field(default="", max_length=500)
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "category", "item_name", "specification", "note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class InternalQuoteSectionPayload(BaseModel):
    currency: Literal["HKD"] = "HKD"
    loss_pct: float = Field(default=0, ge=0, le=100)
    parameters: dict[str, Any] = Field(default_factory=dict)
    reference_snapshot: dict[str, Any] = Field(default_factory=dict)
    rows: list[InternalQuoteCostLine] = Field(default_factory=list, max_length=300)


class InternalQuoteCreateRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    workshop_code: str = Field(min_length=1, max_length=64)
    quote_no: str = Field(min_length=1, max_length=128)
    product_name: str = Field(min_length=1, max_length=255)
    customer: str = Field(min_length=1, max_length=128)
    qty: int = Field(gt=0)
    version_label: str = Field(default="V1", min_length=1, max_length=64)

    @field_validator(
        "factory_id",
        "workshop_code",
        "quote_no",
        "product_name",
        "customer",
        "version_label",
        mode="before",
    )
    @classmethod
    def strip_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class InternalQuoteSectionUpdateRequest(BaseModel):
    revision: int = Field(ge=1)
    payload: InternalQuoteSectionPayload
    submit: bool = False


class InternalQuoteReviewRequest(BaseModel):
    action: Literal["approve", "reject", "reopen"]
    comment: str = Field(default="", max_length=500)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, value: str) -> str:
        return value.strip()


class InternalQuoteImportConfirmRequest(BaseModel):
    revision: int = Field(ge=1)
    mode: Literal["append", "replace"] = "append"


class InternalQuoteImportPreviewOut(BaseModel):
    batch_id: str
    quote_id: str
    import_type: InternalQuoteImportType
    target_department: InternalQuoteDepartment
    source_file_name: str
    source_sha256: str
    sheet_name: str
    header_row: int
    rows: list[InternalQuoteCostLine]
    parameters: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    status: Literal["previewed", "confirmed"]
    created_by_name: str
    created_at: str
    confirmed_by_name: str = ""
    confirmed_at: str = ""


class InternalQuoteAttachmentOut(BaseModel):
    id: str
    quote_id: str
    department: str
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
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
    status: Literal["current", "superseded"]
    exported_by_name: str
    exported_at: str
    superseded_at: str


class InternalQuoteLineCalculationOut(BaseModel):
    line_id: str
    label: str
    formula: str
    amount_hkd: float


class InternalQuoteSectionCalculationOut(BaseModel):
    formula_version: str = "p1-generic-v1"
    subtotal_hkd: float = 0
    loss_amount_hkd: float = 0
    total_hkd: float = 0
    total_rmb: float = 0
    total_usd: float = 0
    line_breakdown: list[InternalQuoteLineCalculationOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reference_snapshot: dict[str, Any] = Field(default_factory=dict)


class InternalQuoteSectionOut(BaseModel):
    id: str
    quote_id: str
    department: InternalQuoteDepartment
    department_name: str
    status: InternalQuoteSectionStatus
    payload: InternalQuoteSectionPayload
    calculation: InternalQuoteSectionCalculationOut
    revision: int
    filled_by: str
    filled_at: str
    submitted_by: str
    submitted_at: str
    reviewed_by: str
    reviewed_at: str
    review_comment: str
    updated_at: str


class InternalQuoteAuditOut(BaseModel):
    id: str
    quote_id: str
    department: str
    actor_id: str
    actor_name: str
    action: str
    detail: str
    created_at: str


class InternalQuoteSummaryOut(BaseModel):
    id: str
    factory_id: str
    workshop_code: str
    workshop_name: str
    quote_no: str
    product_name: str
    customer: str
    qty: int
    version_label: str
    status: InternalQuoteStatus
    approved_count: int
    total_sections: int
    total_hkd: float
    created_by: str
    created_by_name: str
    created_at: str
    updated_at: str


class InternalQuoteDetailOut(InternalQuoteSummaryOut):
    sections: list[InternalQuoteSectionOut]
    audit_logs: list[InternalQuoteAuditOut]
