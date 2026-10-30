import pytest
from sqlalchemy.orm import Session
from test_online_documents import api, BASE, SCOPE, callback, new, open_editor, put_grants, workbook
from app.models.online_documents import OnlineDocument as Document
from app.services import online_documents as service, online_document_protocol as protocol


def collaboration(api):
    client, engine, users, current, monkey = api
    doc = new(client); path = f'{BASE}/{doc}'
    grants = [{'user_id': 'editor', 'access': 'edit'}, {'user_id': 'stranger', 'access': 'edit'}]
    shared = put_grants(client, path + '/grants' + SCOPE, json={'grants': grants}).json()
    owner = open_editor(client, doc)
    for who in ('editor', 'stranger'):
        current['user'] = who; client.cookies.set('rr_session', who)
        assert open_editor(client, doc)['document']['key'] == owner['document']['key']
    current['user'] = 'owner'; client.cookies.set('rr_session', 'owner')
    payload = {'version': shared['share_version'], 'grants': [{'user_id': 'stranger', 'epoch': 1, 'access': 'edit'}]}
    return doc, path, owner, payload


def test_targeted_revoke_keeps_other_editors_and_their_next_saves(api):
    client, engine, users, current, monkey = api
    doc, path, owner, payload = collaboration(api)
    key = owner['document']['key']; calls = []
    monkey.setattr(protocol, 'command', lambda p: calls.append(p) or {'error': 0})
    assert client.post(path + '/prepare-sharing' + SCOPE, json=payload).json() == {'ready': False}
    assert [p for p in calls if p['c'] == 'drop'] == [{'c': 'drop', 'key': key, 'users': ['editor_1']}]
    checkpoint = calls[-1]['userdata']
    saved = workbook('=SUM(11,22)')
    monkey.setattr(protocol, 'fetch_saved', lambda url: saved)
    event = {'key': key, 'status': 6, 'forcesavetype': 0, 'userdata': checkpoint,
             'users': ['editor_1'], 'url': 'http://onlyoffice/cache/files/checkpoint'}
    assert callback(client, doc, event).json() == {'error': 0}
    assert client.post(path + '/prepare-sharing' + SCOPE, json=payload).json() == {'ready': True}
    assert client.put(path + '/grants' + SCOPE, json=payload).status_code == 200
    with Session(engine) as db:
        record = db.get(Document, doc)
        assert record.editor_key == key
        assert {'owner_1', 'stranger_1'}.issubset(record.participants)
        assert record.participants['editor_1']['revoked']
        assert service.SHARING_STATE not in record.participants
    current['user'] = 'stranger'; client.cookies.set('rr_session', 'stranger')
    assert open_editor(client, doc)['document']['key'] == key
    nonce = client.post(path + '/save' + SCOPE).json()['request_id']
    later = workbook('=SUM(100,200)')
    monkey.setattr(protocol, 'fetch_saved', lambda url: later)
    assert callback(client, doc, {**event, 'userdata': nonce, 'users': ['stranger_1']}).json() == {'error': 0}
    assert client.get(path + '/download' + SCOPE).content == later
    current['user'] = 'editor'; client.cookies.set('rr_session', 'editor')
    assert client.post(path + '/editor' + SCOPE).status_code == 404


@pytest.mark.parametrize('status', [2, 6])
def test_revoked_last_editor_can_only_acknowledge_identical_checkpoint(api, status):
    client, engine, users, current, monkey = api
    doc, path, owner, payload = collaboration(api)
    key = owner['document']['key']
    monkey.setattr(protocol, 'command', lambda p: {'error': 4 if p['c'] == 'forcesave' else 0})
    assert client.post(path + '/prepare-sharing' + SCOPE, json=payload).json() == {'ready': True}
    assert client.put(path + '/grants' + SCOPE, json=payload).status_code == 200
    saved = client.get(path + '/download' + SCOPE).content
    monkey.setattr(protocol, 'command', lambda p: {'error': 0})
    nonce = client.post(path + '/save' + SCOPE).json()['request_id']
    event = {'key': key, 'status': status, 'forcesavetype': 0, 'userdata': nonce,
             'users': ['editor_1'], 'url': 'http://onlyoffice/cache/files/duplicate'}
    monkey.setattr(protocol, 'fetch_saved', lambda url: workbook('=999'))
    assert callback(client, doc, event).status_code == 403
    assert client.get(path + '/download' + SCOPE).content == saved
    monkey.setattr(protocol, 'fetch_saved', lambda url: saved)
    assert callback(client, doc, event).json() == {'error': 0}
    assert client.get(path + SCOPE).json()['revision'] == 1


