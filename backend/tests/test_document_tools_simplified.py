from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings
from app.services.document_studio.renderers.office_pdf_renderer import (
    OfficeRendererStatus,
)
from app.services.document_tools.contracts import DocumentToolError, ProcessingMode
from app.services.pdf_to_word import convert_pdf_to_word_layout


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _one_page_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_capabilities_are_local_and_do_not_require_background_runtime(
    monkeypatch,
) -> None:
    from app.services.document_tools import capabilities as service

    monkeypatch.setattr(
        service,
        "office_renderer_status",
        lambda _command: OfficeRendererStatus(
            available=False,
            command="libreoffice",
            reason_code="LIBREOFFICE_NOT_INSTALLED",
        ),
    )
    monkeypatch.setattr(
        service,
        "document_translation_status",
        lambda _model_dir: {"available": False, "engine": "offline"},
    )

    result = service.document_tool_capabilities(_settings())

    assert set(result["tools"]["pdf-to-excel"]["modes"]) == {"AUTO", "LOCAL"}
    assert result["tools"]["pdf-to-excel"]["modes"]["LOCAL"]["available"] is True
    assert result["tools"]["pdf-translation"]["available"] is False
    assert result["tools"]["word-to-pdf"]["available"] is False
    assert result["tools"]["word-to-pdf"]["reason_code"] == "LIBREOFFICE_NOT_INSTALLED"
    assert set(result["providers"]) == {"libreoffice", "local_translation"}


def test_pdf_to_word_layout_mode_reopens_with_one_image_per_page() -> None:
    result = convert_pdf_to_word_layout(_one_page_pdf(), "版式.pdf")

    document = Document(BytesIO(result.content))
    assert len(document.inline_shapes) == 1
    assert result.page_count == 1
    assert result.image_count == 1


def test_processing_mode_rejects_removed_cloud_mode() -> None:
    assert ProcessingMode.parse("AUTO") is ProcessingMode.AUTO
    assert ProcessingMode.parse("LOCAL") is ProcessingMode.LOCAL
    with pytest.raises(DocumentToolError):
        ProcessingMode.parse("CLOUD")
