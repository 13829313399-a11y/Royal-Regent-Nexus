"""Unexpected failures retain useful metadata without logging private exception text."""
from contextlib import asynccontextmanager
import json
import logging
import pytest
from test_assistant_api import env, session, payload
from test_assistant_durable_runs import durable_env, wait_snapshot


@pytest.mark.parametrize('protocol', [2, 3])
def test_unexpected_failure_logs_only_type_and_site_and_keeps_partial_without_retry(durable_env, caplog, protocol):
    from app.services.assistant import provider
    from app.models.assistant import AssistantSession
    client, database, _, patch = durable_env
    secret = 'DO_NOT_LOG_PRIVATE_PROMPT_SQL_BINDS_OR_PROVIDER_KEY'
    calls = []

    @asynccontextmanager
    async def broken(body):
        calls.append(1)
        async def chunks():
            yield ('data: '+json.dumps(dict(choices=[dict(delta=dict(content='PARTIAL_DIAGNOSTIC_BODY'),finish_reason=None)]))+'\n\n').encode()
            raise RuntimeError(secret)
        yield chunks()

    patch.setattr(provider, 'open_stream', broken)
    sid = session(client)
    body = payload(protocol_version=protocol)
    with caplog.at_level(logging.WARNING, logger='assistant.run'):
        response = client.post('/api/assistant/sessions/'+sid+'/messages', json=body)
        assert response.status_code == (202 if protocol == 3 else 200)
        if protocol == 3:
            rid = response.json()['run_id']
            snapshot = wait_snapshot(client, rid)
        else:
            snapshot = client.get('/api/assistant/sessions/'+sid+'/runs/lookup',params=dict(client_request_id=body['client_request_id'])).json()
            rid = snapshot['run_id']
    assert snapshot['state'] == 'failed' and snapshot['error_code'] == 'internal_error'
    assert 'PARTIAL_DIAGNOSTIC_BODY' in json.dumps(snapshot['items'])
    assert snapshot['usage'] is None and snapshot['context_window']['provider_attempt_state']=='started'
    records=[r for r in caplog.records if r.name=='assistant.run' and 'assistant_run_failed' in r.getMessage()]
    assert len(records)==1
    message=records[0].getMessage()
    assert rid in message and 'error_type=RuntimeError' in message and 'site=test_assistant_runtime_diagnostics.py:' in message
    assert secret not in message and 'PARTIAL_DIAGNOSTIC_BODY' not in message
    assert not records[0].exc_info and not records[0].stack_info
    with database.SessionLocal() as db:
        assert db.get(AssistantSession,sid).budget_unknown
    reused=client.post('/api/assistant/sessions/'+sid+'/messages',json=body).json()
    assert reused['run_id']==rid and reused['reused']
    assert len(calls)==1
