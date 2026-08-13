from __future__ import annotations

import io
import zipfile

import pytest
from app.models.ai_artifact import AIArtifact
from app.services.ai.artifacts.scanner import FakeArtifactScanner
from app.services.ai.artifacts.service import (
    ArtifactInvalidError,
    ArtifactScannerFailedError,
    create_artifact,
)
from app.services.ai.artifacts.storage import FakeArtifactStorage
from app.services.ai.artifacts.validation import (
    ArtifactValidationError,
    validate_artifact_upload,
)
from openpyxl import Workbook
from PIL import Image
from pypdf import PdfWriter
from tests.ai_artifact_helpers import (
    NOW,
    artifact_database,
    artifact_settings,
    artifact_user,
    csv_bytes,
    png_bytes,
)


def _xlsx_bytes() -> bytes:
    output = io.BytesIO()
    workbook = Workbook()
    workbook.active.append(["订单", "数量"])
    workbook.active.append(["A-001", 12])
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


def _pdf_bytes(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ("filename", "mime_type", "data", "code"),
    [
        ("fake.pdf", "application/pdf", csv_bytes(), "AI_ARTIFACT_MAGIC_MISMATCH"),
        ("fake.csv", "application/pdf", csv_bytes(), "AI_ARTIFACT_MIME_MISMATCH"),
        ("empty.csv", "text/csv", b"", "AI_ARTIFACT_EMPTY"),
        ("legacy.xls", "application/vnd.ms-excel", b"xls", "AI_ARTIFACT_TYPE_NOT_ALLOWED"),
        ("macro.xlsm", "application/octet-stream", b"PK", "AI_ARTIFACT_TYPE_NOT_ALLOWED"),
    ],
)
def test_extension_mime_magic_and_empty_fail_closed(
    filename, mime_type, data, code
) -> None:
    with pytest.raises(ArtifactValidationError) as exc_info:
        validate_artifact_upload(
            filename=filename, declared_mime_type=mime_type, data=data
        )
    assert exc_info.value.code == code


def test_valid_workbook_and_unicode_traversal_filename_are_safely_normalized() -> None:
    validated = validate_artifact_upload(
        filename="../../客户／订单.xlsx",
        declared_mime_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        data=_xlsx_bytes(),
    )
    assert validated.original_filename == "订单.xlsx"
    assert validated.normalized_extension == ".xlsx"
    assert validated.content_class.value == "WORKBOOK"


def test_ooxml_zip_bomb_traversal_macro_and_external_relationship_are_rejected() -> None:
    base = {
        "[Content_Types].xml": b"<Types/>",
        "xl/workbook.xml": b"<workbook/>",
    }
    cases = (
        ({**base, "xl/worksheets/sheet1.xml": b"A" * 200_000}, "AI_ARTIFACT_ZIP_RATIO"),
        ({**base, "../escape.xml": b"x"}, "AI_ARTIFACT_ZIP_PATH"),
        ({**base, "xl/vbaProject.bin": b"macro"}, "AI_ARTIFACT_ACTIVE_CONTENT"),
        (
            {
                **base,
                "xl/_rels/workbook.xml.rels": (
                    b'<Relationships><Relationship TargetMode="External"/></Relationships>'
                ),
            },
            "AI_ARTIFACT_ACTIVE_CONTENT",
        ),
    )
    for entries, expected_code in cases:
        with pytest.raises(ArtifactValidationError) as exc_info:
            validate_artifact_upload(
                filename="unsafe.xlsx",
                declared_mime_type=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                data=_zip_bytes(entries),
            )
        assert exc_info.value.code == expected_code


def test_pdf_page_limit_and_image_pixel_limit() -> None:
    with pytest.raises(ArtifactValidationError) as pdf_error:
        validate_artifact_upload(
            filename="too-many.pdf",
            declared_mime_type="application/pdf",
            data=_pdf_bytes(201),
        )
    assert pdf_error.value.code == "AI_ARTIFACT_PAGE_LIMIT"

    output = io.BytesIO()
    with Image.new("1", (4001, 4000)) as image:
        image.save(output, format="PNG")
    with pytest.raises(ArtifactValidationError) as image_error:
        validate_artifact_upload(
            filename="too-large.png",
            declared_mime_type="image/png",
            data=output.getvalue(),
        )
    assert image_error.value.code == "AI_ARTIFACT_PIXEL_LIMIT"


def test_image_container_trailing_payload_is_rejected() -> None:
    with pytest.raises(ArtifactValidationError) as exc_info:
        validate_artifact_upload(
            filename="image.png",
            declared_mime_type="image/png",
            data=png_bytes() + b"hidden-payload",
        )
    assert exc_info.value.code == "AI_ARTIFACT_MAGIC_MISMATCH"


@pytest.mark.parametrize("outcome", ["unavailable", "rejected"])
def test_scanner_unavailable_or_rejected_never_registers_artifact(outcome) -> None:
    db = artifact_database()
    try:
        expected = ArtifactScannerFailedError if outcome == "unavailable" else ArtifactInvalidError
        with pytest.raises(expected):
            create_artifact(
                db,
                user=artifact_user(),
                factory_id="huaxing",
                classification="INTERNAL",
                filename="订单.csv",
                declared_mime_type="text/csv",
                data=csv_bytes(),
                storage=FakeArtifactStorage(),
                scanner=FakeArtifactScanner(outcome),
                settings=artifact_settings(),
                allowed_factory_ids=frozenset({"huaxing"}),
                now=NOW,
            )
        assert db.query(AIArtifact).count() == 0
    finally:
        db.close()
