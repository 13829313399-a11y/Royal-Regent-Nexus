from app.main import app


def test_legacy_synchronous_tools_stay_retired():
    paths = set(app.openapi()["paths"])
    assert "/api/tools/jobs" in paths
    assert "/api/tools/uploads" in paths
    assert "/api/tools/pdf-to-excel" not in paths
    assert "/api/tools/pdf-rename/execute" not in paths
    assert "/health" in paths
    assert "/api/pricing/translate-descriptions" in paths
