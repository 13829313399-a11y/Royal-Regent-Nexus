from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfWriter

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings
from app.schemas.document_studio import DocumentPageSnapshot, DocumentSnapshot
from app.services.document_studio.contracts import DocumentExtractionRoute
from app.services.document_studio.renderers.office_pdf_renderer import (
    OfficeRendererStatus,
)
from app.services.document_tools.contracts import (
    OcrBlock,
    OcrPage,
    OcrResult,
    ProcessingMode,
    StructuredTable,
    StructuredTables,
    TableCell,
)


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        qwen_document_enabled=True,
        ai_workspace_id="workspace-test",
        dashscope_api_key="test-key",
        **overrides,
    )


def _one_page_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _empty_snapshot() -> DocumentSnapshot:
    return DocumentSnapshot(
        source_artifact_id=f"aiart-{'a' * 32}",
        source_sha256="b" * 64,
        page_count=1,
        pages=(
            DocumentPageSnapshot(
                page_number=1,
                width=595,
                height=842,
                extraction_route=DocumentExtractionRoute.MANUAL_REVIEW,
            ),
        ),
    )


def test_capabilities_are_runtime_driven_and_do_not_require_task_runtime(
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

    assert result["tools"]["pdf-to-excel"]["modes"]["QWEN"]["available"] is True
    assert result["tools"]["pdf-translation"]["modes"]["QWEN"]["available"] is True
    assert result["tools"]["word-to-pdf"]["available"] is False
    assert result["tools"]["word-to-pdf"]["reason_code"] == "LIBREOFFICE_NOT_INSTALLED"
    assert "artifact" not in str(result).lower()
    assert "task" not in str(result).lower()


def test_qwen_translation_uses_model_and_official_translation_options() -> None:
    from app.services.document_tools.qwen_translation import QwenTranslationService

    calls: list[dict] = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="PO-001 quantity 8")
                    )
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    service = QwenTranslationService(_settings(), client=client)

    result = service.translate_batch(
        ["PO-001 数量 8"],
        "zh_to_en",
        terms=[{"source": "数量", "target": "quantity"}],
        domain_prompt="Manufacturing order document.",
    )

    assert result == ["PO-001 quantity 8"]
    assert calls[0]["model"] == "qwen-mt-plus"
    options = calls[0]["extra_body"]["translation_options"]
    assert options["source_lang"] == "Chinese"
    assert options["target_lang"] == "English"
    assert options["terms"] == [{"source": "数量", "target": "quantity"}]


def test_qwen_table_json_is_validated_and_retried_once() -> None:
    from app.services.document_tools.qwen_table_extractor import QwenTableExtractor

    responses = iter(
        [
            '{"tables":[{"title":"订单","header":[{"value":"货号","confidence":1}],"rows":[[]],"continuation_key":"po","confidence":0.9}]}',
            '{"tables":[{"title":"订单","header":[{"value":"货号","confidence":1}],"rows":[[{"value":"00125","confidence":0.8}]],"continuation_key":"po","confidence":0.9}]}',
        ]
    )
    calls: list[dict] = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=next(responses)))
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    extractor = QwenTableExtractor(_settings(), client=client)
    result = extractor.extract_page(
        OcrPage(page_number=1, blocks=(OcrBlock(text="货号\n00125"),))
    )

    assert result.tables[0].rows[0][0].value == "00125"
    assert len(calls) == 2
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["extra_body"] == {"enable_thinking": False}


def test_qwen_table_json_accepts_null_for_no_continuation() -> None:
    from app.services.document_tools.qwen_table_extractor import QwenTableExtractor

    content = (
        '{"tables":[{"title":"","header":[{"value":"Item","confidence":1}],'
        '"rows":[[{"value":"00125","confidence":0.9}]],'
        '"continuation_key":null,"confidence":0.9}]}'
    )

    class Completions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    result = QwenTableExtractor(_settings(), client=client).extract_page(
        OcrPage(page_number=1, blocks=(OcrBlock(text="Item\n00125"),))
    )

    assert result.tables[0].continuation_key == ""
    assert result.tables[0].rows[0][0].value == "00125"


def test_qwen_table_output_directly_builds_workbook_and_marks_low_confidence(
    monkeypatch,
) -> None:
    from app.services.document_tools import smart_converters as service

    class OcrService:
        def parse_pdf(self, _data, *, page_numbers):
            assert page_numbers == (1,)
            return OcrResult(
                pages=(
                    OcrPage(
                        page_number=1,
                        blocks=(OcrBlock(text="货号 数量\n00125 8", confidence=0.9),),
                    ),
                )
            )

    class TableExtractor:
        def extract_page(self, _page):
            return StructuredTables(
                tables=(
                    StructuredTable(
                        title="订单",
                        header=(
                            TableCell(value="货号", confidence=1),
                            TableCell(value="数量", confidence=1),
                        ),
                        rows=(
                            (
                                TableCell(value="00125", confidence=0.95),
                                TableCell(value="8", confidence=0.7),
                            ),
                        ),
                        continuation_key="order-lines",
                        confidence=0.9,
                    ),
                )
            )

    monkeypatch.setattr(service, "_local_snapshot", lambda _data: _empty_snapshot())
    result = service.convert_pdf_to_excel_smart(
        _one_page_pdf(),
        "订单.pdf",
        settings=_settings(),
        mode=ProcessingMode.QWEN,
        ocr_service=OcrService(),
        table_extractor=TableExtractor(),
    )

    workbook = load_workbook(BytesIO(result.content))
    worksheet = workbook["订单"]
    assert worksheet["A2"].value == "00125"
    assert worksheet["A2"].number_format == "@"
    assert worksheet["B2"].comment is not None
    assert result.qwen_page_count == 1
    assert result.low_confidence_count == 1


def test_pdf_to_word_layout_mode_reopens_with_one_image_per_page() -> None:
    from app.services.document_tools.smart_converters import convert_pdf_to_word_smart

    result = convert_pdf_to_word_smart(
        _one_page_pdf(),
        "版式.pdf",
        settings=_settings(),
        mode=ProcessingMode.LOCAL,
        output_mode="LAYOUT_PRESERVING",
    )

    document = Document(BytesIO(result.content))
    assert len(document.inline_shapes) == 1
    assert result.page_count == 1
    assert result.image_count == 1
    assert result.warnings
