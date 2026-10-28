from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_online_documents import api, new, put_grants, BASE, SCOPE, context, workbook
from app.models.online_documents import OnlineDocument as Document, OnlineDocumentRevision as Revision, OnlineDocumentPlacement as Placement, OnlineDocumentEvent as Event


def folder(client, name="成品进出", scope=SCOPE):
    response = client.post(BASE + '/folders' + scope, json={'id': uuid4().hex, 'name': name})
    assert response.status_code == 201, response.text
    return response.json()['id']


def move(client, ids, target, versions=None, request=None):
    payload = {'request_id': request or uuid4().hex, 'folder_id': target,
               'documents': [{'id': d, 'expected_version': v} for d, v in zip(ids, versions or [0]*len(ids))]}
    return client.post(BASE + '/move' + SCOPE, json=payload)


def test_atomic_moves_keep_bytes_versions_sharing_and_replay(api):
    client, engine, _, current, _ = api
    first, second = new(client), new(client)
    target = folder(client)
    put_grants(client, f'{BASE}/{first}/grants{SCOPE}', json={'grants': [{'user_id': 'viewer', 'access': 'view'}]})
    before = client.get(f'{BASE}/{first}{SCOPE}').json()
    data = client.get(f'{BASE}/{first}/download{SCOPE}').content
    request = uuid4().hex
    assert move(client, [first, second], target, request=request).status_code == 200
    assert client.get(f'{BASE}/{first}{SCOPE}').json() == {**before, 'folder_id': target, 'placement_version': 1}
    assert client.get(f'{BASE}/{first}/download{SCOPE}').content == data
    items = client.get(BASE + SCOPE + '&folder_id=' + target).json()['items']
    assert len(items) == 2 and all(i['placement_version'] == 1 and i['folder_id'] == target for i in items)
    assert move(client, [first, second], None, [1, 1]).status_code == 200
    # Late retries acknowledge the original batch without undoing later moves.
    assert move(client, [first, second], target, request=request).status_code == 200
    assert client.get(BASE + SCOPE + '&folder_id=' + target).json()['items'] == []
    with Session(engine) as db:
        assert len(db.scalars(select(Revision)).all()) == 2
        assert len(db.scalars(select(Event).where(Event.kind == 'move')).all()) == 4
    current['user'] = 'viewer'
    items = client.get(BASE + SCOPE).json()['items']
    assert len(items) == 1 and 'folder_id' not in items[0] and 'placement_version' not in items[0]
    assert client.get(BASE + '/folders' + SCOPE).json()['items'] == []


def test_whole_batch_authorization_and_cas_failure_make_no_changes(api):
    client, engine, _, current, _ = api
    first = new(client); target = folder(client)
    current['user'] = 'editor'; other = new(client); other_folder = folder(client)
    current['user'] = 'owner'
    assert move(client, [first, other], target).status_code in (403, 404)
    assert move(client, [first], other_folder).status_code == 404
    assert move(client, [first, first], target).status_code == 422
    with Session(engine) as db:
        assert db.get(Placement, first) is None
    second = new(client)
    assert move(client, [second], target).status_code == 200
    assert move(client, [first, second], target).status_code == 409
    with Session(engine) as db:
        assert db.get(Placement, first) is None
    assert client.get(BASE + SCOPE + '&folder_id=' + other_folder).status_code == 404


def test_private_folders_bind_factory_epoch_and_shared_edit_is_not_owner(api):
    client, _, contexts, current, _ = api
    doc = new(client); target = folder(client)
    put_grants(client, f'{BASE}/{doc}/grants{SCOPE}', json={'grants': [{'user_id': 'editor', 'access': 'edit'}]})
    current['user'] = 'editor'
    own_folder = folder(client)
    assert move(client, [doc], own_folder).status_code == 403
    assert client.delete(BASE + '/folders/' + target + SCOPE).status_code == 404
    current['user'] = 'owner'
    contexts['owner'] = context('owner', epoch=2)
    assert client.get(BASE + '/folders' + SCOPE).json()['items'] == []
    assert client.get(BASE + SCOPE + '&folder_id=' + target).status_code == 404
    contexts['owner'] = context()
    group = folder(client, scope='?factory_id=group')
    assert move(client, [doc], group).status_code == 404


def test_creation_delete_retries_names_and_deleted_documents(api):
    client, engine, _, _, _ = api
    payload = {'id': uuid4().hex, 'name': '  成品进出  '}
    first = client.post(BASE + '/folders' + SCOPE, json=payload)
    assert first.status_code == 201
    assert client.post(BASE + '/folders' + SCOPE, json=payload).json() == first.json()
    assert client.post(BASE + '/folders' + SCOPE, json={**payload, 'id': uuid4().hex}).status_code == 409
    target = first.json()['id']
    doc = new(client)
    assert move(client, [doc], target).status_code == 200
    with Session(engine) as db:
        db.get(Document, doc).deleted_at = '2026-10-26'; db.commit()
    assert client.delete(BASE + '/folders/' + target + SCOPE).status_code == 409
    with Session(engine) as db:
        db.get(Document, doc).deleted_at = ''; db.commit()
    assert move(client, [doc], None, [1]).status_code == 200
    assert client.delete(BASE + '/folders/' + target + SCOPE).status_code == 200
    assert client.delete(BASE + '/folders/' + target + SCOPE).status_code == 200
    assert client.post(BASE + '/folders' + SCOPE, json=payload).status_code == 409
    assert client.get(BASE + '/folders' + SCOPE).json()['items'] == []
    assert folder(client) != target


def test_new_documents_in_folder_and_filter_before_list_limit(api):
    client, engine, _, _, _ = api
    target = folder(client)
    response = client.post(BASE + SCOPE, json={'title': '分类新建', 'format': 'xlsx', 'folder_id': target})
    assert response.status_code == 201
    doc = response.json()['id']
    assert client.get(BASE + SCOPE + '&folder_id=uncategorized').json()['items'] == []
    with Session(engine) as db:
        source = db.get(Document, doc)
        for i in range(205):
            values = {c.name: getattr(source, c.name) for c in Document.__table__.columns}
            values.update(id=uuid4().hex, updated_at='2099-01-01')
            db.add(Document(**values))
        db.commit()
    assert [d['id'] for d in client.get(BASE + SCOPE + '&folder_id=' + target).json()['items']] == [doc]
    assert client.post(BASE + SCOPE, json={'format': 'docx', 'folder_id': uuid4().hex}).status_code == 404
    upload = client.post(BASE + '/upload', data={'factory_id': 'huaxing', 'folder_id': target}, files={'file': ('归类上传.xlsx', workbook())})
    assert upload.status_code == 201, upload.text
    assert {d['id'] for d in client.get(BASE + SCOPE + '&folder_id=' + target).json()['items']} == {doc, upload.json()['id']}
