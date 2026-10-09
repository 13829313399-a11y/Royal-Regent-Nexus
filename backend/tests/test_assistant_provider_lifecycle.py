"""Exercise the real HTTP transport against loopback, without paid requests."""
import asyncio
import importlib
from types import SimpleNamespace
import pytest

from pydantic import SecretStr


@pytest.mark.parametrize('chunked', [False, True])
@pytest.mark.parametrize('cancel_early', [False, True])
def test_completed_sse_closes_http_iterators_without_shutdown_errors(monkeypatch, chunked, cancel_early):
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
                headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                if chunked:
                    writer.write(headers + b'Transfer-Encoding: chunked\r\n\r\n' + f'{len(body):x}\r\n'.encode() + body + b'\r\n')
                else:
                    writer.write(headers + b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                await writer.drain()
                if chunked:
                    await asyncio.sleep(.05)
                    writer.write(b'0\r\n\r\n')
                    await writer.drain()
                await reader.read()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass

        async with await asyncio.start_server(respond, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            monkeypatch.setattr(provider, 'settings', SimpleNamespace(
                assistant_qwen_base_url=f'http://127.0.0.1:{port}/v1',
                assistant_qwen_api_key=SecretStr('synthetic-only'),
                assistant_upstream_idle_timeout_seconds=3,
                assistant_connect_timeout_seconds=3,
            ))
            monkeypatch.setattr(provider, 'request_body', lambda *args: {'model': 'synthetic', 'stream': True})
            stream = provider.stream([], SimpleNamespace(thinking='auto'))
            if cancel_early:
                assert (await anext(stream))['kind'] == 'delta'
                await stream.aclose()
            else:
                events = [event async for event in stream]
                assert events[-1] == {'kind': 'done', 'finish_reason': 'stop'}
                assert any(event.get('text') == 'synthetic' for event in events)
            await asyncio.sleep(0)

    asyncio.run(scenario())
    assert len(requests) == 1
    assert errors == []
