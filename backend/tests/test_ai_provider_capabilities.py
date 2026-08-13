import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.services.ai.orchestrator import AIOrchestrator, ValidatedChatInput
from app.services.ai.provider_factory import get_provider_status
from app.services.ai.providers import (
    DataClassification,
    FakeProvider,
    InputModality,
    ModelCapability,
    ModelCatalogError,
    OutputModality,
    ProviderError,
    ProviderErrorCode,
    ProviderErrorEvent,
    ProviderIncomplete,
    ProviderMessage,
    ProviderRefusal,
    ProviderResponseFormat,
    ProviderRetryPolicy,
    ProviderUsageEvent,
    QwenResponsesProvider,
    ReasoningPolicy,
    ResponseFormatKind,
    RetryMode,
    StorePolicy,
    ToolChoicePolicy,
    load_model_catalog,
    parse_model_catalog,
)
from app.services.ai.providers.router import (
    ProviderRoutingError,
    build_provider_request,
    resolve_provider_route,
)
from test_ai_api import login_admin, make_client


def settings(**overrides) -> Settings:
    values = {
        "app_env": "development",
        "ai_enabled": True,
        "ai_nif_runtime_enabled": True,
        "ai_provider_capability_router_enabled": True,
        "ai_provider": "qwen",
        "ai_region": "cn-beijing",
        "ai_workspace_id": "ws-catalog-test",
        "dashscope_api_key": "synthetic-key-not-a-secret",
        "ai_default_model": "qwen3.7-plus",
        "ai_vision_model": "qwen3.7-plus",
        "ai_base_url": "",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def catalog_profile(**overrides) -> dict[str, object]:
    profile = {
        "profile_id": "qwen-cn-beijing-default-v1",
        "provider": "qwen",
        "model": "qwen3.7-plus",
        "region": "cn-beijing",
        "capabilities": [
            "FAST_ROUTER",
            "GENERAL_CHAT",
            "DEEP_REASONING",
            "MULTIMODAL_GENERAL",
            "STRUCTURED_EXTRACTION",
            "TRANSLATION",
        ],
        "reasoning_efforts": {
            "FAST": "low",
            "BALANCED": "medium",
            "DEEP": "high",
        },
        "input_modalities": ["TEXT", "IMAGE"],
        "output_modalities": ["TEXT"],
        "supports_streaming": True,
        "supports_custom_tools": True,
        "supports_structured_output": True,
    }
    profile.update(overrides)
    return profile


def catalog_json(*profiles: dict[str, object], version: str = "1") -> str:
    return json.dumps({"version": version, "profiles": list(profiles)})


class AsyncEvents:
    def __init__(self, *events):
        self.events = iter(events)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def close(self):
        self.closed = True


class SequenceResponses:
    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class StatusError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"synthetic provider status {status_code}")
        self.status_code = status_code


async def collect(provider, request):
    return [event async for event in provider.stream(request)]


def qwen_provider(
    responses: SequenceResponses,
    *,
    catalog=None,
    sleeps: list[float] | None = None,
) -> QwenResponsesProvider:
    async def record_sleep(delay: float) -> None:
        if sleeps is not None:
            sleeps.append(delay)

    return QwenResponsesProvider(
        api_key="synthetic-key-not-a-secret",
        base_url=(
            "https://ws-catalog-test.cn-beijing.maas.aliyuncs.com/"
            "compatible-mode/v1"
        ),
        timeout_seconds=5,
        catalog=catalog,
        region="cn-beijing",
        sleep=record_sleep,
        client=SimpleNamespace(responses=responses),
    )


def routed_request(
    *,
    retry_policy: ProviderRetryPolicy | None = None,
    response_format: ProviderResponseFormat | None = None,
):
    current_settings = settings()
    route = resolve_provider_route(
        current_settings,
        capability=ModelCapability.GENERAL_CHAT,
        reasoning_policy=ReasoningPolicy.BALANCED,
        legacy_model=current_settings.ai_default_model,
        require_streaming=True,
    )
    return current_settings, build_provider_request(
        route,
        request_id="request-capability-v2",
        input=(ProviderMessage(role="user", content="hello"),),
        response_format=response_format,
        retry_policy=retry_policy,
        data_classification=DataClassification.INTERNAL,
    )


