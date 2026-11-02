"""Isolated monthly-template and multi-window management regressions."""
from io import BytesIO
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_online_documents import api, BASE, SCOPE, callback, context, new, open_editor, put_grants, workbook
from test_online_document_management import upload, enable, mutate, payload
from test_online_document_folders import folder, move
from test_online_document_convenience import copy_request
from app.models.online_documents import OnlineDocument as Document, OnlineDocumentEvent as Event
from app.services import online_document_protocol as protocol, online_document_protection as protection


def test_monthly_copy_accepts_input_but_retains_formula_guard_and_original(api):
    client, engine, _, _, monkey = api
    source = upload(client)
    template = enable(client, source)
    original = client.get(f'{BASE}/{source}{SCOPE}').json()
    copied = client.post(f'{BASE}/{source}/copy{SCOPE}', json=copy_request(client, source, title='十一月月报')).json()['id']
    key = open_editor(client, copied)['document']['key']
    candidate = mutate(template, 'xl/worksheets/sheet1.xml', lambda root: setattr(
        root.find('.//' + protection.Q('c') + '[@r="B1"]/' + protection.Q('v')), 'text', '99'))
    monkey.setattr(protocol, 'command', lambda _: {'error': 0})
    request = client.post(f'{BASE}/{copied}/save{SCOPE}').json()['request_id']
    monkey.setattr(protocol, 'fetch_saved', lambda _: candidate)
    saved = {'status': 6, 'forcesavetype': 0, 'userdata': request, 'key': key,
             'users': ['owner_1'], 'url': 'http://onlyoffice/cache/files/month.xlsx'}
    assert callback(client, copied, saved).json() == {'error': 0}
    assert load_workbook(BytesIO(client.get(f'{BASE}/{copied}/download{SCOPE}').content)).active['B1'].value == 99
    bad = mutate(candidate, 'xl/worksheets/sheet1.xml', lambda root: setattr(
        root.find('.//' + protection.Q('c') + '[@r="C1"]/' + protection.Q('f')), 'text', '0'))
    request = client.post(f'{BASE}/{copied}/save{SCOPE}').json()['request_id']
    monkey.setattr(protocol, 'fetch_saved', lambda _: bad)
    assert callback(client, copied, {**saved, 'userdata': request}).json() == {'error': 1}
    assert client.get(f'{BASE}/{copied}{SCOPE}').json()['revision'] == 2
    assert client.get(f'{BASE}/{source}/download{SCOPE}').content == template
    assert client.get(f'{BASE}/{source}{SCOPE}').json() == original
    with Session(engine) as db:
        assert db.get(Document, copied).protection['baseline_revision'] == 1


def test_copy_of_pending_save_stays_on_displayed_revision_and_replay_never_upgrades(api):
    client, engine, _, _, monkey = api
    source = new(client)
    original = client.get(f'{BASE}/{source}/download{SCOPE}').content
    key = open_editor(client, source)['document']['key']
    monkey.setattr(protocol, 'command', lambda _: {'error': 0})
    save_request = client.post(f'{BASE}/{source}/save{SCOPE}').json()['request_id']
    request = copy_request(client, source)
    copied = client.post(f'{BASE}/{source}/copy{SCOPE}', json=request).json()['id']
    assert client.get(f'{BASE}/{copied}/download{SCOPE}').content == original
    monkey.setattr(protocol, 'fetch_saved', lambda _: workbook('=123'))
    assert callback(client, source, {'status': 6, 'forcesavetype': 0, 'userdata': save_request, 'key': key,
        'users': ['owner_1'], 'url': 'http://onlyoffice/cache/files/pending.xlsx'}).json() == {'error': 0}
    assert client.post(f'{BASE}/{source}/copy{SCOPE}', json=request).json()['id'] == copied
    assert client.get(f'{BASE}/{copied}/download{SCOPE}').content == original
    stale = client.post(f'{BASE}/{source}/copy{SCOPE}', json={**request, 'request_id': uuid4().hex})
    assert stale.status_code == 409 and '新版本' in stale.json()['detail']
    with Session(engine) as db:
        assert db.query(Document).count() == 2


