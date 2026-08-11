import asyncio
import copy
import logging
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.ai.provider_factory import (
    ProviderConfigurationError,
    build_provider,
    get_pilot_provider_status,
    get_provider_status,
    get_vision_provider_status,
    resolve_qwen_base_url,
)
from app.services.ai.providers import (
    FakeProvider,
    LLMProvider,
    ProviderCompleted,
    ProviderError,
    ProviderErrorCode,
    ProviderImageContent,
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
    ProviderTextContent,
    ProviderTextDelta,
    ProviderToolCall,
    ProviderToolCallEvent,
    ProviderToolDefinition,
    ProviderToolResult,
    QwenResponsesProvider,
)


def make_settings(**overrides) -> Settings:
    values = {
        "app_env": "development",
        "ai_enabled": True,
        "ai_provider": "qwen",
        "ai_region": "cn-beijing",
        "ai_workspace_id": "ws-test-workspace",
        "dashscope_api_key": "test-key-not-a-secret",
        "ai_default_model": "qwen3.7-plus",
        "ai_base_url": "",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


async def collect_stream(provider, request):
    return [event async for event in provider.stream(request)]


class FakeResponses:
    def __init__(self, *, results=(), error=None):
        self.results = list(results)
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.results.pop(0)


class AsyncEvents:
    def __init__(self, *events):
        self._events = iter(events)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def close(self):
        self.closed = True


class BlockingEvents:
    def __init__(self):
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Future()

    async def close(self):
        self.closed = True


class ClosableClient:
    def __init__(self, responses):
        self.responses = responses
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class StatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f"provider returned {status_code}")
        self.status_code = status_code


def make_qwen_provider(responses: FakeResponses) -> QwenResponsesProvider:
    return QwenResponsesProvider(
        api_key="test-key-not-a-secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        timeout_seconds=5,
        client=SimpleNamespace(responses=responses),
    )


def test_feature_flag_off_and_missing_qwen_configuration_are_unavailable():
    disabled = get_provider_status(make_settings(ai_enabled=False))
    assert disabled.enabled is False
    assert disabled.available is False
    assert disabled.reason == "disabled"

    missing_key = get_provider_status(make_settings(dashscope_api_key=""))
    assert missing_key.enabled is True
    assert missing_key.available is False
    assert missing_key.reason == "missing_api_key"

    missing_workspace = get_provider_status(make_settings(ai_workspace_id=""))
    assert missing_workspace.enabled is True
    assert missing_workspace.available is False
    assert missing_workspace.reason == "missing_workspace"


def test_qwen_base_url_is_constructed_and_production_override_is_rejected():
    settings = make_settings(ai_workspace_id="ws-example-123")
    assert resolve_qwen_base_url(settings) == (
        "https://ws-example-123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )

    development_override = make_settings(ai_base_url="http://127.0.0.1:8099/v1/")
    assert resolve_qwen_base_url(development_override) == "http://127.0.0.1:8099/v1"

    production_override = make_settings(
        app_env="production",
        ai_base_url="https://arbitrary.example/v1",
    )
    status = get_provider_status(production_override)
    assert status.available is False
    assert status.reason == "base_url_override_not_allowed"
    with pytest.raises(ProviderConfigurationError) as exc_info:
        resolve_qwen_base_url(production_override)
    assert exc_info.value.reason == "base_url_override_not_allowed"

    invalid_workspace = get_provider_status(make_settings(ai_workspace_id="w" * 64))
    assert invalid_workspace.available is False
    assert invalid_workspace.reason == "invalid_workspace"


def test_vision_runtime_contract_accepts_only_workspace_scoped_beijing_qwen():
    settings = make_settings(ai_cloud_vision_enabled=True)

    status = get_vision_provider_status(settings)

    assert status.available is True
    assert status.provider == "qwen"
    assert status.model == "qwen3.7-plus"
    assert status.region == "cn-beijing"
    assert status.base_url == (
        "https://ws-test-workspace.cn-beijing.maas.aliyuncs.com/"
        "compatible-mode/v1"
    )
    assert status.test_only is False
    provider = build_provider(settings, require_vision=True)
    try:
        assert isinstance(provider, QwenResponsesProvider)
    finally:
        asyncio.run(provider.aclose())


def test_production_pilot_provider_contract_is_exact_and_fail_closed():
    valid = get_pilot_provider_status(make_settings(app_env="production"))
    assert valid.available is True
    assert valid.base_url == (
        "https://ws-test-workspace.cn-beijing.maas.aliyuncs.com/"
        "compatible-mode/v1"
    )

    cases = (
        (make_settings(app_env="production", ai_provider="fake"), "pilot_provider_not_allowed"),
        (
            make_settings(app_env="production", ai_region="cn-shanghai"),
            "pilot_region_not_allowed",
        ),
        (
            make_settings(app_env="production", ai_default_model="another-model"),
            "pilot_model_not_allowed",
        ),
        (
            make_settings(
                app_env="production",
                ai_base_url="https://arbitrary.example/v1",
            ),
            "pilot_base_url_override_not_allowed",
        ),
        (
            make_settings(app_env="production", ai_workspace_id=""),
            "missing_workspace",
        ),
        (
            make_settings(app_env="production", dashscope_api_key=""),
            "missing_api_key",
        ),
    )
    for settings, expected_reason in cases:
        status = get_pilot_provider_status(settings)
        assert status.available is False
        assert status.reason == expected_reason


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"ai_provider": "fake"}, "vision_provider_not_allowed"),
        ({"ai_provider": "unsupported"}, "vision_provider_not_allowed"),
        ({"ai_region": "cn-shanghai"}, "vision_region_not_allowed"),
        ({"ai_vision_model": "another-model"}, "vision_model_not_allowed"),
        (
            {"ai_base_url": "https://ws-test-workspace.cn-beijing.maas.aliyuncs.com"},
            "vision_base_url_override_not_allowed",
        ),
        ({"ai_workspace_id": ""}, "missing_workspace"),
        ({"dashscope_api_key": ""}, "missing_api_key"),
    ],
)
def test_vision_runtime_contract_rejects_every_mismatch(
    overrides,
    expected_reason,
):
    settings = make_settings(ai_cloud_vision_enabled=True, **overrides)

    status = get_vision_provider_status(settings)

    assert status.available is False
    assert status.reason == expected_reason
    with pytest.raises(ProviderConfigurationError) as exc_info:
        build_provider(settings, require_vision=True)
    assert exc_info.value.reason == expected_reason


