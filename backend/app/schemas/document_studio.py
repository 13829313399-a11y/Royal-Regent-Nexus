from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.services.document_studio.contracts import (
    DOCUMENT_CONTRACT_VERSION,
    MAX_BLOCK_TEXT_CHARS,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_PAGES,
    DocumentBlockKind,
    DocumentCellValueType,
    DocumentExtractionRoute,
    DocumentExtractionSource,
    DocumentJobState,
    DocumentJobType,
    DocumentKind,
    DocumentPageRangeKind,
    DocumentProcessingMode,
    DocumentReviewAction,
    DocumentReviewIssueKind,
    DocumentReviewSeverity,
    DocumentRouteDecision,
)

DocumentContractVersion = Literal["1"]
DocumentArtifactId = Annotated[str, Field(pattern=r"^aiart-[0-9a-f]{32}$")]
DocumentTaskId = Annotated[str, Field(pattern=r"^aitask-[0-9a-f]{32}$")]
DocumentJobId = Annotated[str, Field(pattern=r"^docjob-[0-9a-f]{32}$")]
DocumentOperationId = Annotated[str, Field(pattern=r"^docop-[0-9a-f]{32}$")]
DocumentBBox = Annotated[
    tuple[float, float, float, float],
    Field(description="PDF points: left, top, right, bottom in source-page coordinates."),
]

_HTML_TAG_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


class _ClosedDocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_bbox(value: DocumentBBox) -> DocumentBBox:
    left, top, right, bottom = value
    if min(value) < 0:
        raise ValueError("bbox coordinates must be non-negative")
    if right < left or bottom < top:
        raise ValueError("bbox must use left <= right and top <= bottom")
    if max(value) > 1_000_000:
        raise ValueError("bbox coordinate exceeds the contract limit")
    return value


def _reject_html(value: str) -> str:
    if _HTML_TAG_PATTERN.search(value):
        raise ValueError("HTML markup is not allowed in document contracts")
    return value