def test_two_windows_rename_and_inflight_save_keep_latest_name_and_content(api):
    client, engine, _, _, monkey = api
    source = new(client)
    key = open_editor(client, source)['document']['key']
    commands = []
    monkey.setattr(protocol, 'command', lambda command: commands.append(command) or {'error': 0})
    request = client.post(f'{BASE}/{source}/save{SCOPE}').json()['request_id']
    url = f'{BASE}/{source}/title{SCOPE}'
    first = client.patch(url, json={'title': '十一月', 'expected_title': '公式核验', 'expected_version': 1})
    assert first.status_code == 200
    assert client.patch(url, json={'title': '旧窗口名称', 'expected_title': '公式核验', 'expected_version': 1}).status_code == 409
    assert client.patch(url, json={'title': '十一月定稿', 'expected_title': '十一月', 'expected_version': 2}).status_code == 200
    monkey.setattr(protocol, 'fetch_saved', lambda _: workbook('=789'))
    assert callback(client, source, {'status': 6, 'forcesavetype': 0, 'userdata': request, 'key': key,
        'users': ['owner_1'], 'url': 'http://onlyoffice/cache/files/save.xlsx'}).json() == {'error': 0}
    detail = client.get(f'{BASE}/{source}{SCOPE}').json()
    assert detail['title'] == '十一月定稿' and detail['revision'] == 2 and detail['saved_request'] == request
    assert open_editor(client, source)['document']['title'] == '十一月定稿.xlsx'
    assert load_workbook(BytesIO(client.get(f'{BASE}/{source}/download{SCOPE}').content)).active['A1'].value == '=789'
    with Session(engine) as db:
        assert len(db.scalars(select(Event).where(Event.kind == 'rename')).all()) == 2
    assert [c['meta']['title'] for c in commands if c['c'] == 'meta'] == ['十一月.xlsx', '十一月定稿.xlsx']


@pytest.mark.parametrize('role', ['viewer', 'editor'])
def test_shared_roles_cannot_copy_rename_or_rename_owners_folder(api, role):
    client, _, _, current, _ = api
    source = new(client)
    target = folder(client)
    request = copy_request(client, source)
    assert put_grants(client, f'{BASE}/{source}/grants{SCOPE}', json={'grants': [
        {'user_id': role, 'access': 'view' if role == 'viewer' else 'edit'}]}).status_code == 200
    current['user'] = role
    assert client.get(f'{BASE}/{source}{SCOPE}').status_code == 200
    assert client.post(f'{BASE}/{source}/copy{SCOPE}', json=request).status_code == 403
    assert client.patch(f'{BASE}/{source}/title{SCOPE}', json={'title': '越权名称', 'expected_title': '公式核验', 'expected_version': 1}).status_code == 403
    assert client.patch(f'{BASE}/folders/{target}{SCOPE}', json={'name': '越权文件夹', 'expected_name': '成品进出', 'expected_version': 1}).status_code == 404


def test_lost_copy_response_replay_after_source_trash_and_identity_changes(api):
    client, engine, users, current, _ = api
    source = new(client)
    request = copy_request(client, source)
    url = f'{BASE}/{source}/copy{SCOPE}'
    copied = client.post(url, json=request).json()['id']
    assert client.post(f'{BASE}/{source}/trash{SCOPE}', json=payload(client, source)).status_code == 200
    assert client.post(url, json=request).json()['id'] == copied
    current['user'] = 'stranger'
    assert client.post(url, json=request).status_code == 404
    current['user'] = 'owner'
    users['owner'] = context(epoch=2)
    assert client.post(url, json=request).status_code == 404
    users['owner'] = context(factory='huakang-a')
    assert client.post(url, json=request).status_code == 403
    users['owner'] = context()
    assert client.post(url.replace('huaxing', 'group'), json=request).status_code == 404
    assert client.post(url, json={**request, 'request_id': uuid4().hex}).status_code == 409
    with Session(engine) as db:
        assert db.query(Document).count() == 2


