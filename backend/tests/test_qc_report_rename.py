import sys
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image
from pypdf import PdfWriter


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.qc_report_rename import (  # noqa: E402
    ReportRenameBatchError,
    ReportRenameGroup,
    ReportSourceFile,
    rename_report_batch,
)


def _pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _jpeg(color: str = "red") -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color).save(output, format="JPEG")
    return output.getvalue()


def _ordinary(group_id: str = "ordinary-1", **changes) -> ReportRenameGroup:
    group = ReportRenameGroup(
        group_id=group_id,
        files=(
            ReportSourceFile("任意报告名.PDF", _pdf()),
            ReportSourceFile("任意照片名.JPEG", _jpeg()),
        ),
        is_caixing=False,
        export_country="us",
        item_number=" ITEM / 001 ",
        po="001234",
        actual_inspection_date=date(2026, 8, 12),
    )
    return replace(group, **changes)


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_non_caixing_normalizes_fields_preserves_po_and_creates_zip():
    result = rename_report_batch([_ordinary()])

    assert result.successful_group_count == 1
    assert result.failed_group_count == 0
    assert list(result.output_files) == [
        "US_ITEM_001_001234_20260812.jpg",
        "US_ITEM_001_001234_20260812.pdf",
    ]
    assert result.group_results[0].base_name == "US_ITEM_001_001234_20260812"
    with ZipFile(BytesIO(result.archive_bytes)) as archive:
        assert archive.namelist() == list(result.output_files)
        assert archive.read("US_ITEM_001_001234_20260812.pdf") == _pdf()


def test_caixing_uses_required_fields_and_sequences_multiple_jpegs():
    group = ReportRenameGroup(
        group_id="caixing-1",
        files=(
            ReportSourceFile("x.jpg", _jpeg("red"), sequence=2),
            ReportSourceFile("not-an-identity.pdf", _pdf()),
            ReportSourceFile("a.jpeg", _jpeg("blue"), sequence=1),
        ),
        is_caixing=True,
        report_number="RPT: 88",
        item_number="货号 9",
        po="0007",
        quantity="01200",
        actual_inspection_date="2026-08-13",
    )

    result = rename_report_batch([group])

    assert list(result.output_files) == [
        "RPT_88_货号_9_0007_01200_20260813.pdf",
        "RPT_88_货号_9_0007_01200_20260813_01.jpg",
        "RPT_88_货号_9_0007_01200_20260813_02.jpg",
    ]
    assert result.output_files["RPT_88_货号_9_0007_01200_20260813_01.jpg"] == _jpeg("blue")
    assert result.output_files["RPT_88_货号_9_0007_01200_20260813_02.jpg"] == _jpeg("red")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"export_country": "美国"}, "COUNTRY_CODE_INVALID"),
        ({"item_number": "  "}, "FIELD_REQUIRED"),
        ({"po": 123}, "FIELD_TYPE_INVALID"),
        ({"actual_inspection_date": "20260230"}, "INSPECTION_DATE_INVALID"),
    ],
)
def test_missing_or_invalid_ordinary_fields_fail_the_whole_group(changes, code):
    result = rename_report_batch([_ordinary(**changes)])

    assert not result.group_results[0].success
    assert code in _codes(result.group_results[0])
    assert result.output_files == {}


def test_caixing_requires_report_number_and_digit_only_quantity():
    group = ReportRenameGroup(
        group_id="cx",
        files=(ReportSourceFile("x.pdf", _pdf()), ReportSourceFile("x.jpg", _jpeg())),
        is_caixing=True,
        report_number="",
        item_number="I-1",
        po="0001",
        quantity="1,200件",
        actual_inspection_date="20260812",
    )

    result = rename_report_batch([group]).group_results[0]

    assert {"FIELD_REQUIRED", "QUANTITY_INVALID"} <= _codes(result)
    assert result.files == ()


@pytest.mark.parametrize(
    ("files", "codes"),
    [
        ((ReportSourceFile("only.pdf", _pdf()),), {"JPEG_REQUIRED"}),
        ((ReportSourceFile("only.jpg", _jpeg()),), {"PDF_COUNT_INVALID"}),
        (
            (ReportSourceFile("a.pdf", _pdf()), ReportSourceFile("b.pdf", _pdf()), ReportSourceFile("x.jpg", _jpeg())),
            {"PDF_COUNT_INVALID"},
        ),
        (
            (ReportSourceFile("fake.pdf", _jpeg()), ReportSourceFile("x.jpg", _jpeg())),
            {"PDF_INVALID"},
        ),
        (
            (ReportSourceFile("x.pdf", _pdf()), ReportSourceFile("fake.jpg", _pdf())),
            {"JPEG_INVALID"},
        ),
        (
            (ReportSourceFile("x.pdf", _pdf()), ReportSourceFile("x.png", b"png")),
            {"FILE_TYPE_UNSUPPORTED", "JPEG_REQUIRED"},
        ),
    ],
)
def test_file_pair_extension_magic_and_readability_are_validated(files, codes):
    result = rename_report_batch([_ordinary(files=files)]).group_results[0]

    assert codes <= _codes(result)
    assert result.files == ()


