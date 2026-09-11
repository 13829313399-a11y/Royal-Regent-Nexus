from app.main import app


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