def test_two_window_folder_rename_does_not_change_document_or_move_version(api):
    client, _, _, _, _ = api
    source = new(client)
    target = folder(client, '十月')
    assert move(client, [source], target).status_code == 200
    original = client.get(f'{BASE}/{source}{SCOPE}').json()
    url = f'{BASE}/folders/{target}{SCOPE}'
    first = client.patch(url, json={'name': '十一月', 'expected_name': '十月', 'expected_version': 1})
    assert first.status_code == 200 and first.json()['version'] == 2
    assert client.patch(url, json={'name': '旧窗口改名', 'expected_name': '十月', 'expected_version': 1}).status_code == 409
    replay = client.patch(url, json={'name': '十一月', 'expected_name': '十月', 'expected_version': 1})
    assert replay.status_code == 200 and replay.json()['version'] == 2
    assert client.get(f'{BASE}/{source}{SCOPE}').json() == original
    listed = client.get(BASE + SCOPE + '&folder_id=' + target).json()['items'][0]
    assert listed['id'] == source and listed['placement_version'] == 1


def test_copy_confirmation_detail_refreshes_current_folder_after_other_window_moves(api):
    client, _, _, _, _ = api
    source = new(client)
    first, second = folder(client, '十月'), folder(client, '十一月')
    assert move(client, [source], first).status_code == 200
    stale = client.get(BASE + SCOPE).json()['items'][0]
    assert stale['folder_id'] == first
    assert move(client, [source], second, [1]).status_code == 200
    # startCopy merges this detail over the cached row before deriving folder_id.
    fresh = client.get(f'{BASE}/{source}{SCOPE}').json()
    confirmation = {**stale, **fresh}
    assert confirmation['folder_id'] == second, 'Copy confirmation retains the old window folder after a concurrent move'
    assert confirmation['placement_version'] == 2


def test_copy_confirmation_explicit_null_removes_previous_folder(api):
    client, _, _, _, _ = api
    source = new(client)
    target = folder(client, '月报')
    assert move(client, [source], target).status_code == 200
    stale = client.get(BASE + SCOPE).json()['items'][0]
    assert move(client, [source], None, [1]).status_code == 200
    fresh = client.get(f'{BASE}/{source}{SCOPE}').json()
    assert 'folder_id' in fresh and fresh['folder_id'] is None
    confirmation = {**stale, **fresh}
    assert confirmation['folder_id'] is None and confirmation['placement_version'] == 2
    copied = client.post(f'{BASE}/{source}/copy{SCOPE}', json=copy_request(
        client, source, folder_id=confirmation['folder_id'])).json()['id']
    assert any(row['id'] == copied for row in client.get(BASE + SCOPE + '&folder_id=uncategorized').json()['items'])


def test_lost_folder_rename_response_cannot_replay_over_later_reverted_name(api):
    client, _, _, _, _ = api
    target = folder(client, '十月')
    url = f'{BASE}/folders/{target}{SCOPE}'
    original = {'name': '十一月', 'expected_name': '十月', 'expected_version': 1}
    first = client.patch(url, json=original)
    assert first.status_code == 200 and first.json()['version'] == 2
    second = client.patch(url, json={'name': '十月', 'expected_name': '十一月', 'expected_version': 2})
    assert second.status_code == 200 and second.json()['version'] == 3
    # The first response was lost. An exact retry must not undo the second window.
    assert client.patch(url, json=original).status_code == 409
    current = next(item for item in client.get(BASE + '/folders' + SCOPE).json()['items'] if item['id'] == target)
    assert current['name'] == '十月' and current['version'] == 3


def test_lost_document_rename_response_cannot_replay_over_later_reverted_name(api):
    client, engine, _, _, _ = api
    source = new(client)
    url = f'{BASE}/{source}/title{SCOPE}'
    original = {'title': '十一月', 'expected_title': '公式核验', 'expected_version': 1}
    first = client.patch(url, json=original)
    assert first.status_code == 200 and first.json()['state_version'] == 2
    replay = client.patch(url, json=original)
    assert replay.status_code == 200 and replay.json()['state_version'] == 2
    second = client.patch(url, json={'title': '公式核验', 'expected_title': '十一月', 'expected_version': 2})
    assert second.status_code == 200 and second.json()['state_version'] == 3
    assert client.patch(url, json=original).status_code == 409
    current = client.get(f'{BASE}/{source}{SCOPE}').json()
    assert current['title'] == '公式核验' and current['state_version'] == 3
    with Session(engine) as db:
        assert len(db.scalars(select(Event).where(Event.document_id == source, Event.kind == 'rename')).all()) == 2