def test_fake_vision_requires_explicit_test_only_override():
    production = make_settings(
        app_env="production",
        ai_provider="fake",
        ai_cloud_vision_enabled=True,
        ai_test_fake_vision_enabled=True,
    )
    test_without_override = make_settings(
        app_env="test",
        ai_provider="fake",
        ai_cloud_vision_enabled=True,
    )
    test_with_override = make_settings(
        app_env="test",
        ai_provider="fake",
        ai_cloud_vision_enabled=True,
        ai_test_fake_vision_enabled=True,
    )

    assert get_vision_provider_status(production).reason == (
        "test_fake_vision_not_allowed"
    )
    assert get_vision_provider_status(test_without_override).reason == (
        "vision_provider_not_allowed"
    )
    status = get_vision_provider_status(test_with_override)
    assert status.available is True
    assert status.test_only is True
    assert isinstance(
        build_provider(test_with_override, require_vision=True),
        FakeProvider,
    )


def test_fake_provider_replays_text_stream_and_tool_event():
    tool_call = ProviderToolCall(
        call_id="call-1",
        name="lookup_order",
        arguments_json='{"order_id":"ORDER-1"}',
    )
    provider = FakeProvider(
        response=ProviderResponse(text="done", tool_calls=(tool_call,)),
        events=(
            ProviderTextDelta(delta="do"),
            ProviderToolCallEvent(tool_call=tool_call),
            ProviderCompleted(response_id="fake-response"),
        ),
    )
    request = ProviderRequest(
        model="fake-model",
        request_id="request-fake",
        input=(ProviderMessage(role="user", content="hello"),),
    )

    assert isinstance(provider, LLMProvider)
    assert asyncio.run(provider.generate(request)).text == "done"
    events = asyncio.run(collect_stream(provider, request))
    assert [event.type for event in events] == ["text_delta", "tool_call", "completed"]
    assert events[1].tool_call == tool_call
    assert provider.requests == [request, request]


def test_fake_provider_defaults_to_deterministic_chinese_deltas_and_can_close():
    provider = FakeProvider()
    request = ProviderRequest(
        model="fake-model",
        request_id="request-default",
        input=(ProviderMessage(role="user", content="hello"),),
    )

    events = asyncio.run(collect_stream(provider, request))
    assert [event.type for event in events] == [
        "text_delta",
        "text_delta",
        "text_delta",
        "completed",
    ]
    assert "".join(event.delta for event in events if event.type == "text_delta") == (
        "这是一条确定性的中文测试回复。"
    )
    assert provider.closed is False
    asyncio.run(provider.aclose())
    assert provider.closed is True


def test_fake_provider_preserves_explicit_empty_event_sequence():
    provider = FakeProvider(events=())
    request = ProviderRequest(
        model="fake-model",
        request_id="request-empty",
        input=(ProviderMessage(role="user", content="hello"),),
    )

    assert asyncio.run(collect_stream(provider, request)) == []


