from app.api.ai import get_ai_current_user
from app.core.config import settings
from app.main import app
from app.services.ai.context_builder import available_contexts
from fastapi.testclient import TestClient
from test_ai_conversation_context import _user


def test_context_options_come_from_current_authorization() -> None:
    allowed = available_contexts(_user(), factory_scope="huaxing")
    assert [item.page_context.module_id for item in allowed] == ["injection-scheduling"]
    assert allowed[0].display_label == "注塑排产"
    assert "injection_scheduling" in allowed[0].tool_groups

    assert available_contexts(_user(permission=False), factory_scope="huaxing") == ()
    assert available_contexts(_user(), factory_scope="unknown") == ()


def test_context_options_api_is_feature_gated_and_factory_scoped(monkeypatch) -> None:
    user_holder = {"value": _user()}
    app.dependency_overrides[get_ai_current_user] = lambda: user_holder["value"]
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_pilot_enabled", True)
    monkeypatch.setattr(settings, "ai_pilot_user_ids", "context-owner")
    monkeypatch.setattr(settings, "ai_pilot_factory_ids", "huaxing")
    monkeypatch.setattr(settings, "ai_runtime_disable_path", "")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "ai_conversations_enabled", True)
    try:
        client = TestClient(app)
        monkeypatch.setattr(settings, "ai_conversation_context_enabled", False)
        assert (
            client.get("/api/ai/context-options?factory_id=huaxing").status_code == 404
        )

        monkeypatch.setattr(settings, "ai_conversation_context_enabled", True)
        response = client.get("/api/ai/context-options?factory_id=huaxing")
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["module_id"] == "injection-scheduling"
        assert (
            client.get("/api/ai/context-options?factory_id=huakang-a").status_code
            == 403
        )

        user_holder["value"] = _user(permission=False)
        assert client.get("/api/ai/context-options?factory_id=huaxing").json() == {
            "items": []
        }
    finally:
        app.dependency_overrides.clear()