def test_capability_aliases_and_reasoning_policies_are_stable() -> None:
    assert [item.value for item in ModelCapability] == [
        "FAST_ROUTER",
        "GENERAL_CHAT",
        "DEEP_REASONING",
        "MULTIMODAL_GENERAL",
        "STRUCTURED_EXTRACTION",
        "DOCUMENT_OCR",
        "TRANSLATION",
        "EMBEDDING",
        "RERANK",
    ]
    assert [item.value for item in ReasoningPolicy] == ["FAST", "BALANCED", "DEEP"]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (json.dumps({"version": "1"}), "invalid_catalog_fields"),
        (catalog_json(), "missing_catalog_profiles"),
        (
            catalog_json(
                catalog_profile(),
                catalog_profile(profile_id="qwen-second-v1"),
            ),
            "duplicate_capability_alias",
        ),
        (
            catalog_json(
                catalog_profile(capabilities=["GENERAL_CHAT", "UNKNOWN_ALIAS"])
            ),
            "invalid_catalog_profile",
        ),
        (
            catalog_json(
                catalog_profile(capabilities=["GENERAL_CHAT", "DOCUMENT_OCR"])
            ),
            "prohibited_capability",
        ),
    ],
)
def test_catalog_rejects_missing_duplicate_unknown_and_prohibited_entries(
    raw: str,
    reason: str,
) -> None:
    with pytest.raises(ModelCatalogError) as exc_info:
        parse_model_catalog(raw)
    assert exc_info.value.reason == reason


def test_router_flag_off_preserves_legacy_model_reasoning_and_request_shape() -> None:
    legacy = settings(
        ai_provider_capability_router_enabled=False,
        ai_default_model="legacy-model",
        ai_reasoning_effort="xhigh",
    )
    route = resolve_provider_route(
        legacy,
        capability=ModelCapability.GENERAL_CHAT,
        reasoning_policy=ReasoningPolicy.FAST,
        legacy_model=legacy.ai_default_model,
    )
    request = build_provider_request(
        route,
        request_id="legacy-route",
        input=(ProviderMessage(role="user", content="hello"),),
        max_output_tokens=4_096,
    )

    assert route.contract_version == "1"
    assert route.model == "legacy-model"
    assert route.provider_reasoning_effort == "xhigh"
    assert request.contract_version == "1"
    assert request.model == "legacy-model"
    assert request.max_output_tokens == 4_096
    assert request.capability_alias is None
    assert request.reasoning_policy is None


def test_router_flag_on_resolves_profile_without_exposing_deferred_capability() -> None:
    current = settings(ai_provider="fake", ai_default_model="fake-model")
    route = resolve_provider_route(
        current,
        capability=ModelCapability.GENERAL_CHAT,
        reasoning_policy=ReasoningPolicy.DEEP,
        legacy_model="must-not-be-used",
        require_streaming=True,
        require_custom_tools=True,
    )
    status = get_provider_status(current)

    assert route.contract_version == "2"
    assert route.model == "fake-model"
    assert route.provider_reasoning_effort == "high"
    assert route.capability_profile == "fake-cn-beijing-default-v1"
    assert status.capability_profile == route.capability_profile
    assert status.catalog_version == "1"
    assert "GENERAL_CHAT" in status.capabilities
    assert "DOCUMENT_OCR" not in status.capabilities
    assert status.reasoning_policies == ("FAST", "BALANCED", "DEEP")


def test_router_fails_closed_on_region_mismatch() -> None:
    remote_profile = catalog_profile(
        profile_id="qwen-ap-southeast-1-v1",
        region="ap-southeast-1",
    )
    current = settings(ai_model_catalog_json=catalog_json(remote_profile))

    with pytest.raises(ProviderRoutingError) as exc_info:
        resolve_provider_route(
            current,
            capability=ModelCapability.GENERAL_CHAT,
            reasoning_policy=ReasoningPolicy.BALANCED,
            legacy_model=current.ai_default_model,
            required_region="cn-beijing",
        )
    assert exc_info.value.reason == "region_mismatch"


