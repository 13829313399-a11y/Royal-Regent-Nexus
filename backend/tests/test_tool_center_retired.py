from app.main import app
from fastapi.testclient import TestClient


def test_legacy_converters_stay_retired_except_explicit_huaxing_rename():
    paths = set(app.openapi()["paths"])
    assert "/api/tools/jobs" in paths
    assert "/api/tools/uploads" in paths
    assert "/api/tools/pdf-to-excel" not in paths
    assert "/api/tools/pdf-rename/rules" in paths
    assert "/api/tools/pdf-rename/preview" in paths
    assert "/api/tools/pdf-rename/execute" in paths
    assert "/health" in paths
    assert "/api/pricing/translate-descriptions" in paths


def test_collaborative_sheets_are_retired_and_online_documents_remain():
    paths = set(app.openapi()["paths"])
    assert not any(path.startswith("/api/tools/collaborative-sheets") for path in paths)
    assert "/api/tools/online-documents" in paths
    assert "/api/tools/online-documents/recipients" in paths
    assert "/api/tools/spreadsheet-merge/inspect" in paths
    # No lifespan: this route-removal probe must never initialize a real store.
    client = TestClient(app)
    for method, suffix in (("GET", ""), ("POST", ""), ("GET", "/recipients"),
                           ("GET", "/old-task"), ("POST", "/old-task/sync"),
                           ("GET", "/old-task/download"), ("GET", "/old-task/events")):
        assert client.request(method, "/api/tools/collaborative-sheets" + suffix).status_code == 404
