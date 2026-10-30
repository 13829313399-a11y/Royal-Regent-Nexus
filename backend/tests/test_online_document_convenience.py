from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_online_documents import api, BASE, SCOPE, new, context, open_editor, put_grants
from test_online_document_management import upload, enable, payload
from test_online_document_folders import folder, move
from app.models.online_documents import OnlineDocument as Document, OnlineDocumentRevision as Revision, OnlineDocumentEvent as Event
from app.services import online_document_protocol as protocol


def copy_request(client, source, **extra):
    return {'request_id': uuid4().hex, 'expected_revision': client.get(f'{BASE}/{source}{SCOPE}').json()['revision'],
            'title': '独立副本', 'folder_id': None, **extra}


def test_copy_private_exact_bytes_independent_history_protection_and_replay(api):
    client, engine, users, current, _ = api
    source = upload(client); data = enable(client, source)
    target = folder(client)
    put_grants(client, f'{BASE}/{source}/grants{SCOPE}', json={'grants': [{'user_id': 'viewer', 'access': 'view'}]})
    before = client.get(f'{BASE}/{source}{SCOPE}').json()
    request = copy_request(client, source, folder_id=target)
    url = f'{BASE}/{source}/copy{SCOPE}'
    result = client.post(url, json=request)
    assert result.status_code == 201, result.text
    copied = result.json(); copy_id = copied['id']
    assert copy_id != source and copied['grants'] == [] and copied['revision'] == 1 and copied['protected']
    assert client.get(f'{BASE}/{copy_id}/download{SCOPE}').content == data
    assert client.get(f'{BASE}/{source}{SCOPE}').json() == before
    with Session(engine) as db:
        clone = db.get(Document, copy_id)
        assert clone.storage_key != db.get(Document, source).storage_key
        assert clone.protection['baseline_revision'] == 1 and clone.protection['sha256'] == clone.sha256
        assert len(db.scalars(select(Revision).where(Revision.document_id == copy_id)).all()) == 1
    current['user'] = 'viewer'
    assert client.get(f'{BASE}/{copy_id}{SCOPE}').status_code == 404
    current['user'] = 'owner'
    assert move(client, [copy_id], None, [1]).status_code == 200
    assert client.post(f'{BASE}/{copy_id}/trash{SCOPE}', json=payload(client, copy_id)).status_code == 200
    assert client.post(url, json=request).json()['id'] == copy_id
    assert client.post(url, json={**request, 'title': '冲突副本'}).status_code == 409
    with Session(engine) as db:
        assert len(db.scalars(select(Document)).all()) == 2
        assert len(db.scalars(select(Event).where(Event.kind == 'copy')).all()) == 1


def test_copy_rejects_other_identity_scope_folder_stale_revision_and_missing_asset(api):
    client, engine, users, current, _ = api
    source = new(client); url = f'{BASE}/{source}/copy{SCOPE}'; request = copy_request(client, source)
    put_grants(client, f'{BASE}/{source}/grants{SCOPE}', json={'grants': [{'user_id': 'editor', 'access': 'edit'}]})
    current['user'] = 'editor'; foreign = folder(client)
    assert client.post(url, json=request).status_code == 403
    current['user'] = 'stranger'
    assert client.post(url, json=request).status_code == 404
    current['user'] = 'owner'
    assert client.post(url, json={**request, 'folder_id': foreign}).status_code == 404
    assert client.post(url, json={**request, 'expected_revision': 2}).status_code == 409
    assert client.post(url.replace('huaxing', 'group'), json=request).status_code == 404
    users['owner'] = context(epoch=2)
    assert client.post(url, json=request).status_code == 404
    users['owner'] = context()
    with Session(engine) as db:
        record = db.get(Document, source); record.sha256 = 'invalid'; db.commit()
    assert client.post(url, json=request).status_code == 409
    with Session(engine) as db:
        assert len(db.scalars(select(Document)).all()) == 1


def test_copy_uses_durable_version_while_source_editor_remains_active(api):
    client, engine, _, _, _ = api
    source = new(client); open_editor(client, source)
    before = client.get(f'{BASE}/{source}{SCOPE}').json()
    result = client.post(f'{BASE}/{source}/copy{SCOPE}', json=copy_request(client, source))
    assert result.status_code == 201 and not result.json()['editing']
    assert client.get(f'{BASE}/{source}{SCOPE}').json() == before


def test_editor_rename_transport_failure_is_durable_and_retry_synchronizes_once(api):
    client, engine, _, _, monkey = api
    source = new(client); open_editor(client, source)
    url = f'{BASE}/{source}/title{SCOPE}'; request = {'title': '新标题', 'expected_title': '公式核验', 'expected_version': 1}
    def disconnected(_):
        raise RuntimeError('network failure')
    monkey.setattr(protocol, 'command', disconnected)
    result = client.patch(url, json=request)
    assert result.status_code == 200 and result.json()['title_sync_pending']
    assert client.get(f'{BASE}/{source}{SCOPE}').json()['title'] == '新标题'
    monkey.setattr(protocol, 'command', lambda _: {'error': 0})
    retried = client.patch(url, json=request).json()
    assert retried['title'] == '新标题' and not retried.get('title_sync_pending')
    with Session(engine) as db:
        assert len(db.scalars(select(Event).where(Event.kind == 'rename')).all()) == 1


def test_folder_rename_preserves_classification_and_rejects_conflicts_and_foreign_owner(api):
    client, engine, users, current, _ = api
    source = new(client); target = folder(client, '原文件夹'); other = folder(client, '已有文件夹')
    assert move(client, [source], target).status_code == 200
    url = BASE + '/folders/' + target + SCOPE
    request = {'name': '新文件夹', 'expected_name': '原文件夹', 'expected_version': 1}
    assert client.patch(url, json=request).json()['name'] == '新文件夹'
    assert client.patch(url, json=request).status_code == 200
    assert client.get(BASE + SCOPE + '&folder_id=' + target).json()['items'][0]['placement_version'] == 1
    assert client.patch(url, json={'name': '第三个名字', 'expected_name': '原文件夹', 'expected_version': 1}).status_code == 409
    assert client.patch(url, json={'name': '已有文件夹', 'expected_name': '新文件夹', 'expected_version': 2}).status_code == 409
    assert client.patch(url, json={'name': 'bad/name', 'expected_name': '新文件夹', 'expected_version': 2}).status_code == 422
    assert client.patch(url.replace('huaxing', 'group'), json=request).status_code == 404
    current['user'] = 'editor'
    assert client.patch(url, json=request).status_code == 404
    current['user'] = 'owner'; users['owner'] = context(epoch=2)
    assert client.patch(url, json=request).status_code == 404
