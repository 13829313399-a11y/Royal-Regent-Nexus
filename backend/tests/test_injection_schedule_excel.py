from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import HTTPException

from app.services.injection_schedule_excel import inspect_xlsx_upload


def make_xlsx_like_archive(
    extra_members: dict[str, bytes] | None = None,
) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", b"<workbook/>")
        for name, content in (extra_members or {}).items():
            archive.writestr(name, content)
    return stream.getvalue()


def test_xlsx_upload_rejects_wrong_extension_and_invalid_zip():
    with pytest.raises(HTTPException) as wrong_extension:
        inspect_xlsx_upload(b"not-an-xlsx", "schedule.xls")
    assert wrong_extension.value.status_code == 415

    with pytest.raises(HTTPException) as invalid_zip:
        inspect_xlsx_upload(b"not-an-xlsx", "schedule.xlsx")
    assert invalid_zip.value.status_code == 400


def test_xlsx_upload_rejects_zip_path_traversal():
    payload = make_xlsx_like_archive({"../outside.xml": b"unsafe"})
    with pytest.raises(HTTPException) as rejected:
        inspect_xlsx_upload(payload, "schedule.xlsx")
    assert rejected.value.status_code == 400
    assert "不安全" in str(rejected.value.detail)


def test_xlsx_upload_rejects_member_count_and_compression_bombs():
    too_many_members = make_xlsx_like_archive(
        {f"xl/worksheets/sheet-{index}.xml": b"x" for index in range(201)}
    )
    with pytest.raises(HTTPException) as member_rejected:
        inspect_xlsx_upload(too_many_members, "schedule.xlsx")
    assert member_rejected.value.status_code == 413
    assert member_rejected.value.detail["code"] == "xlsx_too_many_members"

    compressed_bomb = make_xlsx_like_archive(
        {"xl/worksheets/sheet1.xml": b"0" * (2 * 1024 * 1024)}
    )
    with pytest.raises(HTTPException) as ratio_rejected:
        inspect_xlsx_upload(compressed_bomb, "schedule.xlsx")
    assert ratio_rejected.value.status_code == 413
    assert "压缩比" in str(ratio_rejected.value.detail)
