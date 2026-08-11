from collections.abc import AsyncIterator

from app.services.ai.providers.base import (
    ProviderCompleted,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderTextDelta,
)


class FakeProvider:
    provider_name = "fake"
    supports_streaming = True
    supports_function_calls = True

    def __init__(
        self,
        *,
        response: ProviderResponse | None = None,
        events: tuple[ProviderStreamEvent, ...] | None = None,
    ) -> None:
        uses_default_response = response is None
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

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return self.response

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        self.requests.append(request)
        for event in self.events:
            yield event

    async def aclose(self) -> None:
        self.closed = True
