from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.document_studio.contracts import (
    DOCUMENT_CONTRACT_VERSION,
    MAX_BLOCK_TEXT_CHARS,
    MAX_DOCUMENT_PAGES,
    DocumentBlockKind,
    DocumentCellValueType,
    DocumentExtractionRoute,
    DocumentExtractionSource,
    DocumentKind,
    DocumentReviewIssueKind,
)

DocumentContractVersion = Literal["1"]
DocumentArtifactId = Annotated[str, Field(pattern=r"^aiart-[0-9a-f]{32}$")]
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
        if any(
            not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?", item)
            for item in value
        ):
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
