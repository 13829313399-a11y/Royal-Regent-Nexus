from __future__ import annotations

from app.core.config import Settings
from app.services.document_studio.renderers.office_pdf_renderer import (
    OfficePdfRenderError,
    OfficePdfRenderResult,
    render_docx_to_pdf,
)


def convert_word_to_pdf(
    content: bytes,
    source_filename: str,
    *,
    settings: Settings,
) -> OfficePdfRenderResult:
    if not (
        settings.document_office_renderer_enabled
        and settings.document_office_renderer_network_isolation_verified
    ):
        raise OfficePdfRenderError(
            "DOCUMENT_OFFICE_RENDERER_UNAVAILABLE",
            "Word 转 PDF 隔离渲染器未开放。",
        )
    return render_docx_to_pdf(
        content,
        source_filename,
        command=settings.document_office_renderer_command,
        timeout_seconds=settings.document_office_renderer_timeout_seconds,
        network_isolation_command=(
            settings.document_office_renderer_network_isolation_command
        ),
    )
