from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.document_studio import (
    DocumentBlock,
    DocumentJobDetail,
    DocumentPageRange,
    DocumentPageSnapshot,
    DocumentReviewPatch,
    DocumentSnapshot,
)
from app.services.document_studio.contracts import (
    DocumentBlockKind,
    DocumentExtractionRoute,
    DocumentExtractionSource,
    DocumentJobState,
    DocumentJobType,
    DocumentPageRangeKind,
    DocumentProcessingMode,
    DocumentReviewAction,
)

HEX = "a" * 32
SHA = "b" * 64


def _block() -> DocumentBlock:
    return DocumentBlock(
        block_id="p1-b1",
        kind=DocumentBlockKind.PARAGRAPH,
        bbox=(10, 20, 200, 40),
        raw_text="货号 001230",
        normalized_text="货号 001230",
        confidence=0.93,
        source=DocumentExtractionSource.NATIVE_TEXT,
    )


def test_page_ranges_are_one_based_unique_and_closed() -> None:
    page_range = DocumentPageRange(
        kind=DocumentPageRangeKind.PAGES,
        pages=(1, 3, 8),
    )

    assert page_range.contract_version == "1"

    with pytest.raises(ValidationError):
        DocumentPageRange(kind="PAGES", pages=(0, 1))
    with pytest.raises(ValidationError):
        DocumentPageRange(kind="PAGES", pages=(2, 1))
    with pytest.raises(ValidationError):
        DocumentPageRange(kind="ALL", pages=(1,))
    with pytest.raises(ValidationError):
        DocumentPageRange(kind="ALL", arbitrary=True)


def test_snapshot_enforces_bbox_page_sequence_confidence_and_no_html() -> None:
    snapshot = DocumentSnapshot(
        source_artifact_id=f"aiart-{HEX}",
        source_sha256=SHA,
        page_count=1,
        languages=("zh-CN", "en"),
        pages=(
            DocumentPageSnapshot(
                page_number=1,
                width=595.2,
                height=841.8,
                extraction_route=DocumentExtractionRoute.NATIVE,
                blocks=(_block(),),
            ),
        ),
    )

    assert snapshot.pages[0].blocks[0].confidence == 0.93

    with pytest.raises(ValidationError):
        DocumentBlock(
            block_id="p1-b1",
            kind="PARAGRAPH",
            bbox=(20, 20, 10, 40),
            confidence=0.5,
            source="NATIVE_TEXT",
        )
    with pytest.raises(ValidationError):
        DocumentBlock(
            block_id="p1-b1",
            kind="PARAGRAPH",
            bbox=(0, 0, 10, 10),
            raw_text="<script>alert(1)</script>",
            confidence=0.5,
            source="NATIVE_TEXT",
        )
    with pytest.raises(ValidationError):
        DocumentBlock(
            block_id="p1-b1",
            kind="PARAGRAPH",
            bbox=(0, 0, 10, 10),
            raw_text="plain text",
            confidence=1.1,
            source="NATIVE_TEXT",
        )


def test_review_patch_requires_edit_value_and_snapshot_hash() -> None:
    patch = DocumentReviewPatch(
        patch_id=f"docpatch-{HEX}",
        operation_id=f"docop-{HEX}",
        issue_id=f"docissue-{HEX}",
        action=DocumentReviewAction.EDIT,
        replacement_value="001230",
        expected_snapshot_sha256=SHA,
    )

    assert patch.replacement_value == "001230"

    with pytest.raises(ValidationError):
        DocumentReviewPatch(
            patch_id=f"docpatch-{HEX}",
            operation_id=f"docop-{HEX}",
            issue_id=f"docissue-{HEX}",
            action="EDIT",
            expected_snapshot_sha256=SHA,
        )


def test_completed_job_requires_authorized_result_artifact() -> None:
    now = datetime.now(UTC)
    detail = DocumentJobDetail(
        id=f"docjob-{HEX}",
        task_id=f"aitask-{HEX}",
        operation_id=f"docop-{HEX}",
        factory_id="huakang-b",
        source_artifact_id=f"aiart-{HEX}",
        source_filename="订单.pdf",
        job_type=DocumentJobType.PDF_TO_EXCEL,
        processing_mode=DocumentProcessingMode.LOCAL_PRIVATE,
        state=DocumentJobState.COMPLETED,
        created_at=now,
        updated_at=now,
        terminal_at=now,
        page_range=DocumentPageRange(),
        result_artifact_id=f"aiart-{HEX}",
        input_hash=SHA,
        runtime_plan_hash=SHA,
    )

    assert detail.result_artifact_id == f"aiart-{HEX}"

    with pytest.raises(ValidationError):
        DocumentJobDetail(**detail.model_dump(exclude={"result_artifact_id"}))
