from __future__ import annotations

from io import BytesIO

import pdfplumber

from app.schemas.document_studio import (
    DocumentBlock,
    DocumentCellEvidence,
    DocumentPageSnapshot,
    DocumentSnapshot,
    DocumentTable,
)
from app.services.document_studio.contracts import (
    DocumentBlockKind,
    DocumentCellValueType,
    DocumentExtractionRoute,
    DocumentExtractionSource,
    DocumentKind,
)
from app.services.pdf_to_excel import _ocr_page_layout


def _bounded_bbox(
    value: tuple[float, float, float, float], *, width: float, height: float
) -> tuple[float, float, float, float]:
    left, top, right, bottom = value
    return (
        max(0.0, min(float(left), width)),
        max(0.0, min(float(top), height)),
        max(0.0, min(float(right), width)),
        max(0.0, min(float(bottom), height)),
    )


def _native_blocks(page, *, page_number: int) -> tuple[DocumentBlock, ...]:
    words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
    grouped: list[list[dict[str, object]]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        if not grouped or abs(float(word["top"]) - float(grouped[-1][0]["top"])) > 3:
            grouped.append([word])
        else:
            grouped[-1].append(word)
    blocks: list[DocumentBlock] = []
    for index, line in enumerate(grouped, start=1):
        text = " ".join(str(item.get("text", "")).strip() for item in line).strip()
        if not text:
            continue
        bbox = _bounded_bbox(
            (
                min(float(item["x0"]) for item in line),
                min(float(item["top"]) for item in line),
                max(float(item["x1"]) for item in line),
                max(float(item["bottom"]) for item in line),
            ),
            width=float(page.width),
            height=float(page.height),
        )
        blocks.append(
            DocumentBlock(
                block_id=f"p{page_number}-b{index}",
                kind=DocumentBlockKind.PARAGRAPH,
                bbox=bbox,
                raw_text=text,
                normalized_text=text,
                confidence=0.98,
                source=DocumentExtractionSource.NATIVE_TEXT,
            )
        )
    return tuple(blocks)


def _ocr_blocks(
    data: bytes, *, page_index: int, page_number: int, width: float, height: float
) -> tuple[DocumentBlock, ...]:
    extracted = _ocr_page_layout(data, page_index, width, height)
    return tuple(
        DocumentBlock(
            block_id=f"p{page_number}-b{index}",
            kind=DocumentBlockKind.PARAGRAPH,
            bbox=_bounded_bbox(
                (block.x0, block.top, block.x1, block.bottom),
                width=width,
                height=height,
            ),
            raw_text=block.text,
            normalized_text=block.text,
            confidence=0.80,
            source=DocumentExtractionSource.LOCAL_OCR,
            needs_review=True,
        )
        for index, block in enumerate(extracted, start=1)
        if block.text.strip()
    )


def _page_tables(
    page, *, page_number: int, first_table_index: int
) -> tuple[tuple[DocumentTable, ...], int]:
    tables: list[DocumentTable] = []
    table_index = first_table_index
    for found in page.find_tables() or []:
        rows = found.extract() or []
        column_count = max((len(row) for row in rows), default=0)
        if not rows or column_count <= 0:
            continue
        table_index += 1
        table_bbox = _bounded_bbox(
            tuple(float(value) for value in found.bbox),
            width=float(page.width),
            height=float(page.height),
        )
        left, top, right, bottom = table_bbox
        cell_width = (right - left) / column_count if column_count else 0
        cell_height = (bottom - top) / len(rows) if rows else 0
        cells: list[DocumentCellEvidence] = []
        for row_index, row in enumerate(rows, start=1):
            for column_index in range(1, column_count + 1):
                raw = str(row[column_index - 1] or "").strip() if column_index <= len(row) else ""
                cells.append(
                    DocumentCellEvidence(
                        cell_id=(
                            f"table-{table_index}-r{row_index}-c{column_index}"
                        ),
                        raw_text=raw,
                        normalized_value=raw,
                        value_type=DocumentCellValueType.TEXT,
                        confidence=0.95,
                        source_page=page_number,
                        source_bbox=(
                            left + cell_width * (column_index - 1),
                            top + cell_height * (row_index - 1),
                            left + cell_width * column_index,
                            top + cell_height * row_index,
                        ),
                        sources=(DocumentExtractionSource.NATIVE_TEXT,),
                    )
                )
        tables.append(
            DocumentTable(
                table_id=f"table-{table_index}",
                page_number=page_number,
                bbox=table_bbox,
                row_count=len(rows),
                column_count=column_count,
                cells=tuple(cells),
                confidence=0.95,
            )
        )
    return tuple(tables), table_index


def extract_local_snapshot(
    *,
    data: bytes,
    source_artifact_id: str,
    source_sha256: str,
    document_kind: DocumentKind = DocumentKind.GENERAL,
) -> DocumentSnapshot:
    pages: list[DocumentPageSnapshot] = []
    warnings: list[str] = []
    table_index = 0
    with pdfplumber.open(BytesIO(data)) as document:
        for page_index, page in enumerate(document.pages):
            page_number = page_index + 1
            width = float(page.width)
            height = float(page.height)
            blocks = _native_blocks(page, page_number=page_number)
            route = DocumentExtractionRoute.NATIVE
            if not blocks:
                blocks = _ocr_blocks(
                    data,
                    page_index=page_index,
                    page_number=page_number,
                    width=width,
                    height=height,
                )
                route = DocumentExtractionRoute.LOCAL_OCR
                if not blocks:
                    route = DocumentExtractionRoute.MANUAL_REVIEW
                    warnings.append(f"第 {page_number} 页没有可验证的本地提取结果。")
            tables, table_index = _page_tables(
                page,
                page_number=page_number,
                first_table_index=table_index,
            )
            pages.append(
                DocumentPageSnapshot(
                    page_number=page_number,
                    width=width,
                    height=height,
                    rotation=int(page.rotation or 0) % 360,
                    extraction_route=route,
                    blocks=blocks,
                    tables=tables,
                )
            )
    return DocumentSnapshot(
        source_artifact_id=source_artifact_id,
        source_sha256=source_sha256,
        page_count=len(pages),
        document_kind=document_kind,
        pages=tuple(pages),
        warnings=tuple(warnings),
    )
