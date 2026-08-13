import importlib
import json
from pathlib import Path

from test_ai_api import (
    chat_payload,
    login_admin,
    make_client,
    parse_sse,
    vision_chat_payload,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _normalized_sse(response) -> list[dict[str, object]]:
    events = parse_sse(response.text)
    normalized = []
    for sequence, event in enumerate(events, start=1):
        data = event["data"]
        assert event["event"] == data["type"]
        assert data["schema_version"] == "1"
        assert data["sequence"] == sequence
        assert data["timestamp"].endswith("Z")
        assert set(data) == {
            "schema_version",
            "request_id",
            "sequence",
            "type",
            "timestamp",
            "payload",
        }
        normalized.append({"type": data["type"], "payload": data["payload"]})
    terminal_types = [
        item["type"]
        for item in normalized
        if item["type"] in {"error", "response.completed"}
    ]
    assert len(terminal_types) == 1
    return normalized


def test_v1_json_golden_and_nif_runtime_default_off(monkeypatch) -> None:
    fixture = _fixture("ai_legacy_responses_v1.json")

    with make_client(monkeypatch, AI_NIF_RUNTIME_ENABLED="false") as client:
        config_module = importlib.import_module("app.core.config")
        schemas = importlib.import_module("app.schemas.ai")
        assert config_module.settings.ai_nif_runtime_enabled is False
        assert config_module.settings.ai_provider_capability_router_enabled is False
        assert schemas.AIChatRequest.model_validate(
            fixture["chat_request"]
        ).model_dump(mode="json") == fixture["chat_request"]

        assert client.get("/api/ai/capabilities").status_code == fixture[
            "http_errors"
        ]["anonymous_status"]
        assert client.post(
            "/api/ai/responses",
            json=fixture["chat_request"],
        ).status_code == fixture["http_errors"]["anonymous_status"]

        login_admin(client)
        capabilities = client.get("/api/ai/capabilities")
        disabled = client.post("/api/ai/responses", json=fixture["chat_request"])
        nif_endpoint = client.post(
            "/api/ai/capabilities/context",
            json={"page_context": None},
        )
        action_execute = client.post(
            "/api/ai/action-confirmations/missing/execute",
            json={
                "factory_id": "huaxing",
                "expected_args_hash": "0" * 64,
                "execution_request_id": "legacy-contract-request",
            },
        )

    assert capabilities.json() == fixture["capabilities_disabled"]
    assert disabled.status_code == fixture["http_errors"]["disabled"]["status"]
    assert disabled.json() == fixture["http_errors"]["disabled"]["body"]
    assert nif_endpoint.status_code == 404
    assert action_execute.status_code == fixture["action_boundary"][
        "configured_off_status"
    ]


def test_v1_direct_and_tool_sse_match_golden_with_flag_off(monkeypatch) -> None:
    response_fixture = _fixture("ai_legacy_responses_v1.json")
    sse_fixture = _fixture("ai_legacy_sse_v1.json")

    with make_client(
        monkeypatch,
        AI_ENABLED="true",
        AI_NIF_RUNTIME_ENABLED="false",
        AI_PROVIDER="fake",
        AI_DEFAULT_MODEL="fake-model",
    ) as client:
        login_admin(client)
        capabilities = client.get("/api/ai/capabilities")
        direct = client.post("/api/ai/responses", json=chat_payload())

        ai_api = importlib.import_module("app.api.ai")
        fake_module = importlib.import_module("app.services.ai.providers.fake")
        tool_provider = fake_module.FakeProvider(scenario="tool")
        monkeypatch.setattr(
            ai_api,
            "build_provider",
            lambda _settings, require_vision=False: tool_provider,
        )
        tool_response = client.post("/api/ai/responses", json=chat_payload())

    assert capabilities.json() == response_fixture["capabilities_fake_pilot"]
    assert _normalized_sse(direct) == sse_fixture["direct_text"]
    assert _normalized_sse(tool_response) == sse_fixture["tool_round"]
    assert tool_provider.stream_calls == 2
    assert tool_provider.closed is True
    assert all(request.model == "fake-model" for request in tool_provider.requests)


def test_named_fake_provider_failure_eof_and_truncation_are_repeatable(
    monkeypatch,
) -> None:
    scenarios = _fixture("ai_legacy_sse_v1.json")["named_scenarios"]

    with make_client(
        monkeypatch,
        AI_ENABLED="true",
        AI_NIF_RUNTIME_ENABLED="false",
        AI_PROVIDER="fake",
        AI_DEFAULT_MODEL="fake-model",
    ) as client:
        login_admin(client)
        ai_api = importlib.import_module("app.api.ai")
        fake_module = importlib.import_module("app.services.ai.providers.fake")

        for scenario_name in ("failure", "eof", "truncated"):
            provider = fake_module.FakeProvider(scenario=scenario_name)
            monkeypatch.setattr(
                ai_api,
                "build_provider",
                lambda _settings, require_vision=False, provider=provider: provider,
            )
            response = client.post("/api/ai/responses", json=chat_payload())
            events = _normalized_sse(response)
            expected = scenarios[scenario_name]

            assert [event["type"] for event in events] == expected["event_types"]
            assert events[-1]["type"] == expected["terminal"]
            if "error_code" in expected:
                assert events[-1]["payload"]["code"] == expected["error_code"]
            if "delta_chars" in expected:
                delta = next(
                    event["payload"]["delta"]
                    for event in events
                    if event["type"] == "message.delta"
                )
                assert len(delta) == expected["delta_chars"]
            assert provider.closed is True


def test_default_tool_registry_and_action_execute_boundary_match_golden() -> None:
    fixture = _fixture("ai_legacy_responses_v1.json")
    registry_module = importlib.import_module("app.services.ai.tool_registry")
    action_module = importlib.import_module("app.services.ai.action_registry")

    default_registry = registry_module.build_default_tool_registry()
    controlled_registry = registry_module.build_default_tool_registry(
        controlled_apply_enabled=True
    )
    expected_specs = fixture["tool_registry"]["default"]
    actual_specs = [
        {
            "name": spec.name,
            "group": spec.tool_group,
            "risk": spec.risk_level.value,
        }
        for spec in default_registry.specs
    ]

    assert len(default_registry.specs) == fixture["tool_registry"]["default_count"]
    assert actual_specs == expected_specs
    assert len(controlled_registry.specs) == fixture["tool_registry"][
        "controlled_apply_count"
    ]
    proposal = fixture["tool_registry"]["controlled_apply_proposal"]
    proposal_spec = controlled_registry.resolve(proposal["name"])
    assert proposal_spec is not None
    assert {
        "name": proposal_spec.name,
        "group": proposal_spec.tool_group,
        "risk": proposal_spec.risk_level.value,
    } == proposal
    execute_handler = fixture["action_boundary"]["non_model_callable_execute_handler"]
    assert default_registry.resolve(execute_handler) is None
    assert controlled_registry.resolve(execute_handler) is None
    assert action_module.build_default_action_registry().resolve(execute_handler) is not None


def test_vision_golden_never_sends_tools_or_replays_provider(monkeypatch) -> None:
    contract = _fixture("ai_legacy_responses_v1.json")["vision_request"]
    with make_client(
        monkeypatch,
        APP_ENV="test",
        AI_ENABLED="true",
        AI_NIF_RUNTIME_ENABLED="false",
        AI_PROVIDER="fake",
        AI_DEFAULT_MODEL="fake-model",
        AI_VISION_MODEL="qwen3.7-plus",
        AI_CLOUD_VISION_ENABLED="true",
        AI_TEST_FAKE_VISION_ENABLED="true",
    ) as client:
        login_admin(client)
        ai_api = importlib.import_module("app.api.ai")
        fake_module = importlib.import_module("app.services.ai.providers.fake")
        provider = fake_module.FakeProvider(scenario="tool")
        monkeypatch.setattr(
            ai_api,
            "build_provider",
            lambda _settings, require_vision=False: provider,
        )
        payload, _, _ = vision_chat_payload()
        response = client.post("/api/ai/responses", json=payload)

    events = _normalized_sse(response)
    assert [event["type"] for event in events] == contract[
        "unexpected_tool_event_types"
    ]
    assert events[-1]["payload"]["code"] == contract[
        "unexpected_tool_error_code"
    ]
    assert provider.stream_calls == contract["max_provider_calls"]
    assert len(provider.requests[0].tools) == contract["provider_tool_count"]


def test_context_capability_lists_only_server_validated_available_tools(
    monkeypatch,
) -> None:
    context = {
        "route_name": "injection-scheduling-v2",
        "path": "/modules/production/injection-scheduling",
        "factory_id": "huaxing",
        "module_id": "injection-scheduling",
        "selected_entity": None,
    }
    with make_client(
        monkeypatch,
        AI_ENABLED="true",
        AI_NIF_RUNTIME_ENABLED="true",
        AI_PROVIDER="fake",
        AI_DEFAULT_MODEL="fake-model",
        AI_CONTROLLED_APPLY_ENABLED="false",
    ) as client:
        login_admin(client)
        missing = client.post(
            "/api/ai/capabilities/context",
            json={"page_context": None},
        )
        allowed = client.post(
            "/api/ai/capabilities/context",
            json={"page_context": context},
        )
        invalid = client.post(
            "/api/ai/capabilities/context",
            json={
                "page_context": {
                    **context,
                    "path": "/modules/sales-business/internal-quote-desk",
                }
            },
        )

    assert missing.status_code == 200
    assert missing.json()["context_status"] == "MISSING"
    assert missing.json()["available_tools"] == ["identity.get_current_context"]
    assert missing.json()["max_autonomy_level"] == "L1"

    assert allowed.status_code == 200
    assert allowed.json()["contract_version"] == "2"
    assert allowed.json()["context_status"] == "ALLOWED"
    assert allowed.json()["available_tool_groups"] == [
        "identity",
        "injection_scheduling",
        "module_knowledge",
    ]
    assert "injection_scheduling.generate_preview" in allowed.json()[
        "available_tools"
    ]
    assert "injection_scheduling.propose_apply" not in allowed.json()[
        "available_tools"
    ]
    assert allowed.json()["feature_flags"]["controlled_apply_configured"] is False
    assert allowed.json()["max_autonomy_level"] == "L2"

    assert invalid.status_code == 200
    assert invalid.json()["context_status"] == "INVALID"
    assert invalid.json()["reason_code"] == "AI_INVALID_PAGE_CONTEXT"
    assert invalid.json()["available_tools"] == []


def test_context_capability_proposal_requires_flag_page_and_permission(
    monkeypatch,
) -> None:
    context = {
        "route_name": "injection-scheduling-v2",
        "path": "/modules/production/injection-scheduling",
        "factory_id": "huaxing",
        "module_id": "injection-scheduling",
        "selected_entity": None,
    }
    with make_client(
        monkeypatch,
        AI_ENABLED="true",
        AI_NIF_RUNTIME_ENABLED="true",
        AI_PROVIDER="fake",
        AI_DEFAULT_MODEL="fake-model",
        AI_CONTROLLED_APPLY_ENABLED="true",
    ) as client:
        login_admin(client)
        ai_api = importlib.import_module("app.api.ai")
        auth_module = importlib.import_module("app.services.auth")
        allowed = client.post(
            "/api/ai/capabilities/context",
            json={"page_context": context},
        )

        deny_grant = auth_module.AuthGrantContext(
            role_id="role-scheduling-reader",
            role_name="排产读取",
            factory_id="huaxing",
            department="production",
            permissions=frozenset(
                {"injection_scheduling:read", "injection_scheduling:edit"}
            ),
            binding_id="grant-scheduling-reader",
        )
        denied_user = auth_module.AuthContext(
            id="user-admin",
            username="denied-pilot",
            display_name="显式拒绝测试用户",
            roles=("测试",),
            role_codes=("test",),
            permissions=frozenset(
                {"injection_scheduling:read", "injection_scheduling:edit"}
            ),
            factory_scopes=("huaxing",),
            department_scopes=("production",),
            grants=(deny_grant,),
            overrides=(
                auth_module.AuthOverrideContext(
                    id="deny-scheduling-read",
                    permission_code="injection_scheduling:read",
                    effect="deny",
                    factory_id="huaxing",
                    department="production",
                ),
            ),
            active_permission_codes=frozenset(
                {"injection_scheduling:read", "injection_scheduling:edit"}
            ),
        )
        client.app.dependency_overrides[ai_api.get_ai_current_user] = lambda: denied_user
        denied = client.post(
            "/api/ai/capabilities/context",
            json={"page_context": context},
        )

    assert "injection_scheduling.propose_apply" in allowed.json()["available_tools"]
    assert allowed.json()["feature_flags"]["controlled_apply_configured"] is True
    assert "injection_scheduling.apply_preview_run" not in allowed.json()[
        "available_tools"
    ]
    assert denied.status_code == 200
    assert denied.json()["context_status"] == "DENIED"
    assert denied.json()["available_tools"] == []