def test_qwen_requests_always_disable_store_and_map_text_and_tool_calls():
    tool_call = SimpleNamespace(
        type="function_call",
        call_id="call-1",
        name="lookup_order",
        arguments='{"order_id":"ORDER-1"}',
    )
    usage = SimpleNamespace(input_tokens=12, output_tokens=4, total_tokens=16)
    response = SimpleNamespace(
        id="response-1",
        status="completed",
        output_text="result",
        output=[tool_call],
        usage=usage,
    )
    stream = AsyncEvents(
        SimpleNamespace(type="response.output_text.delta", delta="res"),
        SimpleNamespace(type="response.output_item.done", item=tool_call),
        SimpleNamespace(type="response.completed", response=response),
    )
    responses = FakeResponses(results=(response, stream))
    provider = make_qwen_provider(responses)
    request = ProviderRequest(
        model="qwen3.7-plus",
        request_id="request-qwen",
        input=(
            ProviderMessage(role="user", content="find it"),
            ProviderToolCall(
                call_id="previous-call",
                name="lookup_order",
                arguments_json='{"order_id":"ORDER-0"}',
            ),
            ProviderToolResult(call_id="previous-call", output='{"ok":true}'),
        ),
        tools=(
            ProviderToolDefinition(
                name="lookup_order",
                description="Look up one order",
                parameters={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                },
            ),
        ),
    )

    result = asyncio.run(provider.generate(request))
    events = asyncio.run(collect_stream(provider, request))

    assert result.text == "result"
    assert result.tool_calls[0].call_id == "call-1"
    assert result.usage.total_tokens == 16
    assert [event.type for event in events] == ["text_delta", "tool_call", "completed"]
    assert stream.closed is True
    assert all(call["store"] is False for call in responses.calls)
    assert [call["stream"] for call in responses.calls] == [False, True]
    assert all("previous_response_id" not in call for call in responses.calls)
    assert responses.calls[0]["reasoning"] == {"effort": "low"}
    assert responses.calls[0]["tools"][0]["type"] == "function"
    assert "function" not in responses.calls[0]["tools"][0]
    assert responses.calls[0]["input"][1] == {
        "type": "function_call",
        "call_id": "previous-call",
        "name": "lookup_order",
        "arguments": '{"order_id":"ORDER-0"}',
    }
    assert responses.calls[0]["input"][2] == {
        "type": "function_call_output",
        "call_id": "previous-call",
        "output": '{"ok":true}',
    }


def test_qwen_image_request_uses_data_url_without_tools_or_parallel_calls(caplog):
    class SnapshotResponses(FakeResponses):
        def __init__(self, *, results=()):
            super().__init__(results=results)
            self.snapshots = []

        async def create(self, **kwargs):
            self.snapshots.append(copy.deepcopy(kwargs))
            return await super().create(**kwargs)

    response = SimpleNamespace(
        id="response-image",
        status="completed",
        output_text="synthetic result",
        output=[],
        usage=None,
    )
    for logger_name in ("openai", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.DEBUG)
    responses = SnapshotResponses(results=(response,))
    provider = make_qwen_provider(responses)
    image_bytes = bytearray(b"synthetic-image-bytes")
    request = ProviderRequest(
        model="qwen3.7-plus",
        request_id="request-image",
        input=(
            ProviderMessage(role="system", content="system policy"),
            ProviderMessage(
                role="user",
                content=(
                    ProviderTextContent(text="describe image"),
                    ProviderImageContent(
                        attachment_id="image-1",
                        media_type="image/png",
                        data=image_bytes,
                    ),
                ),
            ),
        ),
    )

    result = asyncio.run(provider.generate(request))

    assert result.text == "synthetic result"
    assert all(
        logging.getLogger(logger_name).level >= logging.ERROR
        for logger_name in ("openai", "httpx", "httpcore")
    )
    snapshot = responses.snapshots[0]
    assert snapshot["store"] is False
    assert snapshot["parallel_tool_calls"] is False
    assert "tools" not in snapshot
    assert snapshot["input"][-1]["content"] == [
        {"type": "input_text", "text": "describe image"},
        {
            "type": "input_image",
            "image_url": "data:image/png;base64,c3ludGhldGljLWltYWdlLWJ5dGVz",
        },
    ]
    assert responses.calls[0]["input"][-1]["content"][-1]["image_url"] == ""
    assert "data:image" not in caplog.text
    assert "c3ludGhldGljLWltYWdlLWJ5dGVz" not in caplog.text


