from __future__ import annotations

import hashlib

from app.schemas.document_studio import (
    DocumentQualityReport,
    DocumentReviewIssue,
    DocumentSnapshot,
)
from app.services.document_studio.contracts import (
    DocumentExtractionRoute,
    DocumentReviewAction,
    DocumentReviewIssueKind,
    DocumentReviewSeverity,
)


def snapshot_sha256(snapshot: DocumentSnapshot) -> str:
    return hashlib.sha256(
        snapshot.model_dump_json(exclude_none=True).encode("utf-8")
    ).hexdigest()


def _issue_id(kind: DocumentReviewIssueKind, target_id: str) -> str:
    value = hashlib.sha256(f"{kind.value}:{target_id}".encode()).hexdigest()[:32]
    return f"docissue-{value}"


def build_quality_report(
    snapshot: DocumentSnapshot, *, review_threshold: float
) -> DocumentQualityReport:
    issues: list[DocumentReviewIssue] = []
    confidences: list[float] = []
    table_count = 0
    block_count = 0
    native_pages = 0
    ocr_pages = 0
    for page in snapshot.pages:
        if page.extraction_route == DocumentExtractionRoute.NATIVE:
            native_pages += 1
        elif page.extraction_route in {
            DocumentExtractionRoute.LOCAL_OCR,
            DocumentExtractionRoute.QWEN_OCR,
            DocumentExtractionRoute.NATIVE_PLUS_AI_REPAIR,
        }:
            ocr_pages += 1
        for block in page.blocks:
            block_count += 1
            confidences.append(block.confidence)
            if block.needs_review or block.confidence < review_threshold:
                issue_kind = (
                    DocumentReviewIssueKind.TEXT_OVERFLOW
                    if block.needs_review and block.confidence >= review_threshold
                    else DocumentReviewIssueKind.LOW_CONFIDENCE_BLOCK
                )
                issues.append(
                    DocumentReviewIssue(
                        issue_id=_issue_id(
                            issue_kind,
                            block.block_id,
                        ),
                        severity=DocumentReviewSeverity.WARNING,
                        kind=issue_kind,
                        page_number=page.page_number,
                        target_id=block.block_id,
                        original_value=block.raw_text,
                        proposed_value=block.normalized_text,
                        confidence=block.confidence,
                        message="该文本块置信度低于当前复核阈值。",
                        options=(
                            DocumentReviewAction.ACCEPT,
                            DocumentReviewAction.EDIT,
                            DocumentReviewAction.MARK_UNKNOWN,
                        ),
                    )
                )
        for table in page.tables:
            table_count += 1
            confidences.append(table.confidence)
            for cell in table.cells:
                confidences.append(cell.confidence)
                if cell.review_reasons or cell.confidence < review_threshold:
                    issue_kind = (
                        cell.review_reasons[0]
                        if cell.review_reasons
                        else DocumentReviewIssueKind.LOW_CONFIDENCE_CELL
                    )
                    issues.append(
                        DocumentReviewIssue(
                            issue_id=_issue_id(
                                issue_kind,
                                cell.cell_id,
                            ),
                            severity=DocumentReviewSeverity.WARNING,
                            kind=issue_kind,
                            page_number=page.page_number,
                            target_id=cell.cell_id,
                            original_value=cell.raw_text,
                            proposed_value=cell.normalized_value,
                            confidence=cell.confidence,
                            message="该单元格需要人工确认后才能生成结果。",
                            options=(
                                DocumentReviewAction.ACCEPT,
                                DocumentReviewAction.EDIT,
                                DocumentReviewAction.MARK_UNKNOWN,
                            ),
                        )
                    )
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return DocumentQualityReport(
        snapshot_sha256=snapshot_sha256(snapshot),
        overall_confidence=round(confidence, 6),
        page_count=snapshot.page_count,
        native_text_page_count=native_pages,
        ocr_page_count=ocr_pages,
        block_count=block_count,
        table_count=table_count,
        review_required=bool(issues),
        issues=tuple(issues),
        warnings=snapshot.warnings,
    )