class DocumentPageRange(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    kind: DocumentPageRangeKind = DocumentPageRangeKind.ALL
    pages: tuple[int, ...] = Field(default=(), max_length=MAX_DOCUMENT_PAGES)

    @model_validator(mode="after")
    def validate_pages(self) -> DocumentPageRange:
        if self.kind == DocumentPageRangeKind.ALL and self.pages:
            raise ValueError("ALL page ranges must not include explicit pages")
        if self.kind == DocumentPageRangeKind.PAGES and not self.pages:
            raise ValueError("PAGES page ranges require at least one page")
        if any(page < 1 or page > MAX_DOCUMENT_PAGES for page in self.pages):
            raise ValueError("page numbers must be between 1 and 200")
        if tuple(sorted(set(self.pages))) != self.pages:
            raise ValueError("page numbers must be unique and ascending")
        return self


class DocumentPreflightResult(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    source_artifact_id: DocumentArtifactId
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    filename: str = Field(min_length=1, max_length=255)
    detected_mime_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    size_bytes: int = Field(gt=0, le=MAX_DOCUMENT_BYTES)
    page_count: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    native_text_pages: int = Field(default=0, ge=0, le=MAX_DOCUMENT_PAGES)
    scanned_pages: int = Field(default=0, ge=0, le=MAX_DOCUMENT_PAGES)
    route_decision: DocumentRouteDecision
    warnings: tuple[str, ...] = Field(default=(), max_length=50)

    @field_validator("filename", "warnings")
    @classmethod
    def reject_html(cls, value):
        if isinstance(value, tuple):
            return tuple(_reject_html(item) for item in value)
        return _reject_html(value)

    @model_validator(mode="after")
    def validate_page_totals(self) -> DocumentPreflightResult:
        if self.native_text_pages + self.scanned_pages > self.page_count:
            raise ValueError("classified page counts cannot exceed page_count")
        return self


class DocumentBlock(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    block_id: str = Field(pattern=r"^p[1-9][0-9]*-b[1-9][0-9]*$")
    kind: DocumentBlockKind
    bbox: DocumentBBox
    raw_text: str = Field(default="", max_length=MAX_BLOCK_TEXT_CHARS)
    normalized_text: str = Field(default="", max_length=MAX_BLOCK_TEXT_CHARS)
    confidence: float = Field(ge=0, le=1)
    source: DocumentExtractionSource
    needs_review: bool = False

    _bbox_contract = field_validator("bbox")(_validate_bbox)

    @field_validator("raw_text", "normalized_text")
    @classmethod
    def reject_html(cls, value: str) -> str:
        return _reject_html(value)


class DocumentCellEvidence(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    cell_id: str = Field(pattern=r"^table-[1-9][0-9]*-r[1-9][0-9]*-c[1-9][0-9]*$")
    raw_text: str = Field(default="", max_length=10_000)
    normalized_value: str = Field(default="", max_length=10_000)
    value_type: DocumentCellValueType
    confidence: float = Field(ge=0, le=1)
    source_page: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    source_bbox: DocumentBBox
    sources: tuple[DocumentExtractionSource, ...] = Field(min_length=1, max_length=5)
    review_reasons: tuple[DocumentReviewIssueKind, ...] = Field(
        default=(), max_length=10
    )

    _bbox_contract = field_validator("source_bbox")(_validate_bbox)

    @field_validator("raw_text", "normalized_value")
    @classmethod
    def reject_html(cls, value: str) -> str:
        return _reject_html(value)

    @field_validator("sources", "review_reasons")
    @classmethod
    def validate_unique_enums(cls, value: tuple) -> tuple:
        if len(value) != len(set(value)):
            raise ValueError("contract enum lists must be unique")
        return value


class DocumentTable(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    table_id: str = Field(pattern=r"^table-[1-9][0-9]*$")
    page_number: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    bbox: DocumentBBox
    row_count: int = Field(ge=1, le=10_000)
    column_count: int = Field(ge=1, le=1_000)
    cells: tuple[DocumentCellEvidence, ...] = Field(default=(), max_length=50_000)
    confidence: float = Field(ge=0, le=1)

    _bbox_contract = field_validator("bbox")(_validate_bbox)

    @model_validator(mode="after")
    def validate_cells(self) -> DocumentTable:
        if len(self.cells) > self.row_count * self.column_count:
            raise ValueError("cell count cannot exceed the declared table dimensions")
        if any(cell.source_page != self.page_number for cell in self.cells):
            raise ValueError("table cells must reference the table page")
        return self


class DocumentPageSnapshot(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    page_number: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    width: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    rotation: Literal[0, 90, 180, 270] = 0
    extraction_route: DocumentExtractionRoute
    blocks: tuple[DocumentBlock, ...] = Field(default=(), max_length=10_000)
    tables: tuple[DocumentTable, ...] = Field(default=(), max_length=500)

    @model_validator(mode="after")
    def validate_page_references(self) -> DocumentPageSnapshot:
        expected_prefix = f"p{self.page_number}-"
        if any(not block.block_id.startswith(expected_prefix) for block in self.blocks):
            raise ValueError("block ids must match the containing page")
        if any(table.page_number != self.page_number for table in self.tables):
            raise ValueError("table page_number must match the containing page")
        return self


class DocumentSnapshot(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    source_artifact_id: DocumentArtifactId
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(default=1, ge=1, le=10_000)
    page_count: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    document_kind: DocumentKind = DocumentKind.GENERAL
    languages: tuple[str, ...] = Field(default=(), max_length=20)
    pages: tuple[DocumentPageSnapshot, ...] = Field(
        min_length=1, max_length=MAX_DOCUMENT_PAGES
    )
    warnings: tuple[str, ...] = Field(default=(), max_length=100)

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("languages must be unique")
        if any(not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?", item) for item in value):
            raise ValueError("languages must use a BCP-47 style language tag")
        return value

    @field_validator("warnings")
    @classmethod
    def reject_html(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_reject_html(item) for item in value)

    @model_validator(mode="after")
    def validate_pages(self) -> DocumentSnapshot:
        page_numbers = tuple(page.page_number for page in self.pages)
        if len(self.pages) != self.page_count:
            raise ValueError("pages length must equal page_count")
        if page_numbers != tuple(range(1, self.page_count + 1)):
            raise ValueError("snapshot pages must be unique and contiguous from 1")
        return self


class DocumentReviewIssue(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    issue_id: str = Field(pattern=r"^docissue-[0-9a-f]{32}$")
    severity: DocumentReviewSeverity
    kind: DocumentReviewIssueKind
    page_number: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    target_id: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^(?:p[1-9][0-9]*-b[1-9][0-9]*|table-[1-9][0-9]*(?:-r[1-9][0-9]*-c[1-9][0-9]*)?)$",
    )
    original_value: str = Field(default="", max_length=10_000)
    proposed_value: str = Field(default="", max_length=10_000)
    confidence: float = Field(ge=0, le=1)
    message: str = Field(min_length=1, max_length=1_000)
    options: tuple[DocumentReviewAction, ...] = Field(min_length=1, max_length=3)

    @field_validator("original_value", "proposed_value", "message")
    @classmethod
    def reject_html(cls, value: str) -> str:
        return _reject_html(value)

    @field_validator("options")
    @classmethod
    def validate_unique_options(
        cls, value: tuple[DocumentReviewAction, ...]
    ) -> tuple[DocumentReviewAction, ...]:
        if len(value) != len(set(value)):
            raise ValueError("review options must be unique")
        return value


class DocumentReviewPatch(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    patch_id: str = Field(pattern=r"^docpatch-[0-9a-f]{32}$")
    operation_id: DocumentOperationId
    issue_id: str = Field(pattern=r"^docissue-[0-9a-f]{32}$")
    action: DocumentReviewAction
    replacement_value: str | None = Field(default=None, max_length=10_000)
    expected_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("replacement_value")
    @classmethod
    def reject_html(cls, value: str | None) -> str | None:
        return None if value is None else _reject_html(value)

    @model_validator(mode="after")
    def validate_replacement(self) -> DocumentReviewPatch:
        if self.action == DocumentReviewAction.EDIT and self.replacement_value is None:
            raise ValueError("EDIT review patches require replacement_value")
        if self.action != DocumentReviewAction.EDIT and self.replacement_value is not None:
            raise ValueError("only EDIT review patches may include replacement_value")
        return self


class DocumentQualityReport(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    overall_confidence: float = Field(ge=0, le=1)
    page_count: int = Field(ge=1, le=MAX_DOCUMENT_PAGES)
    native_text_page_count: int = Field(default=0, ge=0, le=MAX_DOCUMENT_PAGES)
    ocr_page_count: int = Field(default=0, ge=0, le=MAX_DOCUMENT_PAGES)
    block_count: int = Field(default=0, ge=0, le=2_000_000)
    table_count: int = Field(default=0, ge=0, le=100_000)
    review_required: bool
    issues: tuple[DocumentReviewIssue, ...] = Field(default=(), max_length=10_000)
    warnings: tuple[str, ...] = Field(default=(), max_length=100)

    @field_validator("warnings")
    @classmethod
    def reject_html(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_reject_html(item) for item in value)

    @model_validator(mode="after")
    def validate_counts(self) -> DocumentQualityReport:
        if self.native_text_page_count + self.ocr_page_count > self.page_count:
            raise ValueError("quality page counts cannot exceed page_count")
        if self.review_required != bool(self.issues):
            raise ValueError("review_required must match the presence of review issues")
        return self


class DocumentJobSummary(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    id: DocumentJobId
    task_id: DocumentTaskId | None = None
    operation_id: DocumentOperationId
    factory_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    source_artifact_id: DocumentArtifactId
    source_filename: str = Field(min_length=1, max_length=255)
    job_type: DocumentJobType
    processing_mode: DocumentProcessingMode
    state: DocumentJobState
    revision: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None = None

    @field_validator("source_filename")
    @classmethod
    def reject_html(cls, value: str) -> str:
        return _reject_html(value)


class DocumentJobDetail(DocumentJobSummary):
    page_range: DocumentPageRange
    preflight: DocumentPreflightResult | None = None
    snapshot_artifact_id: DocumentArtifactId | None = None
    result_artifact_id: DocumentArtifactId | None = None
    quality_report_artifact_id: DocumentArtifactId | None = None
    quality_report: DocumentQualityReport | None = None
    snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    failure_code: str = Field(
        default="", max_length=96, pattern=r"^(?:[A-Z][A-Z0-9_]{2,95})?$"
    )

    @model_validator(mode="after")
    def validate_result_state(self) -> DocumentJobDetail:
        if self.state == DocumentJobState.COMPLETED and self.result_artifact_id is None:
            raise ValueError("completed document jobs require a result artifact")
        if self.state == DocumentJobState.FAILED and not self.failure_code:
            raise ValueError("failed document jobs require failure_code")
        if self.state != DocumentJobState.FAILED and self.failure_code:
            raise ValueError("only failed document jobs may include failure_code")
        return self


class DocumentJobOptions(_ClosedDocumentModel):
    split_mode: Literal["each_page", "ranges"] = "each_page"
    split_page_ranges: str = Field(default="", max_length=1_000)
    profile: DocumentKind = DocumentKind.GENERAL
    review_threshold: float = Field(default=0.85, ge=0.5, le=1)
    sheet_strategy: Literal["TABLE_PER_SHEET", "PAGE_PER_SHEET", "MERGE_SAME_SCHEMA"] = "TABLE_PER_SHEET"
    type_inference: Literal["CONSERVATIVE", "SMART"] = "CONSERVATIVE"
    word_mode: Literal["EDITABLE", "LAYOUT_PRESERVING"] = "EDITABLE"
    translation_direction: Literal["AUTO", "ZH_TO_EN", "EN_TO_ZH"] = "AUTO"
    translation_layout: Literal["TRANSLATED_ONLY", "SIDE_BY_SIDE", "STACKED"] = "TRANSLATED_ONLY"
    glossary_version: str = Field(
        default="rrn-manufacturing-v1",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    protected_tokens: tuple[str, ...] = Field(default=(), max_length=200)
    include_editable_docx: bool = False
    preserve_bookmarks: bool = True
    office_output_quality: Literal["STANDARD", "PRINT"] = "STANDARD"

    @field_validator("split_page_ranges")
    @classmethod
    def normalize_page_ranges(cls, value: str) -> str:
        return _reject_html(value.strip())

    @field_validator("protected_tokens")
    @classmethod
    def validate_protected_tokens(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_reject_html(item.strip()) for item in value)
        if any(not item or len(item) > 256 for item in normalized):
            raise ValueError("protected tokens must contain 1 to 256 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("protected tokens must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_split_options(self) -> DocumentJobOptions:
        if self.split_mode == "ranges" and not self.split_page_ranges:
            raise ValueError("ranges split mode requires split_page_ranges")
        if self.split_mode == "each_page" and self.split_page_ranges:
            raise ValueError("each_page split mode must not include split_page_ranges")
        return self


class DocumentCloudConsent(_ClosedDocumentModel):
    accepted: Literal[True]
    provider: Literal["qwen"]
    region: Literal["cn-beijing"]
    purpose: Literal["DOCUMENT_PARSE"]
    notice_version: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$",
        max_length=64,
    )


class DocumentPreflightRequest(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    factory_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    source_artifact_id: DocumentArtifactId
    job_type: DocumentJobType
    processing_mode: DocumentProcessingMode = DocumentProcessingMode.AUTO


class DocumentJobCreate(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    operation_id: DocumentOperationId
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    factory_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    source_artifact_id: DocumentArtifactId
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_type: DocumentJobType
    processing_mode: DocumentProcessingMode = DocumentProcessingMode.AUTO
    page_range: DocumentPageRange = Field(default_factory=DocumentPageRange)
    options: DocumentJobOptions = Field(default_factory=DocumentJobOptions)
    cloud_consent: DocumentCloudConsent | None = None

    @model_validator(mode="after")
    def validate_cloud_consent(self) -> DocumentJobCreate:
        if (
            self.processing_mode == DocumentProcessingMode.LOCAL_PRIVATE
            and self.cloud_consent is not None
        ):
            raise ValueError("local private jobs must not include cloud consent")
        return self


class DocumentJobCapabilities(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    available: bool
    artifact_upload_available: bool
    task_runtime_available: bool
    cloud_ocr_available: bool = False
    local_translation_available: bool = False
    office_renderer_available: bool = False
    supported_job_types: tuple[DocumentJobType, ...] = Field(
        default=(), max_length=len(DocumentJobType)
    )
    legacy_fallback_job_types: tuple[DocumentJobType, ...] = (
        DocumentJobType.PDF_TO_EXCEL,
        DocumentJobType.PDF_TO_WORD,
        DocumentJobType.PDF_SPLIT,
    )


class DocumentJobList(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    items: tuple[DocumentJobSummary, ...] = Field(default=(), max_length=100)
    next_cursor: str | None = Field(default=None, max_length=512)


class DocumentJobOperationalMetrics(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    total_jobs: int = Field(ge=0)
    completed_jobs: int = Field(ge=0)
    failed_jobs: int = Field(ge=0)
    cancelled_jobs: int = Field(ge=0)
    active_jobs: int = Field(ge=0)
    review_jobs: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    review_rate: float = Field(ge=0, le=1)
    p50_duration_ms: int = Field(ge=0)
    p95_duration_ms: int = Field(ge=0)
    cloud_page_count: int = Field(ge=0)
    average_quality_confidence: float | None = Field(default=None, ge=0, le=1)


class DocumentJobEvent(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    sequence: int = Field(ge=1)
    task_id: DocumentTaskId
    step_key: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        max_length=64,
    )
    state: DocumentJobState
    reason_code: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]{2,95}$",
        max_length=96,
    )
    created_at: datetime


class DocumentJobEventPage(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    items: tuple[DocumentJobEvent, ...] = Field(default=(), max_length=100)
    next_after: int | None = Field(default=None, ge=1)


class DocumentJobCancelRequest(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    expected_revision: int = Field(ge=1)
    reason_code: str = Field(
        default="USER_CANCELLED",
        pattern=r"^[A-Z][A-Z0-9_]{2,95}$",
        max_length=96,
    )


class DocumentJobRetryRequest(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    expected_revision: int = Field(ge=1)


class DocumentJobReviewRequest(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    expected_revision: int = Field(ge=1)
    expected_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_runtime_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    patches: tuple[DocumentReviewPatch, ...] = Field(min_length=1, max_length=500)


class DocumentJobResult(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    task_id: DocumentTaskId
    artifact_id: DocumentArtifactId
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0, le=MAX_DOCUMENT_BYTES * 5)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    download_url: str = Field(
        pattern=r"^/api/ai/artifacts/aiart-[0-9a-f]{32}/download$",
        max_length=256,
    )


class DocumentStudioTaskOptions(_ClosedDocumentModel):
    """Closed arguments copied into each immutable AI Task step."""

    operation_id: DocumentOperationId
    factory_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    source_artifact_id: DocumentArtifactId
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_type: DocumentJobType
    processing_mode: DocumentProcessingMode
    page_range: DocumentPageRange
    options: DocumentJobOptions
    cloud_consent: DocumentCloudConsent | None = None


class DocumentStudioToolMetrics(_ClosedDocumentModel):
    page_count: int | None = Field(default=None, ge=1, le=MAX_DOCUMENT_PAGES)
    blank_page_count: int | None = Field(default=None, ge=0, le=MAX_DOCUMENT_PAGES)
    table_count: int | None = Field(default=None, ge=0, le=100_000)
    text_page_count: int | None = Field(default=None, ge=0, le=MAX_DOCUMENT_PAGES)
    ocr_page_count: int | None = Field(default=None, ge=0, le=MAX_DOCUMENT_PAGES)
    cloud_page_count: int | None = Field(default=None, ge=0, le=MAX_DOCUMENT_PAGES)
    image_count: int | None = Field(default=None, ge=0, le=100_000)
    file_count: int | None = Field(default=None, ge=1, le=MAX_DOCUMENT_PAGES)


class DocumentStudioToolResult(_ClosedDocumentModel):
    contract_version: DocumentContractVersion = DOCUMENT_CONTRACT_VERSION
    stage: Literal[
        "INSPECT",
        "EXTRACT",
        "RECONCILE",
        "REVIEW",
        "RENDER",
        "VERIFY",
    ]
    operation_id: DocumentOperationId
    factory_id: str
    source_artifact_id: DocumentArtifactId
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_artifact_id: DocumentArtifactId
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: str = Field(min_length=1, max_length=64)
    model_version: str = Field(min_length=1, max_length=128)
    source_unchanged: Literal[True] = True
    idempotent_replay: bool
    result_file_name: str = Field(min_length=1, max_length=255)
    review_required: bool = False
    metrics: DocumentStudioToolMetrics = Field(default_factory=DocumentStudioToolMetrics)