def test_qwen_provider_rejects_image_outside_final_user_or_with_tool_replay():
    image = ProviderImageContent(
        attachment_id="image-1",
        media_type="image/png",
        data=bytearray(b"synthetic"),
    )
    text_part = ProviderTextContent(text="text")
    invalid_requests = (
        ProviderRequest(
            model="qwen3.7-plus",
            request_id="image-in-system",
            input=(
                ProviderMessage(role="system", content=(text_part, image)),
                ProviderMessage(role="user", content="hello"),
            ),
        ),
        ProviderRequest(
            model="qwen3.7-plus",
            request_id="image-in-history",
            input=(
                ProviderMessage(role="user", content=(text_part, image)),
                ProviderMessage(role="assistant", content="seen"),
                ProviderMessage(role="user", content="continue"),
            ),
        ),
        ProviderRequest(
            model="qwen3.7-plus",
            request_id="assistant-after-image",
            input=(
                ProviderMessage(role="user", content=(text_part, image)),
                ProviderMessage(role="assistant", content="final message"),
            ),
        ),
        ProviderRequest(
            model="qwen3.7-plus",
            request_id="image-with-tool-definition",
            input=(ProviderMessage(role="user", content=(text_part, image)),),
            tools=(
                ProviderToolDefinition(
                    name="identity",
                    description="must be blocked",
                    parameters={"type": "object"},
                ),
            ),
        ),
        ProviderRequest(
            model="qwen3.7-plus",
            request_id="image-with-tool-replay",
            input=(
                ProviderMessage(role="user", content=(text_part, image)),
                ProviderToolCall(
                    call_id="call-1",
                    name="identity",
                    arguments_json="{}",
                ),
            ),
        ),
    )

    for request in invalid_requests:
        responses = FakeResponses()
        provider = make_qwen_provider(responses)
        with pytest.raises(ProviderError) as exc_info:
            asyncio.run(provider.generate(request))
        assert exc_info.value.code == ProviderErrorCode.REQUEST_FAILED
        assert responses.calls == []


@pytest.mark.parametrize(
    ("error", "expected_code", "retryable"),
    [
        (StatusError(401), ProviderErrorCode.AUTHENTICATION_FAILED, False),
        (StatusError(429), ProviderErrorCode.RATE_LIMITED, True),
        (StatusError(500), ProviderErrorCode.PROVIDER_UNAVAILABLE, True),
        (TimeoutError(), ProviderErrorCode.TIMEOUT, True),
    ],
)
def test_qwen_provider_normalizes_provider_errors(error, expected_code, retryable):
    provider = make_qwen_provider(FakeResponses(error=error))
    request = ProviderRequest(
        model="qwen3.7-plus",
        request_id="request-error",
        input=(ProviderMessage(role="user", content="hello"),),
    )

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.generate(request))

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert "provider returned" not in str(exc_info.value)


def test_qwen_provider_rejects_unknown_stream_event():
    stream = AsyncEvents(SimpleNamespace(type="unexpected.vendor.event"))
    responses = FakeResponses(results=(stream,))
    provider = make_qwen_provider(responses)
    request = ProviderRequest(
        model="qwen3.7-plus",
        request_id="request-invalid-stream",
        input=(ProviderMessage(role="user", content="hello"),),
    )

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(collect_stream(provider, request))

    assert exc_info.value.code == ProviderErrorCode.INVALID_EVENT
    assert stream.closed is True


def test_qwen_stream_closes_and_preserves_task_cancellation():
    stream = BlockingEvents()
    provider = make_qwen_provider(FakeResponses(results=(stream,)))
    request = ProviderRequest(
        model="qwen3.7-plus",
        request_id="request-cancelled",
        input=(ProviderMessage(role="user", content="hello"),),
    )

    async def cancel_stream():
        task = asyncio.create_task(collect_stream(provider, request))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_stream())
    assert stream.closed is True


def test_qwen_provider_aclose_closes_client_once():
    client = ClosableClient(FakeResponses())
    provider = QwenResponsesProvider(
        api_key="test-key-not-a-secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        timeout_seconds=5,
        client=client,
    )

    async def close_twice():
        await provider.aclose()
        await provider.aclose()

    asyncio.run(close_twice())
    assert client.close_calls == 1


@pytest.mark.parametrize("status", ["failed", "incomplete", "cancelled", "in_progress"])
def test_qwen_provider_rejects_non_completed_response_status(status):
    response = SimpleNamespace(
        id="response-failed",
        status=status,
        output_text="partial output must not be returned",
        output=[],
        error=SimpleNamespace(message="provider-internal-sensitive-detail"),
    )
    provider = make_qwen_provider(FakeResponses(results=(response,)))
    request = ProviderRequest(
        model="qwen3.7-plus",
        request_id="request-status",
        input=(ProviderMessage(role="user", content="hello"),),
    )

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.generate(request))

    assert exc_info.value.code == ProviderErrorCode.REQUEST_FAILED
    assert "provider-internal-sensitive-detail" not in str(exc_info.value)
