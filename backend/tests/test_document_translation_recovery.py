"""Online document batches recover without losing text or accepting partial output."""
import json

import httpx2 as httpx
import pytest

from app.core.config import settings
from app.services.document_tools import translation_engine as engine
from app.services.document_tools.document_ir import Cancelled, ToolError


@pytest.fixture(params=['openai', 'dashscope'])
def provider(monkeypatch, request):
    protocol = request.param
    monkeypatch.setattr(engine, 'online_configured', lambda: True)
    monkeypatch.setattr(settings, 'document_tools_qwen_base_url', 'https://example.test/v1')
    monkeypatch.setattr(settings, 'document_tools_qwen_protocol', protocol)
    original = engine.online_batch
    clients = []

    def install(reply):
        def handle(request):
            payload = json.loads(request.content)
            messages = payload['input']['messages'] if protocol == 'dashscope' else payload['messages']
            content = messages[1]['content']
            inputs = json.loads(content if isinstance(content, str) else content[0]['text'])
            response = reply(inputs)
            if isinstance(response, httpx.Response):
                return response
            raw, reason = response
            content = raw if protocol == 'openai' else [{'text': raw}]
            body = {'choices': [{'finish_reason': reason, 'message': {'content': content}}]}
            return httpx.Response(200, json=body if protocol == 'openai' else {'output': body})

        client = httpx.Client(transport=httpx.MockTransport(handle))
        clients.append(client)
        monkeypatch.setattr(engine, 'online_batch', lambda *args: original(*args, client=client))

    yield install
    for client in clients:
        client.close()


def run(texts, progress=lambda *args: None, cancelled=lambda: False):
    return engine.make_translator({'translation_engine': 'online', 'glossary': 'Inspection=检验'}, progress, cancelled)(texts, 'en_to_zh')


def result(values):
    return json.dumps({'translations': values}, ensure_ascii=False), 'stop'


def test_long_document_splits_truncated_batches_and_preserves_order(provider):
    texts = [f'Inspection {i:04d}: ' + 'Verify material and packing. ' * 9 for i in range(180)]
    attempted, completed, progress = [], [], []

    def reply(inputs):
        batch = inputs['texts']
        assert inputs['terminology'] == 'Inspection=检验'
        attempted.append(batch)
        if len(batch) > 3:
            # Even syntactically complete JSON cannot be used after truncation.
            return result(batch[:1])[0], 'length'
        completed.extend(batch)
        return result([text.replace('Inspection', '检验') for text in batch])

    provider(reply)
    actual = run(texts, lambda stage, done, total: progress.append((done, total)))
    assert actual == [text.replace('Inspection', '检验') for text in texts]
    assert completed == texts  # Successful fragments are neither repeated nor lost.
    assert max(map(len, attempted)) <= 12
    assert max(sum(map(len, batch)) for batch in attempted) <= 2400
    assert progress[-1] == (len(texts), len(texts))
    assert [done for done, _ in progress] == sorted(done for done, _ in progress)


def test_count_mismatch_splits_instead_of_guessing_missing_positions(provider):
    calls = []

    def reply(inputs):
        batch = inputs['texts']
        calls.append(batch)
        return result(['合并后失去对应关系'] if len(batch) > 1 else ['译文：' + batch[0]])

    provider(reply)
    assert run(['Hair', 'Fabric', 'Skin', 'Sole']) == ['译文：Hair', '译文：Fabric', '译文：Skin', '译文：Sole']
    assert [batch[0] for batch in calls if len(batch) == 1] == ['Hair', 'Fabric', 'Skin', 'Sole']


def test_single_region_gets_one_retry_after_invalid_format(provider):
    calls = []

    def reply(inputs):
        calls.append(inputs['texts'])
        return ('{"translations":', 'stop') if len(calls) == 1 else result(['数量 00123'])

    provider(reply)
    assert run(['Quantity 00123']) == ['数量 00123']
    assert len(calls) == 2


def test_complete_fenced_json_is_accepted_without_extra_requests(provider):
    calls = []

    def reply(inputs):
        calls.append(inputs)
        return '\n```json\n' + result(['数量 00123'])[0] + '\n```\n', 'stop'

    provider(reply)
    assert run(['Quantity 00123']) == ['数量 00123']
    assert len(calls) == 1


def test_truncated_finish_reason_is_retried_even_if_json_looks_complete(provider):
    calls = []

    def reply(inputs):
        calls.append(inputs)
        return result(['数量 00123'])[0], 'length' if len(calls) == 1 else 'stop'

    provider(reply)
    assert run(['Quantity 00123']) == ['数量 00123']
    assert len(calls) == 2


def test_network_timeout_is_not_multiplied_by_splitting(provider):
    calls = []

    def reply(inputs):
        calls.append(inputs)
        raise httpx.ReadTimeout('test timeout')

    provider(reply)
    with pytest.raises(ToolError) as error:
        run(['Inspection'] * 12)
    assert error.value.code == 'TRANSLATION_NETWORK'
    assert len(calls) == 1


def test_persistently_invalid_response_stops_with_bounded_requests(provider):
    calls, progress = [], []

    def reply(inputs):
        calls.append(inputs)
        return result([])

    provider(reply)
    with pytest.raises(ToolError) as error:
        run(['Inspection'] * 12, lambda stage, done, total: progress.append(done))
    assert error.value.code == 'TRANSLATION_RESPONSE'
    assert '重试' in str(error.value)
    assert 2 <= len(calls) <= 6
    assert not any(progress)


@pytest.mark.parametrize('status', [401, 429, 503])
def test_service_errors_do_not_fan_out_into_split_requests(provider, status):
    calls = []

    def reply(inputs):
        calls.append(inputs)
        return httpx.Response(status)

    provider(reply)
    with pytest.raises(ToolError) as error:
        run(['Inspection'] * 12)
    assert error.value.code == 'TRANSLATION_SERVICE'
    assert len(calls) == 1


def test_cancelled_response_never_starts_recovery(provider):
    calls, stopped = [], False

    def reply(inputs):
        nonlocal stopped
        calls.append(inputs)
        stopped = True
        return result([])

    provider(reply)
    with pytest.raises(Cancelled):
        run(['Inspection'] * 12, cancelled=lambda: stopped)
    assert len(calls) == 1


def test_numeric_corruption_after_split_is_still_rejected(provider):
    def reply(inputs):
        return result([] if len(inputs['texts']) > 1 else ['数量 999'])

    provider(reply)
    with pytest.raises(ToolError) as error:
        run(['Quantity 00123', 'Quantity 00456'])
    assert error.value.code == 'TRANSLATION_NUMBERS_CHANGED'


def test_refusal_is_not_retried_as_a_format_problem(provider):
    calls = []

    def reply(inputs):
        calls.append(inputs)
        return '', 'content_filter'

    provider(reply)
    with pytest.raises(ToolError) as error:
        run(['Inspection'] * 12)
    assert error.value.code == 'TRANSLATION_REFUSED'
    assert len(calls) == 1
