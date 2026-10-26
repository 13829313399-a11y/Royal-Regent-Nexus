"""Real parser subprocess and isolated persistence; provider is offline replay."""
import json
import time
import pytest
from test_assistant_api import env, session, payload
from test_assistant_v2 import migrate
from assistant_office_fixtures import docx_fixture, xlsx_fixture


def ready(client, ident):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = client.get(f'/api/assistant/files/{ident}').json()
        if value.get('parse_status') in ('ready', 'failed'):
            return value
        time.sleep(.05)
    pytest.fail(f'Office subprocess did not reach a terminal state within 20 seconds: {value}')


@pytest.mark.parametrize('extension,factory,locator', [
    ('.docx', docx_fixture, dict(kind='paragraph', paragraph=8)),
    ('.xlsx', xlsx_fixture, dict(kind='sheet', sheet='采购', cells='C7')),
])
def test_real_worker_preserves_metadata_history_exports_and_private_revocation(env, extension, factory, locator):
    client, dbm, calls, _ = env
    migrate(dbm); sid = session(client)
    response = client.post(f'/api/assistant/sessions/{sid}/files', files={'file': ('合成资料'+extension, factory())})
    assert response.status_code == 200, response.text
    ident = response.json()['id']
    info = ready(client, ident)
    assert info['parse_status'] == 'ready', info
    parts = client.get(f'/api/assistant/files/{ident}/content?extracted=true').json()
    part = next(p for p in parts if p['locator'] == locator)
    assert part['metadata']['format'] == extension[1:]
    client.cookies.set('rr_session', 'bob')
    assert client.get(f'/api/assistant/files/{ident}/content').status_code == 404
    client.cookies.set('rr_session', 'alice')
    question = '采购表 C7 和 D7 的公式和缓存是什么？' if extension == '.xlsx' else '验收条件与合成条款有哪些要求？'
    run = client.post(f'/api/assistant/sessions/{sid}/messages', json=payload(protocol_version=2, document_ids=[ident], intent='analyze_files') | {'text':question})
    assert 'event: run.completed' in run.text, run.text
    upstream = json.dumps(calls[-1], ensure_ascii=False)
    if extension == '.xlsx':
        assert '=A7-B7' in upstream and '=EXTERNAL_REF' in upstream
        assert '未知（公式未保存可用缓存）' in upstream and 'missing' in upstream
    else:
        assert '验收条件' in upstream and '合成条款：交付前核对数量与单位。' in upstream
    answer = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    evidence = next(p for p in answer['content_parts'] if p['type'] == 'evidence')
    source = next(s for s in evidence['sources'] if s.get('locator') == locator)
    assert len(source['content_hash']) == 64
    exported = client.get(f"/api/assistant/runs/{answer['run_id']}/export").text
    assert ('采购!C7' if extension == '.xlsx' else '第8段') in exported
    saved = client.post(f'/api/assistant/sessions/{sid}/artifacts', json=dict(source_run_id=answer['run_id'], title='合成资料成果', kind='markdown', content='合成验收结果'))
    assert saved.status_code == 200, saved.text
    aid = saved.json()['id']
    assert client.delete(f'/api/assistant/files/{ident}').status_code == 204
    assert client.get(f'/api/assistant/files/{ident}/content').status_code == 410
    assert client.get(f'/api/assistant/artifacts/{aid}/export').status_code == 410
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['unavailable']


def test_signature_failure_and_mime_mismatch_do_not_consume_queue_or_poison_next_file(env):
    client, dbm, calls, _ = env
    migrate(dbm); sid = session(client)
    url = f'/api/assistant/sessions/{sid}/files'
    mismatch = client.post(url, files={'file': ('synthetic.xlsx', xlsx_fixture(), 'text/plain')})
    assert mismatch.status_code == 422
    bad = client.post(url, files={'file': ('fake.xlsx', b'plain text pretending to be a spreadsheet')})
    assert bad.status_code == 200
    failure = ready(client, bad.json()['id'])
    assert failure['parse_status'] == 'failed' and failure['error_code'] == 'office_signature'
    good = client.post(url, files={'file': ('synthetic.docx', docx_fixture())})
    assert ready(client, good.json()['id'])['parse_status'] == 'ready'
    assert client.get(f"/api/assistant/files/{bad.json()['id']}/content?extracted=true").status_code == 409
    assert not calls, 'upload and preview must never invoke a provider'


def test_legacy_text_preserves_its_exact_context_budget_without_metadata(env):
    client, dbm, calls, patch = env
    from app.services.assistant import files
    from test_work_center_api import actor
    migrate(dbm); sid=session(client)
    response=client.post(f'/api/assistant/sessions/{sid}/files',files={'file':('boundary.txt',b'12345678')})
    ident=response.json()['id']
    assert ready(client,ident)['parse_status']=='ready'
    patch.setattr(files.settings,'assistant_context_character_budget',16)
    with dbm.SessionLocal() as db:
        parts,sources=files.materials(db,actor('alice'),sid,[ident],'boundary')
    assert parts[0]['text']=='12345678' and len(sources)==1
    assert 'metadata' not in parts[0] and not calls
