from __future__ import annotations

from app.schemas.document_studio import DocumentSnapshot
from app.services.document_studio.contracts import DocumentExtractionRoute


def cloud_ocr_page_numbers(
    snapshot: DocumentSnapshot,
    *,
    force_all_pages: bool = False,
) -> tuple[int, ...]:
    """Select pages for the request-time Base64 Qwen OCR path."""
    if force_all_pages:
        return tuple(page.page_number for page in snapshot.pages)
    selected: list[int] = []
    for page in snapshot.pages:
        confidence = (
            sum(block.confidence for block in page.blocks) / len(page.blocks)
            if page.blocks
            else 0.0
        )
        if page.extraction_route != DocumentExtractionRoute.NATIVE or confidence < 0.92:
            selected.append(page.page_number)
    return tuple(selected)
