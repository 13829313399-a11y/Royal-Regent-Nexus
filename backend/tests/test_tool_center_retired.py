from app.main import app


def test_public_tool_endpoints_are_not_registered():
    paths = set(app.openapi()["paths"])
    assert not any(path == "/api/tools" or path.startswith("/api/tools/") for path in paths)
    assert "/health" in paths
    assert "/api/pricing/translate-descriptions" in paths