def test_multiple_images_require_explicit_unique_positive_sequence():
    no_sequence = _ordinary(
        files=(
            ReportSourceFile("x.pdf", _pdf()),
            ReportSourceFile("1.jpg", _jpeg("red")),
            ReportSourceFile("2.jpg", _jpeg("blue")),
        )
    )
    duplicate = replace(
        no_sequence,
        group_id="duplicate-sequence",
        files=(
            ReportSourceFile("x.pdf", _pdf()),
            ReportSourceFile("1.jpg", _jpeg("red"), 1),
            ReportSourceFile("2.jpg", _jpeg("blue"), 1),
        ),
    )

    results = rename_report_batch([no_sequence, duplicate]).group_results

    assert "IMAGE_SEQUENCE_REQUIRED" in _codes(next(result for result in results if result.group_id == "ordinary-1"))
    assert "IMAGE_SEQUENCE_DUPLICATE" in _codes(next(result for result in results if result.group_id == "duplicate-sequence"))


def test_failed_group_is_atomic_while_other_groups_continue():
    bad = _ordinary("bad", files=(ReportSourceFile("only.pdf", _pdf()),))
    good = _ordinary("good", export_country="DE", item_number="X9")

    result = rename_report_batch([bad, good])

    assert result.successful_group_count == 1
    assert result.failed_group_count == 1
    assert all(name.startswith("DE_X9_") for name in result.output_files)
    assert next(group for group in result.group_results if group.group_id == "bad").files == ()


def test_case_insensitive_cross_group_target_collision_blocks_all_conflicting_groups():
    upper = _ordinary("upper", item_number="ABC")
    lower = _ordinary("lower", item_number="abc")

    result = rename_report_batch([upper, lower])

    assert result.failed_group_count == 2
    assert all("TARGET_NAME_COLLISION" in _codes(group) for group in result.group_results)
    assert result.output_files == {}


def test_windows_reserved_component_and_unicode_are_safely_normalized():
    result = rename_report_batch(
        [_ordinary(item_number="ＣＯＮ", po=" A  /  B ", export_country="gb")]
    )

    assert list(result.output_files) == [
        "GB__CON_A_B_20260812.jpg",
        "GB__CON_A_B_20260812.pdf",
    ]


def test_source_file_name_is_not_business_identity_or_fingerprint_input():
    first = _ordinary(
        files=(ReportSourceFile("客户给的名字.pdf", _pdf()), ReportSourceFile("照片1.jpeg", _jpeg()))
    )
    second = _ordinary(
        files=(ReportSourceFile("totally-different.PDF", _pdf()), ReportSourceFile("photo.JPG", _jpeg()))
    )

    first_result = rename_report_batch([first])
    second_result = rename_report_batch([second])

    assert first_result.fingerprint == second_result.fingerprint
    assert first_result.archive_bytes == second_result.archive_bytes
    assert list(first_result.output_files) == list(second_result.output_files)


def test_output_order_fingerprint_and_zip_bytes_are_deterministic():
    first = _ordinary("z-group", export_country="US")
    second = _ordinary("a-group", export_country="DE")

    one = rename_report_batch([first, second])
    two = rename_report_batch([second, first])

    assert one.fingerprint == two.fingerprint
    assert one.archive_file_name == two.archive_file_name
    assert one.archive_bytes == two.archive_bytes
    assert [result.group_id for result in one.group_results] == ["a-group", "z-group"]


def test_duplicate_group_ids_fail_without_partial_output():
    result = rename_report_batch([_ordinary("same", export_country="US"), _ordinary("same", export_country="DE")])

    assert all("GROUP_ID_DUPLICATE" in _codes(group) for group in result.group_results)
    assert result.output_files == {}


def test_empty_and_oversized_batches_are_rejected():
    with pytest.raises(ReportRenameBatchError, match="至少"):
        rename_report_batch([])

    with pytest.raises(ReportRenameBatchError, match="最多"):
        rename_report_batch([_ordinary(str(index)) for index in range(101)])
