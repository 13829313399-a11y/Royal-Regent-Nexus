from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader, PdfWriter

from app.core.config import Settings
from app.schemas.document_studio import (
    DocumentBlock,
    DocumentCellEvidence,
    DocumentJobOptions,
    DocumentPageSnapshot,
    DocumentSnapshot,
    DocumentTable,
)
from app.services.document_studio.extractors.qwen_ocr import enhance_snapshot_with_qwen
from app.services.document_studio.pipelines import pdf_to_excel as excel_pipeline
from app.services.document_studio.pipelines.pdf_to_word import (
    convert_pdf_to_layout_preserving_word,
)
from app.services.document_studio.pipelines.pdf_translation import translate_snapshot
from app.services.document_studio.providers.qwen_document import (
    QwenDocumentBlock,
    QwenDocumentError,
    QwenDocumentPage,
    QwenDocumentParseResult,
    QwenDocumentProvider,
    _parse_result,
    get_document_provider_status,
)
from app.services.document_studio.providers.qwen_reconcile import (
    CellRevision,
    QwenReconcileProvider,
    ReconcileResult,
    apply_reconcile_result,
)
from app.services.document_studio.providers.signed_file_source import SignedFileLease
from app.services.document_studio.renderers import office_pdf_renderer
from app.services.pdf_to_excel import PdfToExcelResult


def _pdf_bytes(page_count: int = 1) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def _snapshot(text: str = "订单 PO-001 数量 0012") -> DocumentSnapshot:
    return DocumentSnapshot(
        source_artifact_id="aiart-" + "a" * 32,
        source_sha256="b" * 64,
        page_count=1,
        pages=(
            DocumentPageSnapshot(
                page_number=1,
                width=612,
                height=792,
                extraction_route="NATIVE",
                blocks=(
                    DocumentBlock(
                        block_id="p1-b1",
                        kind="PARAGRAPH",
                        bbox=(10, 10, 300, 40),
                        raw_text=text,
                        normalized_text=text,
                        confidence=0.98,
                        source="NATIVE_TEXT",
                    ),
                ),
            ),
        ),
    )


def _table_snapshot() -> DocumentSnapshot:
    cells = (
        DocumentCellEvidence(
            cell_id="table-1-r1-c1",
            raw_text="0012",
            normalized_value="0012",
            value_type="IDENTIFIER",
            confidence=0.9,
            source_page=1,
            source_bbox=(10, 10, 60, 30),
            sources=("NATIVE_TEXT",),
        ),
        DocumentCellEvidence(
            cell_id="table-1-r1-c2",
            raw_text="42.00",
            normalized_value="42.00",
            value_type="TEXT",
            confidence=0.9,
            source_page=1,
            source_bbox=(60, 10, 120, 30),
            sources=("NATIVE_TEXT",),
        ),
    )
    return DocumentSnapshot(
        source_artifact_id="aiart-" + "a" * 32,
        source_sha256="b" * 64,
        page_count=1,
        pages=(
            DocumentPageSnapshot(
                page_number=1,
                width=612,
                height=792,
                extraction_route="NATIVE",
                tables=(
                    DocumentTable(
                        table_id="table-1",
                        page_number=1,
                        bbox=(10, 10, 120, 30),
                        row_count=1,
                        column_count=2,
                        cells=cells,
                        confidence=0.9,
                    ),
                ),
            ),
        ),
    )


def test_layout_preserving_word_renders_each_pdf_page_as_a_page_image() -> None:
    result = convert_pdf_to_layout_preserving_word(_pdf_bytes(2), "layout.pdf")

    document = Document(BytesIO(result.content))
    assert result.page_count == 2
    assert result.image_count == 2
    assert result.output_file_name == "layout_版式保真.docx"
    assert len(document.inline_shapes) == 2


def test_evidence_workbook_adds_closed_source_mapping_and_smart_types(
    monkeypatch,
) -> None:
    workbook = Workbook()
    workbook.active.title = "转换说明"
    workbook.active.append(["PDF 转 Excel", "转换结果"])
    data = workbook.create_sheet("第1页_表格1")
    data.append(["编号", "数量", "日期"])
    data.append(["0012", "42", "2026-08-14"])
    output = BytesIO()
    workbook.save(output)
    monkeypatch.setattr(
        excel_pipeline,
        "convert_pdf_to_excel",
        lambda *_args: PdfToExcelResult(
            content=output.getvalue(),
            page_count=1,
            table_count=1,
            text_page_count=1,
            ocr_page_count=0,
            output_file_name="evidence.xlsx",
        ),
    )

    result = excel_pipeline.convert_pdf_to_evidence_workbook(
        _pdf_bytes(),
        "source.pdf",
        snapshot=_snapshot(),
        options=DocumentJobOptions(type_inference="SMART"),
    )

    rendered = load_workbook(BytesIO(result.content))
    assert "来源映射" in rendered.sheetnames
    assert rendered["来源映射"]["A2"].value == "p1-b1"
    assert rendered["第1页_表格1"]["A2"].value == "0012"
    assert rendered["第1页_表格1"]["B2"].value == 42


