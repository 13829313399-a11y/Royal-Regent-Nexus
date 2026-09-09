from io import BytesIO

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.api import pdf_rename as routes
from app.core.config import settings
from app.services.auth import get_current_user


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "document_tools_enabled", True)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("factory", ["group", "unknown"])
def test_invalid_factory_cannot_load_rules_or_process(client, factory):
    response = client.get("/api/tools/pdf-rename/rules", params={"factory_id": factory})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PDF_RENAME_FACTORY_INVALID"
    for endpoint in ("preview", "execute"):
        response = client.post(
            f"/api/tools/pdf-rename/{endpoint}",
            data={"factory_id": factory, "rule_id": "buzzbee-inspection", "preview_token": "old"},
            files={"pdf_files": ("a.pdf", b"%PDF-test", "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "PDF_RENAME_FACTORY_INVALID"


def test_gate_applies_to_catalog_preview_and_execute(client, monkeypatch):
    monkeypatch.setattr(settings, "document_tools_enabled", False)
    responses = [client.get("/api/tools/pdf-rename/rules", params={"factory_id": "huaxing"})]
    for endpoint in ("preview", "execute"):
        responses.append(client.post(
            f"/api/tools/pdf-rename/{endpoint}",
            data={"factory_id": "huaxing", "rule_id": "buzzbee-inspection", "preview_token": "old"},
            files={"pdf_files": ("a.pdf", b"%PDF-test", "application/pdf")},
        ))
    assert all(response.status_code == 503 for response in responses)
    assert all(response.json()["detail"]["code"] == "DOCUMENT_TOOLS_DISABLED" for response in responses)


@pytest.mark.parametrize(("name", "content", "code", "status"), [
    ("a.docx", b"%PDF-test", "DOCUMENT_FILE_TYPE_UNSUPPORTED", 400),
    ("a.pdf", b"", "DOCUMENT_FILE_EMPTY", 400),
    ("a.pdf", b"not a PDF", "DOCUMENT_FILE_SIGNATURE_INVALID", 400),
])
def test_upload_errors_are_structured(client, name, content, code, status):
    response = client.post(
        "/api/tools/pdf-rename/preview",
        data={"factory_id": "huaxing", "rule_id": "buzzbee-inspection"},
        files={"pdf_files": (name, content, "application/pdf")},
    )
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


def test_pdf_read_is_bounded_to_limit_plus_one(monkeypatch):
    import asyncio

    monkeypatch.setattr(routes, "MAX_PDF_RENAME_FILE_BYTES", 12)
    source = UploadFile(filename="large.pdf", file=BytesIO(b"%PDF-" + b"x" * 100))
    with pytest.raises(HTTPException) as error:
        asyncio.run(routes._read_pdf(source))
    assert source.file.tell() == 13
    assert error.value.status_code == 413
    assert error.value.detail["code"] == "DOCUMENT_FILE_TOO_LARGE"


def test_batch_limits_are_checked_before_ocr(client, monkeypatch):
    data = {"factory_id": "huaxing", "rule_id": "buzzbee-inspection"}
    files = [("pdf_files", (f"{i}.pdf", b"%PDF-test", "application/pdf")) for i in range(2)]
    monkeypatch.setattr(routes, "MAX_PDF_RENAME_FILES", 1)
    response = client.post("/api/tools/pdf-rename/preview", data=data, files=files)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "PDF_RENAME_TOO_MANY_FILES"
    monkeypatch.setattr(routes, "MAX_PDF_RENAME_FILES", 50)
    monkeypatch.setattr(routes, "MAX_PDF_RENAME_BATCH_BYTES", 12)
    response = client.post("/api/tools/pdf-rename/preview", data=data, files=files)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "PDF_RENAME_BATCH_TOO_LARGE"


def test_requests_still_require_authentication(client):
    client.app.dependency_overrides.clear()
    response = client.get("/api/tools/pdf-rename/rules", params={"factory_id": "huaxing"})
    assert response.status_code == 401
