from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from app.models.ai_artifact import AIArtifact
from app.schemas.document_studio import DocumentPreflightResult
from app.services.ai.artifacts.service import ArtifactInvalidError
from app.services.document_studio.contracts import (
    DocumentJobType,
    DocumentProcessingMode,
)
from app.services.document_studio.routing import route_document_job

MAX_SYNC_TEXT_CLASSIFICATION_PAGES = 20


def _inspect_pdf(data: bytes) -> tuple[int, int, int, tuple[str, ...]]:
    warnings: list[str] = []
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ArtifactInvalidError(
                "不接受加密 PDF。", code="DOCUMENT_PREFLIGHT_ENCRYPTED"
            )
        page_count = len(reader.pages)
        if page_count <= 0:
            raise ArtifactInvalidError(
                "PDF 不包含可处理页面。", code="DOCUMENT_PREFLIGHT_EMPTY"
            )
        native_text_pages = 0
        inspected_page_count = min(page_count, MAX_SYNC_TEXT_CLASSIFICATION_PAGES)
        for page_index in range(inspected_page_count):
            page = reader.pages[page_index]
            try:
                if (page.extract_text() or "").strip():
                    native_text_pages += 1
            except Exception:  # noqa: BLE001 - one unreadable page must not hide the document
                warnings.append("部分页面无法完成轻量文本检查，将在任务中重新验证。")
        scanned_pages = inspected_page_count - native_text_pages
        if inspected_page_count < page_count:
            warnings.append(
                f"同步预检仅分类前 {inspected_page_count} 页；完整页级检查由 Task 执行。"
            )
    except ArtifactInvalidError:
        raise
    except Exception as exc:
        raise ArtifactInvalidError(
            "PDF 无法完成预检。", code="DOCUMENT_PREFLIGHT_INVALID_PDF"
        ) from exc
    return page_count, native_text_pages, scanned_pages, tuple(dict.fromkeys(warnings))


def preflight_document(
    *,
    source: AIArtifact,
    data: bytes,
    job_type: DocumentJobType,
    processing_mode: DocumentProcessingMode,
    task_runtime_available: bool,
    cloud_ocr_available: bool,
    local_translation_available: bool,
    office_renderer_available: bool,
) -> DocumentPreflightResult:
    is_pdf = source.normalized_extension == ".pdf"
    is_docx = source.normalized_extension == ".docx"
    if job_type == DocumentJobType.WORD_TO_PDF and not is_docx:
        raise ArtifactInvalidError(
            "Word 转 PDF 只接受 DOCX Artifact。",
            code="DOCUMENT_PREFLIGHT_TYPE_MISMATCH",
        )
    if job_type != DocumentJobType.WORD_TO_PDF and not is_pdf:
        raise ArtifactInvalidError(
            "当前文档任务只接受 PDF Artifact。",
            code="DOCUMENT_PREFLIGHT_TYPE_MISMATCH",
        )

    if is_pdf:
        page_count, native_pages, scanned_pages, inspect_warnings = _inspect_pdf(data)
        detected_mime = "application/pdf"
    else:
        page_count, native_pages, scanned_pages, inspect_warnings = 1, 1, 0, ()
        detected_mime = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    route, route_warnings = route_document_job(
        job_type=job_type,
        processing_mode=processing_mode,
        page_count=page_count,
        task_runtime_available=task_runtime_available,
        cloud_ocr_available=cloud_ocr_available,
        local_translation_available=local_translation_available,
        office_renderer_available=office_renderer_available,
    )
    return DocumentPreflightResult(
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        filename=source.original_filename,
        detected_mime_type=detected_mime,
        size_bytes=source.size_bytes,
        page_count=page_count,
        native_text_pages=native_pages,
        scanned_pages=scanned_pages,
        route_decision=route,
        warnings=(*inspect_warnings, *route_warnings),
    )