def test_pdf_translation_preserves_codes_and_numbers() -> None:
    def translator(values, direction):
        assert direction == "zh_to_en"
        return [value.replace("订单", "Order").replace("数量", "Quantity") for value in values]

    result = translate_snapshot(
        _snapshot(),
        settings=Settings(_env_file=None),
        requested_direction="ZH_TO_EN",
        protected_tokens=(),
        translator=translator,
    )

    translated = result.pages[0].blocks[0].normalized_text
    assert "PO-001" in translated
    assert "0012" in translated
    assert translated.startswith("Order")


def test_pdf_translation_includes_table_cells_in_one_to_one_units() -> None:
    received = []

    def translator(values, _direction):
        received.extend(values)
        return [f"Translated {value}" for value in values]

    result = translate_snapshot(
        _table_snapshot(),
        settings=Settings(_env_file=None),
        requested_direction="EN_TO_ZH",
        protected_tokens=(),
        translator=translator,
    )

    assert len(received) == 2
    values = [cell.normalized_value for cell in result.pages[0].tables[0].cells]
    assert values[0].startswith("Translated ")
    assert "0012" in values[0]


def test_office_renderer_uses_temporary_profile_and_validates_output(
    monkeypatch,
) -> None:
    source = BytesIO()
    document = Document()
    document.add_paragraph("受限 Office 渲染")
    document.save(source)
    monkeypatch.setattr(office_pdf_renderer.shutil, "which", lambda _value: "libreoffice")
    monkeypatch.setattr(office_pdf_renderer, "_validate_fonts", lambda _value: None)

    def run(command, **_kwargs):
        output_dir = Path(command[command.index("--outdir") + 1])
        (output_dir / "source.pdf").write_bytes(_pdf_bytes())
        assert any(value.startswith("-env:UserInstallation=file:") for value in command)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(office_pdf_renderer.subprocess, "run", run)
    result = office_pdf_renderer.render_docx_to_pdf(
        source.getvalue(),
        "订单.docx",
        command="libreoffice",
    )

    assert result.page_count == 1
    assert result.blank_page_count == 1
    assert result.output_file_name == "订单_转换结果.pdf"
    assert len(PdfReader(BytesIO(result.content)).pages) == 1


def test_office_font_preflight_fails_with_stable_code(monkeypatch) -> None:
    source = BytesIO()
    document = Document()
    run = document.add_paragraph().add_run("custom font")
    run.font.name = "FactoryPrivateFont"
    document.save(source)
    monkeypatch.setattr(office_pdf_renderer, "_installed_fonts", lambda: frozenset())

    with pytest.raises(office_pdf_renderer.OfficePdfRenderError) as captured:
        office_pdf_renderer._validate_fonts(source.getvalue())

    assert captured.value.code == "DOCUMENT_FONT_MISSING"


def test_office_font_preflight_ignores_east_asia_language_metadata(
    monkeypatch,
) -> None:
    source = BytesIO()
    document = Document()
    run = document.add_paragraph().add_run("language metadata is not a font")
    run.font.name = "Noto Sans CJK SC"
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Noto Sans CJK SC")
    language = OxmlElement("w:lang")
    language.set(qn("w:eastAsia"), "en-US")
    run._element.get_or_add_rPr().append(language)
    document.save(source)

    requested_fonts = office_pdf_renderer._requested_fonts(source.getvalue())
    assert "en-US" not in requested_fonts
    assert "Noto Sans CJK SC" in requested_fonts
    monkeypatch.setattr(
        office_pdf_renderer,
        "_installed_fonts",
        lambda: frozenset({"noto sans cjk sc", "dejavu sans mono"}),
    )
    office_pdf_renderer._validate_fonts(source.getvalue())