def test_same_prepare_requests_cannot_overwrite_a_newer_checkpoint(api):
    client, engine, users, current, monkey = api
    doc, path, owner, payload = collaboration(api)
    calls = []; nested = False
    def command(packet):
        nonlocal nested
        calls.append(packet)
        if packet['c'] == 'drop' and not nested:
            nested = True
            assert client.post(path + '/prepare-sharing' + SCOPE, json=payload).json() == {'ready': False}
        return {'error': 0}
    monkey.setattr(protocol, 'command', command)
    assert client.post(path + '/prepare-sharing' + SCOPE, json=payload).json() == {'ready': False}
    saves = [p for p in calls if p['c'] == 'forcesave']
    assert len(saves) == 1
    with Session(engine) as db:
        record = db.get(Document, doc)
        assert record.participants[service.SHARING_STATE]['phase'] == 'saving'
        assert record.participants[service.SHARING_STATE]['request_id'] == record.pending_save == saves[0]['userdata']


def test_abandoned_prepare_expires_without_clearing_any_unsaved_content(api):
    client, engine, users, current, monkey = api
    doc, path, owner, payload = collaboration(api)
    monkey.setattr(protocol, 'command', lambda p: (_ for _ in ()).throw(TimeoutError()))
    assert client.post(path + '/prepare-sharing' + SCOPE, json=payload).status_code == 502
    original_time = service.time.time()
    monkey.setattr(service.time, 'time', lambda: original_time + 121)
    monkey.setattr(protocol, 'command', lambda p: {'error': 0})
    other = {'version': payload['version'], 'grants': [{'user_id': who, 'epoch': 1, 'access': 'edit'} for who in ('editor', 'stranger')]}
    assert client.post(path + '/prepare-sharing' + SCOPE, json=other).json() == {'ready': True}
    with Session(engine) as db:
        record = db.get(Document, doc)
        assert record.editor_key == owner['document']['key'] and record.revision == 1


def test_late_checkpoint_command_response_cannot_replace_a_newer_intent(api):
    client, engine, users, current, monkey = api
    doc, path, owner, payload = collaboration(api)
    saved = client.get(path + '/download' + SCOPE).content
    monkey.setattr(protocol, 'fetch_saved', lambda url: saved)
    other = {'version': payload['version'], 'grants': [{'user_id': who, 'epoch': 1, 'access': 'edit'} for who in ('editor', 'stranger')]}
    def command(packet):
        if packet['c'] == 'forcesave':
            assert callback(client, doc, {'key': owner['document']['key'], 'status': 6, 'forcesavetype': 0,
                'userdata': packet['userdata'], 'users': ['owner_1'], 'url': 'http://onlyoffice/cache/files/saved'}).json() == {'error': 0}
            assert client.post(path + '/prepare-sharing' + SCOPE, json=other).json() == {'ready': True}
        return {'error': 0}
    monkey.setattr(protocol, 'command', command)
    assert client.post(path + '/prepare-sharing' + SCOPE, json=payload).status_code == 409
    assert client.put(path + '/grants' + SCOPE, json=other).status_code == 200


def test_adding_a_colleague_never_drops_or_saves_existing_editors(api):
    client, engine, users, current, monkey = api
    doc = new(client); path = f'{BASE}/{doc}'; key = open_editor(client, doc)['document']['key']
    payload = {'version': client.get(path + SCOPE).json()['share_version'], 'grants': [{'user_id': 'viewer', 'epoch': 1, 'access': 'view'}]}
    calls = []; monkey.setattr(protocol, 'command', lambda p: calls.append(p) or {'error': 0})
    assert client.post(path + '/prepare-sharing' + SCOPE, json=payload).json() == {'ready': True}
    assert calls == [{'c': 'info', 'key': key}]
    assert client.put(path + '/grants' + SCOPE, json=payload).json()['editing']
