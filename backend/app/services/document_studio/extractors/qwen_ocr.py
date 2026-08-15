from __future__ import annotations

import hashlib
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from app.schemas.document_studio import DocumentBlock, DocumentSnapshot
from app.services.document_studio.contracts import (
    DocumentBlockKind,
    DocumentExtractionRoute,
    DocumentExtractionSource,
)
from app.services.document_studio.providers.qwen_document import QwenDocumentProvider


def _selected_page_numbers(snapshot: DocumentSnapshot) -> tuple[int, ...]:
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


def _pdf_subset(data: bytes, page_numbers: tuple[int, ...]) -> bytes:
    reader = PdfReader(BytesIO(data), strict=True)
    writer = PdfWriter()
    for page_number in page_numbers:
        writer.add_page(reader.pages[page_number - 1])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _scaled_bbox(
    value: tuple[float, float, float, float], *, width: float, height: float
) -> tuple[float, float, float, float]:
    left, top, right, bottom = value
    if max(value) <= 1:
        left, right = left * width, right * width
        top, bottom = top * height, bottom * height
    left = max(0.0, min(left, width))
    right = max(left, min(right, width))
    top = max(0.0, min(top, height))
    bottom = max(top, min(bottom, height))
    return left, top, right, bottom


def enhance_snapshot_with_qwen(
    snapshot: DocumentSnapshot,
    *,
    data: bytes,
    artifact_id: str,
    filename: str,
    provider: QwenDocumentProvider,
) -> DocumentSnapshot:
    selected = _selected_page_numbers(snapshot)
    if not selected:
        return snapshot
    payload = snapshot.model_dump(mode="json")
    pages_by_number = {int(page["page_number"]): page for page in payload["pages"]}
    for batch_start in range(0, len(selected), 50):
        global_pages = selected[batch_start : batch_start + 50]
        subset = _pdf_subset(data, global_pages)
        result = provider.parse_pdf(
            artifact_id=artifact_id,
            sha256=hashlib.sha256(subset).hexdigest(),
            filename=filename,
            data=subset,
            page_count=len(global_pages),
        )
        for parsed_page, global_page_number in zip(
            result.pages, global_pages, strict=True
        ):
            target = pages_by_number[global_page_number]
            width = float(target["width"])
            height = float(target["height"])
            target["blocks"] = [
                DocumentBlock(
                    block_id=f"p{global_page_number}-b{index}",
                    kind=DocumentBlockKind.PARAGRAPH,
                    bbox=_scaled_bbox(block.bbox, width=width, height=height),
                    raw_text=block.text,
                    normalized_text=block.text,
                    confidence=block.confidence,
                    source=DocumentExtractionSource.QWEN_OCR,
                    needs_review=block.confidence < 0.85,
                ).model_dump(mode="json")
                for index, block in enumerate(parsed_page.blocks, start=1)
            ]
            target["extraction_route"] = DocumentExtractionRoute.QWEN_OCR.value
    return DocumentSnapshot.model_validate(payload)
