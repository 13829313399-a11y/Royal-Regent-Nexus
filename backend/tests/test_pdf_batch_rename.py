from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.pdf_rename import (
    NormalizedRegion,
    PdfRenameRuleBase,
    PdfRenameRuleDefinition,
    PdfRenameServiceError,
    PdfRenameSource,
    RecognizedRegionValue,
    build_pdf_rename_preview,
    execute_pdf_rename_batch,
    list_pdf_rename_rules,
)


def _pdf(width: float = 595) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=842)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class ExampleRule(PdfRenameRuleBase):
    definition = PdfRenameRuleDefinition(
        rule_id="test-fixed-region",
        label="测试固定区域",
        description="test only",
        version="1",
        regions=(
            NormalizedRegion(
                key="interval",
                label="区间名",
                page_number=1,
                left=0.1,
                top=0.1,
                right=0.5,
                bottom=0.2,
            ),
        ),
    )

    def build_interval_name(self, values):
        return values["interval"].normalized_text


def _recognizer(text: str, *, route: str = "NATIVE_TEXT"):
    def recognize(_content, region):
        return RecognizedRegionValue(
            key=region.key,
            label=region.label,
            raw_text=text,
            normalized_text=text,
            route=route,
            confidence=0.98 if route == "NATIVE_TEXT" else 0.80,
        )

    return recognize


def test_rule_catalog_exposes_draft_setup_without_enabling_it() -> None:
    rules = list_pdf_rename_rules("huaxing")
    template = next(rule for rule in rules if rule["id"] == "fixed-region-template")
    assert template["status"] == "draft"
    assert template["available"] is False
    assert "固定区域坐标" in " ".join(template["setup_checklist"])


def test_preview_builds_safe_target_and_preserves_source_bytes() -> None:
    source = PdfRenameSource("原文件.pdf", _pdf())

    preview = build_pdf_rename_preview(
        ExampleRule(),
        (source,),
        recognizer=_recognizer('2026/09:第 01 区'),
    )

    assert preview.items[0].interval_name == '2026/09:第 01 区'
    assert preview.items[0].target_file_name == "2026_09_第 01 区.pdf"
    assert preview.items[0].status == "READY"
    assert preview.error_count == 0
    assert len(preview.preview_token) == 64
    assert source.content == _pdf()


def test_preview_blocks_case_insensitive_target_collisions() -> None:
    sources = (
        PdfRenameSource("A.pdf", _pdf(595)),
        PdfRenameSource("B.pdf", _pdf(596)),
    )

    preview = build_pdf_rename_preview(
        ExampleRule(),
        sources,
        recognizer=_recognizer("SAME"),
    )

    assert preview.error_count == 2
    assert all(item.issues[-1].code == "PDF_RENAME_TARGET_COLLISION" for item in preview.items)


def test_ocr_preview_requires_explicit_review_before_zip() -> None:
    source = PdfRenameSource("扫描件.pdf", _pdf())
    rule = ExampleRule()
    recognizer = _recognizer("A区-B区", route="LOCAL_OCR")
    preview = build_pdf_rename_preview(rule, (source,), recognizer=recognizer)

    assert preview.review_count == 1
    with pytest.raises(PdfRenameServiceError, match="尚未确认"):
        execute_pdf_rename_batch(
            rule,
            (source,),
            expected_preview_token=preview.preview_token,
            recognizer=recognizer,
        )

    result = execute_pdf_rename_batch(
        rule,
        (source,),
        expected_preview_token=preview.preview_token,
        ocr_review_confirmed=True,
        recognizer=recognizer,
    )
    with ZipFile(BytesIO(result.content)) as archive:
        assert archive.namelist() == ["A区-B区.pdf"]
        assert archive.read("A区-B区.pdf") == source.content


def test_execute_rejects_a_stale_preview_token() -> None:
    source = PdfRenameSource("原文件.pdf", _pdf())
    with pytest.raises(PdfRenameServiceError) as raised:
        execute_pdf_rename_batch(
            ExampleRule(),
            (source,),
            expected_preview_token="stale",
            recognizer=_recognizer("一区"),
        )

    assert raised.value.code == "PDF_RENAME_PREVIEW_STALE"