def test_qwen_v2_payload_maps_catalog_policies_and_forces_store_false() -> None:
    current, request = routed_request(
        response_format=ProviderResponseFormat(
            kind=ResponseFormatKind.JSON_SCHEMA,
            name="answer_v1",
            schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        )
    )
    response = SimpleNamespace(
        id="response-v2",
        status="completed",
        output_text='{"answer":"ok"}',
        output=[],
        usage=SimpleNamespace(input_tokens=4, output_tokens=2, total_tokens=6),
    )
    responses = SequenceResponses(response)
    provider = qwen_provider(responses, catalog=load_model_catalog(current))

    result = asyncio.run(provider.generate(request))

    assert result.text == '{"answer":"ok"}'
    payload = responses.calls[0]
    assert payload["model"] == "qwen3.7-plus"
    assert payload["store"] is False
    assert payload["parallel_tool_calls"] is False
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["tool_choice"] == "none"
    assert payload["text"]["format"] == {
        "type": "json_schema",
        "name": "answer_v1",
        "schema": dict(request.response_format.schema),
        "strict": True,
    }

    invalid_store = replace(request, store_policy="ALWAYS")
    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.generate(invalid_store))
    assert exc_info.value.code == ProviderErrorCode.REQUEST_FAILED
    assert len(responses.calls) == 1


@pytest.mark.parametrize("status_code", [429, 503])
def test_qwen_retries_only_safe_transient_requests_with_bounded_backoff(
    status_code: int,
) -> None:
    retry_policy = ProviderRetryPolicy(
        mode=RetryMode.SAFE_TRANSIENT,
        max_attempts=3,
        base_delay_seconds=0.01,
        max_delay_seconds=0.02,
    )
    current, request = routed_request(retry_policy=retry_policy)
    response = SimpleNamespace(
        id="response-retried",
        status="completed",
        output_text="ok",
        output=[],
        usage=None,
    )
    responses = SequenceResponses(StatusError(status_code), StatusError(status_code), response)
    sleeps: list[float] = []
    provider = qwen_provider(
        responses,
        catalog=load_model_catalog(current),
        sleeps=sleeps,
    )

    assert asyncio.run(provider.generate(request)).text == "ok"
    assert len(responses.calls) == 3
    assert sleeps == [0.01, 0.02]
    assert all(call["store"] is False for call in responses.calls)


def test_qwen_does_not_retry_auth_or_invalid_policy() -> None:
    policy = ProviderRetryPolicy(
        mode=RetryMode.SAFE_TRANSIENT,
        max_attempts=3,
    )
    current, request = routed_request(retry_policy=policy)
    responses = SequenceResponses(StatusError(401))
    provider = qwen_provider(responses, catalog=load_model_catalog(current))

    with pytest.raises(ProviderError) as auth_error:
        asyncio.run(provider.generate(request))
    assert auth_error.value.code == ProviderErrorCode.AUTHENTICATION_FAILED
    assert len(responses.calls) == 1

    invalid_region = replace(
        request,
        region_policy=replace(request.region_policy, required_region="ap-southeast-1"),
    )
    before = len(responses.calls)
    with pytest.raises(ProviderError) as policy_error:
        asyncio.run(provider.generate(invalid_region))
    assert policy_error.value.code == ProviderErrorCode.REQUEST_FAILED
    assert len(responses.calls) == before


def test_qwen_v2_standardizes_refusal_incomplete_error_and_usage_events() -> None:
    current, request = routed_request()
    catalog = load_model_catalog(current)
    refusal_response = SimpleNamespace(
        id="response-refusal",
        status="completed",
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="refusal", refusal="blocked")],
            )
        ],
        usage=None,
    )
    completed_response = SimpleNamespace(
        id="response-usage",
        status="completed",
        output=[],
        usage=SimpleNamespace(input_tokens=7, output_tokens=3, total_tokens=10),
    )
    streams = (
        AsyncEvents(
            SimpleNamespace(type="response.refusal.done"),
            SimpleNamespace(type="response.completed", response=refusal_response),
        ),
        AsyncEvents(
            SimpleNamespace(
                type="response.incomplete",
                response=SimpleNamespace(
                    incomplete_details=SimpleNamespace(reason="max_output_tokens")
                ),
            )
        ),
        AsyncEvents(SimpleNamespace(type="response.failed")),
        AsyncEvents(
            SimpleNamespace(type="response.output_text.delta", delta="ok"),
            SimpleNamespace(type="response.completed", response=completed_response),
        ),
    )
    expected_types = (
        ["refusal"],
        ["incomplete"],
        ["error"],
        ["text_delta", "usage", "completed"],
    )

    for stream, expected in zip(streams, expected_types, strict=True):
        provider = qwen_provider(SequenceResponses(stream), catalog=catalog)
        events = asyncio.run(collect(provider, request))
        assert [event.type for event in events] == expected
        assert stream.closed is True
    assert isinstance(events[1], ProviderUsageEvent)
    assert events[1].usage.total_tokens == 10


