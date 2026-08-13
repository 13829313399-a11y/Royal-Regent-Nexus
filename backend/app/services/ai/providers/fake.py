from collections.abc import AsyncIterator
from enum import StrEnum

from app.services.ai.providers.base import (
    ProviderCompleted,
    ProviderError,
    ProviderErrorCode,
    ProviderErrorEvent,
    ProviderIncomplete,
    ProviderRefusal,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderToolCall,
    ProviderToolCallEvent,
    ProviderUsage,
    ProviderUsageEvent,
)


class FakeProviderScenario(StrEnum):
    NORMAL = "normal"
    TOOL = "tool"
    TRUNCATED = "truncated"
    FAILURE = "failure"
    EOF = "eof"
    REFUSAL = "refusal"
    INCOMPLETE = "incomplete"
    ERROR = "error"
    USAGE = "usage"


class FakeProvider:
    provider_name = "fake"
    supports_streaming = True
    supports_function_calls = True

    def __init__(
        self,
        *,
        response: ProviderResponse | None = None,
        events: tuple[ProviderStreamEvent, ...] | None = None,
        scenario: FakeProviderScenario | str = FakeProviderScenario.NORMAL,
    ) -> None:
        self.scenario = FakeProviderScenario(scenario)
        if self.scenario is not FakeProviderScenario.NORMAL and (
            response is not None or events is not None
        ):
            raise ValueError("named Fake Provider scenarios cannot override events")
        uses_default_response = response is None
        self.uses_default_events = events is None
        self.response = response or ProviderResponse(
            text="这是一条确定性的中文测试回复。",
            response_id="fake-response",
        )
        self.events = (
            events
            if events is not None
            else (
                *(
                    (
                        ProviderTextDelta(delta="这是一条"),
                        ProviderTextDelta(delta="确定性的中文"),
                        ProviderTextDelta(delta="测试回复。"),
                    )
                    if uses_default_response
                    else (ProviderTextDelta(delta=self.response.text),)
                ),
                ProviderCompleted(
                    response_id=self.response.response_id,
                    usage=self.response.usage,
                ),
            )
        )
        self.requests: list[ProviderRequest] = []
        self.closed = False
        self.stream_calls = 0

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if self.scenario is FakeProviderScenario.FAILURE:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "deterministic fake provider failure",
                retryable=True,
            )
        return self.response

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        self.requests.append(request)
        self.stream_calls += 1
        if self.scenario is FakeProviderScenario.FAILURE:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "deterministic fake provider failure",
                retryable=True,
            )
        if self.scenario is FakeProviderScenario.EOF:
            return
        if self.scenario is FakeProviderScenario.REFUSAL:
            yield ProviderRefusal()
            return
        if self.scenario is FakeProviderScenario.INCOMPLETE:
            yield ProviderIncomplete(reason="max_output_tokens")
            return
        if self.scenario is FakeProviderScenario.ERROR:
            yield ProviderErrorEvent(
                code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
                status_code=503,
            )
            return
        if self.scenario is FakeProviderScenario.USAGE:
            usage = ProviderUsage(input_tokens=7, output_tokens=3, total_tokens=10)
            yield ProviderTextDelta(delta="确定性用量事件。")
            yield ProviderUsageEvent(usage=usage)
            yield ProviderCompleted(response_id="fake-usage-response", usage=usage)
            return
        if self.scenario is FakeProviderScenario.TOOL:
            if self.stream_calls == 1:
                yield ProviderToolCallEvent(
                    tool_call=ProviderToolCall(
                        call_id="fake-call-1",
                        name="identity.get_current_context",
                        arguments_json="{}",
                    )
                )
                yield ProviderCompleted(response_id="fake-tool-request")
                return
            yield ProviderTextDelta(delta="工具结果已由服务端验证。")
            yield ProviderCompleted(response_id="fake-tool-response")
            return
        if self.scenario is FakeProviderScenario.TRUNCATED:
            yield ProviderTextDelta(delta="长" * 8_001)
            yield ProviderCompleted(response_id="fake-truncated-response")
            return
        for event in self.events:
            if (
                request.contract_version == "2"
                and self.uses_default_events
                and isinstance(event, ProviderCompleted)
            ):
                yield ProviderUsageEvent(usage=event.usage)
            yield event

    async def aclose(self) -> None:
        self.closed = True