def test_recent_order_filters_private_trash_factory_and_old_epoch_ids(api):
    client, _, users, current, _ = api
    first, second, third, trashed = [new(client) for _ in range(4)]
    assert client.post(f'{BASE}/{trashed}/trash{SCOPE}', json=payload(client, trashed)).status_code == 200
    group = client.post(BASE + '?factory_id=group', json={'title': '集团私有', 'format': 'xlsx'}).json()['id']
    current['user'] = 'editor'
    private, shared = new(client), new(client)
    assert put_grants(client, f'{BASE}/{shared}/grants{SCOPE}', json={
        'grants': [{'user_id': 'owner', 'access': 'edit'}]}).status_code == 200
    current['user'] = 'owner'
    injected = [private, trashed, group, third, shared, first, 'missing', second, first]
    result = client.get(BASE, params={'factory_id': 'huaxing', 'sort': 'recent', 'recent_ids': ','.join(injected)})
    assert result.status_code == 200
    items = result.json()['items']
    assert [item['id'] for item in items] == [third, shared, first, second]
    assert 'folder_id' not in next(item for item in items if item['id'] == shared)
    target = folder(client, '近期月报')
    assert move(client, [first], target).status_code == 200
    filtered = client.get(BASE, params={'factory_id': 'huaxing', 'sort': 'recent', 'recent_ids': ','.join(injected), 'folder_id': target})
    assert [item['id'] for item in filtered.json()['items']] == [first]
    users['owner'] = context(epoch=2)
    rehired = new(client)
    result = client.get(BASE, params={'factory_id': 'huaxing', 'sort': 'recent', 'recent_ids': ','.join([*injected, rehired])})
    assert [item['id'] for item in result.json()['items']] == [rehired]


@pytest.mark.parametrize('order', ['updated', 'name', 'name_desc'])
def test_sort_precedes_200_cap_and_private_documents_never_consume_visible_quota(api, order):
    client, engine, _, _, _ = api
    source = new(client)
    ids = []
    with Session(engine) as db:
        original = db.get(Document, source)
        template = {column.name: getattr(original, column.name) for column in Document.__table__.columns}
        for index in range(206):
            document_id = source if index == 0 else uuid4().hex
            ids.append(document_id)
            values = {**template, 'id': document_id, 'title': f'Month-{index:03}',
                      'updated_at': (datetime(2026, 10, 26, tzinfo=timezone.utc) + timedelta(seconds=index)).isoformat()}
            if index == 0:
                original.title, original.updated_at = values['title'], values['updated_at']
            else:
                db.add(Document(**values))
        # These sort before all visible rows. Filtering must happen before the cap.
        for index in range(205):
            db.add(Document(**{**template, 'id': uuid4().hex, 'owner_id': 'editor',
                'title': f'A-private-{index:03}', 'updated_at': '2099-01-01T00:00:00Z'}))
        db.commit()
    result = client.get(BASE, params={'factory_id': 'huaxing', 'sort': order})
    assert result.status_code == 200
    expected = ids[:200] if order == 'name' else ids[::-1][:200]
    assert [item['id'] for item in result.json()['items']] == expected


def test_recent_input_limits_empty_state_and_unknown_sort(api):
    client, _, _, _, _ = api
    assert client.get(BASE, params={'factory_id': 'huaxing', 'sort': 'recent'}).json()['items'] == []
    ids = [f'not-existing-{index}' for index in range(101)]
    allowed = client.get(BASE, params={'factory_id': 'huaxing', 'sort': 'recent', 'recent_ids': ','.join(ids[:100])})
    assert allowed.status_code == 200 and allowed.json()['items'] == []
    assert client.get(BASE, params={'factory_id': 'huaxing', 'sort': 'recent', 'recent_ids': ','.join(ids)}).status_code == 422
    assert client.get(BASE, params={'factory_id': 'huaxing', 'sort': 'recent', 'recent_ids': 'x' * 65}).status_code == 422
    assert client.get(BASE, params={'factory_id': 'huaxing', 'sort': 'unknown'}).status_code == 422