@pytest.mark.parametrize(
    ("scenario", "event_type", "event_class"),
    [
        ("refusal", "refusal", ProviderRefusal),
        ("incomplete", "incomplete", ProviderIncomplete),
        ("error", "error", ProviderErrorEvent),
        ("usage", "usage", ProviderUsageEvent),
    ],
)
def test_fake_provider_covers_each_new_standard_event(
    scenario: str,
    event_type: str,
    event_class: type,
) -> None:
    current, request = routed_request()
    del current
    events = asyncio.run(collect(FakeProvider(scenario=scenario), request))

    assert any(isinstance(event, event_class) for event in events)
    assert event_type in [event.type for event in events]


def test_structured_response_contract_remains_closed_for_pydantic_validation() -> None:
    with pytest.raises(ValueError, match="closed"):
        ProviderResponseFormat(
            kind=ResponseFormatKind.JSON_SCHEMA,
            name="unsafe_schema",
            schema={"type": "object", "additionalProperties": True},
        )
    assert OutputModality.TEXT.value == "TEXT"
    assert InputModality.IMAGE.value == "IMAGE"
    assert StorePolicy.NEVER.value == "NEVER"
    assert ToolChoicePolicy.REQUIRED.value == "REQUIRED"


def test_orchestrator_v2_records_route_and_normalizes_standard_terminals() -> None:
    current = settings(
        ai_provider="fake",
        ai_default_model="fake-model",
        ai_pilot_max_output_tokens=4_096,
    )
    chat = ValidatedChatInput(
        messages=(ProviderMessage(role="user", content="你好"),),
        message_count=1,
        input_chars=2,
    )

    async def run(scenario: str):
        provider = FakeProvider(scenario=scenario)
        orchestrator = AIOrchestrator(provider=provider, settings=current)
        events = [
            event
            async for event in orchestrator.stream(
                chat,
                request_id=f"route-{scenario}",
                user_id="user-route-test",
            )
        ]
        return provider, events

    normal_provider, normal = asyncio.run(run("normal"))
    assert [event.type for event in normal] == [
        "response.started",
        "message.delta",
        "message.delta",
        "message.delta",
        "message.completed",
        "response.completed",
    ]
    started = normal[0].payload
    terminal = normal[-1].payload
    assert started["provider"] == "fake"
    assert started["model"] == "fake-model"
    assert started["capability_profile"] == "fake-cn-beijing-default-v1"
    assert started["catalog_version"] == "1"
    assert started["capability_alias"] == "GENERAL_CHAT"
    assert started["reasoning_policy"] == "BALANCED"
    assert terminal["capability_profile"] == started["capability_profile"]
    request = normal_provider.requests[0]
    assert request.contract_version == "2"
    assert request.capability_alias is ModelCapability.GENERAL_CHAT
    assert request.reasoning_policy is ReasoningPolicy.BALANCED
    assert request.max_output_tokens == 4_096

    for scenario, code in (
        ("refusal", "AI_REFUSAL"),
        ("incomplete", "AI_INCOMPLETE"),
        ("error", "AI_PROVIDER_UNAVAILABLE"),
    ):
        _provider, events = asyncio.run(run(scenario))
        assert [event.type for event in events] == ["response.started", "error"]
        assert events[-1].payload["code"] == code

    _provider, usage_events = asyncio.run(run("usage"))
    assert usage_events[-1].type == "response.completed"
    assert usage_events[-1].payload["usage"] == {
        "input_tokens": 7,
        "output_tokens": 3,
        "total_tokens": 10,
    }


def test_context_capability_reports_only_configured_catalog_profile(monkeypatch) -> None:
    with make_client(
        monkeypatch,
        AI_ENABLED="true",
        AI_NIF_RUNTIME_ENABLED="true",
        AI_PROVIDER_CAPABILITY_ROUTER_ENABLED="true",
        AI_PROVIDER="fake",
        AI_DEFAULT_MODEL="fake-model",
    ) as client:
        login_admin(client)
        response = client.post(
            "/api/ai/capabilities/context",
            json={"page_context": None},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_profile"] == "fake-cn-beijing-default-v1"
    assert payload["catalog_version"] == "1"
    assert payload["reasoning_policies"] == ["FAST", "BALANCED", "DEEP"]
    assert "GENERAL_CHAT" in payload["model_capabilities"]
    assert "DOCUMENT_OCR" not in payload["model_capabilities"]
    assert payload["feature_flags"]["nif_runtime_enabled"] is True
