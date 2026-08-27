import pytest
from app.schemas.document_studio import (
    DocumentBlock,
    DocumentPageSnapshot,
    DocumentSnapshot,
)
from app.services.document_studio.contracts import (
    DocumentBlockKind,
    DocumentExtractionRoute,
    DocumentExtractionSource,
)
from pydantic import ValidationError

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


def test_snapshot_enforces_bbox_page_sequence_confidence_and_no_html() -> None:
    snapshot = DocumentSnapshot(
        source_artifact_id=f"document-{HEX}",
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
