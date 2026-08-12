import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api.customer_order import _read_po_uploads, _validate_upload


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


def test_validate_upload_rejects_macos_appledouble_file_with_clear_message():
    with pytest.raises(HTTPException) as exc_info:
        _validate_upload(
            _upload("._RR-4500002299.pdf", b"\x00\x05Mac OS X"),
            kind="PO",
            supported=(".pdf",),
        )

    assert exc_info.value.status_code == 400
    assert "Mac 解压产生的隐藏资源文件" in exc_info.value.detail
    assert "不带“._”前缀" in exc_info.value.detail


def test_batch_upload_ignores_macos_metadata_when_real_po_is_also_present():
    uploads = [
        _upload("__MACOSX/银辉PO/._RR-4500002299.pdf", b"appledouble"),
        _upload("RR-4500002299.pdf", b"%PDF-1.7\nreal"),
    ]

    result = asyncio.run(_read_po_uploads(uploads, supported=(".pdf",)))

    assert result == [("RR-4500002299.pdf", b"%PDF-1.7\nreal")]


def test_batch_upload_rejects_selection_containing_only_macos_metadata():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            _read_po_uploads(
                [_upload("._RR-4500002299.pdf", b"appledouble")],
                supported=(".pdf",),
            )
        )

    assert exc_info.value.status_code == 400
    assert "不是真实 PO" in exc_info.value.detail
