"""Exercise the real HTTP transport against loopback, without paid requests."""
import asyncio
import importlib
from types import SimpleNamespace

from pydantic import SecretStr


def test_completed_sse_closes_http_iterators_without_shutdown_errors(monkeypatch):
    provider = importlib.import_module('app.services.assistant.provider')
    errors, requests = [], []
    body = (
        'data: {"choices":[{"delta":{"content":"synthetic"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        'data: [DONE]\n\n'
    ).encode()

    async def scenario():
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: errors.append(context['message']))

        async def respond(reader, writer):
            try:
                headers = await reader.readuntil(b'\r\n\r\n')
                length = next(int(line.split(b':', 1)[1]) for line in headers.split(b'\r\n') if line.lower().startswith(b'content-length:'))
                requests.append(await reader.readexactly(length))
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                await writer.drain()
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()

        async with await asyncio.start_server(respond, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            monkeypatch.setattr(provider, 'settings', SimpleNamespace(
                assistant_qwen_base_url=f'http://127.0.0.1:{port}/v1',
                assistant_qwen_api_key=SecretStr('synthetic-only'),
                assistant_upstream_idle_timeout_seconds=3,
                assistant_connect_timeout_seconds=3,
            ))
            monkeypatch.setattr(provider, 'request_body', lambda *args: {'model': 'synthetic', 'stream': True})
            events = [event async for event in provider.stream([], SimpleNamespace(thinking='auto'))]
            assert events[-1] == {'kind': 'done', 'finish_reason': 'stop'}
            assert any(event.get('text') == 'synthetic' for event in events)
            await asyncio.sleep(0)

    asyncio.run(scenario())
    assert len(requests) == 1
    assert errors == []