def test_qwen_document_provider_uses_responses_file_input_without_storage() -> None:
    settings = Settings(
        _env_file=None,
        ai_document_cloud_ocr_enabled=True,
        ai_region="cn-beijing",
        ai_workspace_id="workspace-test",
        dashscope_api_key="test-secret",
        ai_document_signed_file_service_url="https://signer.example.test",
        ai_document_signed_file_service_token="broker-secret",
        ai_document_signed_file_allowed_hosts="lease.example.test",
    )
    calls = []

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return {
                "output": [
                    {
                        "content": [
                            {
                                "ocr_result": {
                                    "pages": [
                                        {
                                            "page_number": 1,
                                            "blocks": [
                                                {
                                                    "text": "订单 0012",
                                                    "bbox": [0.1, 0.1, 0.8, 0.2],
                                                    "confidence": 0.96,
                                                }
                                            ],
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }

    class Client:
        responses = Responses()

    class SignedSource:
        revoked = False

        def create(self, **kwargs):
            assert kwargs["ttl_seconds"] == 300
            return SignedFileLease(
                lease_id="doclease-" + "1" * 32,
                file_url="https://lease.example.test/document.pdf?token=secret",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
                sha256=kwargs["sha256"],
                size_bytes=len(kwargs["data"]),
            )

        def revoke(self, _lease):
            self.revoked = True

    signed_source = SignedSource()
    provider = QwenDocumentProvider(
        settings,
        signed_file_source=signed_source,
        client=Client(),
    )
    result = provider.parse_pdf(
        artifact_id="aiart-" + "a" * 32,
        sha256="b" * 64,
        filename="source.pdf",
        data=_pdf_bytes(),
        page_count=1,
    )

    assert result.pages[0].blocks[0].text == "订单 0012"
    assert calls[0]["model"] == "qwen3.5-ocr"
    assert calls[0]["store"] is False
    assert calls[0]["input"][0]["content"][0]["type"] == "input_file"
    assert signed_source.revoked is True
    assert get_document_provider_status(settings).available is True


def test_qwen_document_parser_accepts_single_page_processed_text_only() -> None:
    result = _parse_result(
        {"processed_text": "  订单 0012  "},
        expected_pages=1,
    )

    assert result.pages[0].page_number == 1
    assert result.pages[0].blocks[0].text == "订单 0012"

    with pytest.raises(QwenDocumentError) as captured:
        _parse_result({"processed_text": "ambiguous pages"}, expected_pages=2)

    assert captured.value.code == "DOCUMENT_OCR_SCHEMA_INVALID"


def test_qwen_document_parser_normalizes_zero_based_layout_pages() -> None:
    result = _parse_result(
        {
            "layouts": [
                {
                    "pageNum": 0,
                    "blocks": [{"text": "订单"}, {"text": " 0012 "}],
                    "text": "订单 0012",
                },
                {"pageNum": 1, "blocks": [], "text": "第二页"},
            ]
        },
        expected_pages=2,
    )

    assert [page.page_number for page in result.pages] == [1, 2]
    assert [block.text for block in result.pages[0].blocks] == ["订单", "0012"]
    assert result.pages[1].blocks[0].text == "第二页"

    with pytest.raises(QwenDocumentError) as captured:
        _parse_result(
            {"layouts": [{"pageNum": 1, "text": "missing page"}]},
            expected_pages=2,
        )

    assert captured.value.code == "DOCUMENT_OCR_PAGE_MISMATCH"


def test_qwen_extractor_chunks_51_pages_and_restores_global_page_numbers() -> None:
    snapshot = DocumentSnapshot(
        source_artifact_id="aiart-" + "a" * 32,
        source_sha256="b" * 64,
        page_count=51,
        pages=tuple(
            DocumentPageSnapshot(
                page_number=page_number,
                width=612,
                height=792,
                extraction_route="LOCAL_OCR",
            )
            for page_number in range(1, 52)
        ),
    )
    calls = []

    class Provider:
        def parse_pdf(self, **kwargs):
            calls.append(kwargs["page_count"])
            return QwenDocumentParseResult(
                pages=tuple(
                    QwenDocumentPage(
                        page_number=page_number,
                        blocks=(
                            QwenDocumentBlock(
                                text=f"chunk-page-{page_number}",
                                confidence=0.95,
                            ),
                        ),
                    )
                    for page_number in range(1, kwargs["page_count"] + 1)
                )
            )

    result = enhance_snapshot_with_qwen(
        snapshot,
        data=_pdf_bytes(51),
        artifact_id=snapshot.source_artifact_id,
        filename="large.pdf",
        provider=Provider(),
    )

    assert calls == [50, 1]
    assert result.pages[49].blocks[0].block_id == "p50-b1"
    assert result.pages[50].blocks[0].block_id == "p51-b1"
    assert result.pages[50].blocks[0].raw_text == "chunk-page-1"


def test_qwen_reconcile_is_closed_and_never_drops_leading_zeroes() -> None:
    snapshot = _table_snapshot()
    applied = apply_reconcile_result(
        snapshot,
        ReconcileResult(
            revisions=(
                CellRevision(
                    cell_id="table-1-r1-c1",
                    normalized_value="12",
                    value_type="INTEGER",
                    confidence=0.99,
                ),
                CellRevision(
                    cell_id="table-1-r1-c2",
                    normalized_value="42.00",
                    value_type="DECIMAL",
                    confidence=0.95,
                ),
            )
        ),
    )

    first, second = applied.pages[0].tables[0].cells
    assert first.normalized_value == "0012"
    assert [reason.value for reason in first.review_reasons] == [
        "LEADING_ZERO_IDENTIFIER"
    ]
    assert second.value_type.value == "DECIMAL"
    assert [source.value for source in second.sources][-1] == "QWEN_RECONCILE"

    settings = Settings(
        _env_file=None,
        ai_document_reconcile_enabled=True,
        ai_region="cn-beijing",
        ai_workspace_id="workspace-test",
        dashscope_api_key="test-secret",
    )
    calls = []

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return type("Response", (), {"output_text": '{"revisions":[]}'})()

    client = type("Client", (), {"responses": Responses()})()
    result = QwenReconcileProvider(settings, client=client).reconcile(snapshot)
    assert result.revisions == ()
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert "tools" not in calls[0]
    assert "exactly one JSON object" in calls[0]["input"][0]["content"]
    assert "revisions array" in calls[0]["input"][0]["content"]
