from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.core.config import Settings
from app.services.document_studio.contracts import DocumentExtractionRoute
from app.services.document_studio.evidence import extract_local_snapshot
from app.services.document_studio.pipelines.pdf_translation import (
    PdfTranslationError,
    TranslationBatch,
    translate_snapshot,
)
from app.services.document_studio.renderers.pdf_translation_renderer import (
    render_pdf_translation,
)

MAX_PDF_PAGES = 80


class PdfTranslationConversionError(ValueError):
    pass


@dataclass(frozen=True)
class PdfTranslationResult:
    content: bytes
    output_file_name: str
    media_type: str
    page_count: int
    translated_unit_count: int
    ocr_page_count: int


def convert_pdf_translation(
    pdf_bytes: bytes,
    source_file_name: str,
    *,
    settings: Settings,
    requested_direction: str = "AUTO",
    layout: str = "TRANSLATED_ONLY",
    protected_tokens: tuple[str, ...] = (),
    include_editable_docx: bool = False,
    translator: TranslationBatch | None = None,
) -> PdfTranslationResult:
    if requested_direction not in {"AUTO", "ZH_TO_EN", "EN_TO_ZH"}:
        raise PdfTranslationConversionError("PDF 翻译方向无效。")
    if layout not in {"TRANSLATED_ONLY", "SIDE_BY_SIDE", "STACKED"}:
        raise PdfTranslationConversionError("PDF 翻译版式无效。")

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted:
            raise PdfTranslationConversionError("PDF 已加密，无法翻译；请先移除打开密码。")
        page_count = len(reader.pages)
    except PdfTranslationConversionError:
        raise
    except Exception as exc:
        raise PdfTranslationConversionError(
            "PDF 无法读取；请确认文件未加密、未损坏。"
        ) from exc

    if page_count < 1:
        raise PdfTranslationConversionError("PDF 中没有可翻译的页面。")
    if page_count > MAX_PDF_PAGES:
        raise PdfTranslationConversionError(f"单次最多翻译 {MAX_PDF_PAGES} 页 PDF。")

    source_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    try:
        snapshot = extract_local_snapshot(
            data=pdf_bytes,
            source_artifact_id=f"aiart-{source_sha256[:32]}",
            source_sha256=source_sha256,
        )
        translated = translate_snapshot(
            snapshot,
            settings=settings,
            requested_direction=requested_direction,
            protected_tokens=protected_tokens,
            translator=translator,
        )
        content, output_file_name, media_type = render_pdf_translation(
            source_pdf=pdf_bytes,
            snapshot=translated,
            source_filename=source_file_name,
            layout=layout,
            include_editable_docx=include_editable_docx,
        )
    except PdfTranslationError as exc:
        raise PdfTranslationConversionError(str(exc)) from exc
    except PdfTranslationConversionError:
        raise
    except Exception as exc:
        raise PdfTranslationConversionError(
            "PDF 翻译失败；请确认文档包含可识别文字并稍后重试。"
        ) from exc

    translated_unit_count = sum(
        1
        for page in translated.pages
        for value in (
            *(block.normalized_text for block in page.blocks),
            *(
                cell.normalized_value
                for table in page.tables
                for cell in table.cells
            ),
        )
        if value.strip()
    )
    ocr_page_count = sum(
        page.extraction_route == DocumentExtractionRoute.LOCAL_OCR
        for page in translated.pages
    )
    return PdfTranslationResult(
        content=content,
        output_file_name=output_file_name,
        media_type=media_type,
        page_count=page_count,
        translated_unit_count=translated_unit_count,
        ocr_page_count=ocr_page_count,
    )
