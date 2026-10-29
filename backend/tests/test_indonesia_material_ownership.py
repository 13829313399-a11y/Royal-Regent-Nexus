"""Two independent Sales accounts, a factory supervisor, and private document handoff."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from app.models.auth import AuthUser
from app.models.indonesia_materials import IndonesiaMaterialRecord as Record
from app.services import indonesia_materials as ledger, indonesia_material_ownership as ownership
from test_indonesia_materials import client, actor, command, material, product, workspace, schedule_bytes, BASE
from test_indonesia_warehouse_import import catalog, preview, source, confirm
from test_indonesia_master_import import workbook, source as master_source, preview as master_preview, choices


@pytest.fixture
def accounts(client, monkeypatch):
    staff = actor('read', 'write', 'export')
    people = {key: replace(staff, id=key, username=key, display_name=name, identity={'employment_epoch': 1})
              for key, name in [('alice', '跟客甲'), ('bob', '跟客乙')]}
    people['manager'] = replace(actor('read', 'write', 'export', role='position_sales_supervisor'),
                                id='manager', username='manager', display_name='业务主管', identity={'employment_epoch': 1})
    AuthUser.__table__.create(client.engine)
    with Session(client.engine) as db:
        for user in people.values():
            db.add(AuthUser(id=user.id, username=user.username, display_name=user.display_name, password_salt='', password_hash='', status='active'))
        db.commit()
    # Keep this module test isolated from IAM's database fixtures. Canonical grants/denies
    # and the production active-account directory/target lookup still execute unchanged.
    monkeypatch.setattr(ownership, 'build_auth_context', lambda db, account: people[account.id])
    client.materials_auth['user'] = people['alice']
    return people


def login(client, accounts, name):
    client.materials_auth['user'] = accounts[name]


def ids(client):
    return {row['id'] for row in workspace(client)['records']}


def schedule_preview(client):
    response = client.post(BASE + '/imports/preview', data=dict(factory_id='huaxing', customer='合成客户', recipient='RRI'),
                           files={'file': ('schedule.xlsx', schedule_bytes())})
    assert response.status_code == 200, response.text
    return response.json()['record']


def source_file(client, row):
    return client.get(BASE + '/assets/' + row['data']['asset_id'], params={'factory_id': 'huaxing'})


def test_old_operation_receipt_cannot_be_replayed_by_a_rehired_identity(client, accounts):
    product(client, material(client), code='00001'); row = schedule_preview(client)
    operation = uuid4().hex
    command(client, 'import_confirm', {'indexes': [0]}, row, operation_id=operation)
    accounts['alice'] = replace(accounts['alice'], identity={'employment_epoch': 2})
    login(client, accounts, 'alice')
    command(client, 'import_confirm', {'indexes': [0]}, row, operation_id=operation, status=403)


def test_replay_resolves_completed_operation_without_leaking_after_handoff_or_demotion(client, accounts):
    catalog(client); original = preview(client, source(), source(receipt_no='SECOND', purchase_no='SECOND'))
    operation = uuid4().hex
    posted = confirm(client, original, operation_id=operation)
    login(client, accounts, 'manager')
    transfer_op = uuid4().hex
    command(client, 'draft_transfer', dict(assignee_id='bob', reason='交接'), posted, operation_id=transfer_op)
    login(client, accounts, 'alice')
    # No second posting; receipt stays immutable, but its private result is no longer visible.
    failure = confirm(client, original, operation_id=operation, status=404)
    assert '原操作已完成' in failure.text
    accounts['manager'] = replace(accounts['manager'], grants=accounts['alice'].grants)
    login(client, accounts, 'manager')
    failure = command(client, 'draft_transfer', dict(assignee_id='bob', reason='交接'), posted, operation_id=transfer_op, status=404)
    assert '原操作已完成' in failure.text
    assert posted['id'] not in ids(client)


@pytest.mark.parametrize('kind', ['schedule', 'master', 'warehouse'])
def test_two_accounts_have_independent_previews_and_cannot_process_or_download_each_others(client, accounts, kind):
    m = material(client); p = product(client, m, code='00001')
    create = {'schedule': lambda: schedule_preview(client),
              'master': lambda: master_preview(client, workbook([master_source(item='00001')]), p),
              'warehouse': lambda: preview(client)}[kind]
    action = {'schedule': 'import_confirm', 'master': 'master_import_confirm', 'warehouse': 'warehouse_import_confirm'}[kind]
    first = create()
    assert first['responsibility']['assignee']['id'] == 'alice'
    assert source_file(client, first).status_code == 200
    assert create()['id'] == first['id']
    login(client, accounts, 'bob')
    assert first['id'] not in ids(client)
    assert source_file(client, first).status_code == 404
    command(client, action, {}, first, status=404)
    second = create()
    assert first['id'] != second['id']
    assert second['responsibility']['assignee']['id'] == 'bob'
    login(client, accounts, 'alice')
    assert second['id'] not in ids(client)
    login(client, accounts, 'manager')
    assert {first['id'], second['id']} <= ids(client)
    assert source_file(client, first).status_code == 200


def test_transfer_changes_responsibility_not_uploader_and_old_versions_cannot_write(client, accounts):
    product(client, material(client), code='00001')
    first = schedule_preview(client)
    command(client, 'draft_transfer', dict(assignee_id='bob', reason='工作交接'), first, status=403)
    login(client, accounts, 'manager')
    key = uuid4().hex
    assigned = command(client, 'draft_transfer', dict(assignee_id='bob', reason='工作交接'), first, operation_id=key)
    assert command(client, 'draft_transfer', dict(assignee_id='bob', reason='工作交接'), first, operation_id=key) == assigned
    assert assigned['responsibility']['uploader']['id'] == 'alice'
    assert assigned['responsibility']['assignee']['id'] == 'bob'
    assert len(assigned['responsibility']['transfers']) == 1
    login(client, accounts, 'alice')
    assert assigned['id'] not in ids(client)
    command(client, 'import_confirm', {'indexes': [0]}, assigned, status=404)
    assert source_file(client, assigned).status_code == 404
    assert schedule_preview(client)['id'] != assigned['id']  # no reclaim via file deduplication
    login(client, accounts, 'bob')
    command(client, 'import_confirm', {'indexes': [0]}, first, status=409)
    formal = command(client, 'import_confirm', {'indexes': [0]}, assigned)
    formal_order = formal['data']['order_ids'][0]
    login(client, accounts, 'alice')
    assert formal_order in ids(client)
    assert assigned['id'] not in ids(client)  # original file can include skipped rows
    login(client, accounts, 'manager')
    command(client, 'draft_transfer', dict(assignee_id='alice', reason='已完成不能转交'), formal, status=422)


def test_receipt_to_packing_confirmation_and_excel_share_only_formal_results(client, accounts):
    catalog(client)
    imported = preview(client)
    login(client, accounts, 'manager')
    assigned = command(client, 'draft_transfer', dict(assignee_id='bob', reason='跟客接手'), imported)
    assigned = next(row for row in workspace(client)['records'] if row['id'] == assigned['id'])
    # Supervisor processing on behalf of a follower must retain that follower's ownership.
    posted = confirm(client, assigned)
    shipping_id = posted['data']['shipment_ids'][0]
    login(client, accounts, 'alice')
    assert shipping_id not in ids(client)
    assert any(row['kind'] == 'supply' for row in workspace(client)['records'])
    login(client, accounts, 'bob')
    shipment = next(row for row in workspace(client)['records'] if row['id'] == shipping_id)
    assert shipment['responsibility']['uploader']['id'] == 'alice'
    assert shipment['responsibility']['assignee']['id'] == 'bob'
    data = {key: shipment['data'][key] for key in ('customer', 'recipient', 'shipment_date', 'lines', 'packages', 'remarks')}
    data['packages'] = [dict(label='箱1', cartons=1, length_cm='27', width_cm='14.5', height_cm='27.3',
                              carton_weight_kg='.02', items=deepcopy(data['lines']))]
    login(client, accounts, 'alice')
    command(client, 'shipment_save', data, shipment, status=404)
    command(client, 'shipment_confirm', {}, shipment, status=404)
    login(client, accounts, 'bob')
    saved = command(client, 'shipment_save', data, shipment)
    assert saved['responsibility']['assignee']['id'] == 'bob'
    done = command(client, 'shipment_confirm', {}, saved)
    login(client, accounts, 'alice')
    assert done['id'] in ids(client)
    result = client.get(BASE + f"/shipments/{done['id']}/export", params={'factory_id': 'huaxing'})
    assert result.status_code == 200 and result.content.startswith(b'PK')
    assert source_file(client, posted).status_code == 404


def test_partial_import_and_confirmed_import_do_not_expose_other_private_shipment_ids(client, accounts):
    catalog(client, quantity='200')
    imported = preview(client, source(), source(receipt_no='WH-002', purchase_no='PO-002'))
    posted = confirm(client, imported)
    assert posted['data']['status'] == 'partial'
    shipping_id = posted['data']['shipment_ids'][0]
    login(client, accounts, 'bob')
    assert imported['id'] not in ids(client) and shipping_id not in ids(client)
    duplicate = preview(client, source())
    assert duplicate['data']['rows'][0]['blocked']  # global receipt dedup still applies
    login(client, accounts, 'manager')
    shipment = next(row for row in workspace(client)['records'] if row['id'] == shipping_id)
    command(client, 'draft_transfer', dict(assignee_id='bob', reason='装箱交接'), shipment)
    login(client, accounts, 'alice')
    visible_import = next(row for row in workspace(client)['records'] if row['id'] == imported['id'])
    assert visible_import['data']['shipment_ids'] == []


def test_master_confirmation_shares_materials_but_not_skipped_source_rows(client, accounts):
    m = material(client); p = product(client, m, code='40149')
    original = master_preview(client, workbook([master_source(), master_source(code='UNSELECTED', name='未选资料')]), p)
    payload = choices(original); payload['choices'] = payload['choices'][:1]
    done = command(client, 'master_import_confirm', payload, original)
    login(client, accounts, 'bob')
    assert done['id'] not in ids(client)
    assert any(row['kind'] == 'material' and row['data']['code'] == 'M-NEW' for row in workspace(client)['records'])
    assert source_file(client, done).status_code == 404


def test_target_directory_and_transfer_recheck_permissions_and_account_availability(client, accounts):
    product(client, material(client), code='00001'); row = schedule_preview(client)
    assert client.get(BASE + '/draft-assignees', params={'factory_id': 'huaxing'}).status_code == 403
    login(client, accounts, 'manager')
    directory = client.get(BASE + '/draft-assignees', params={'factory_id': 'huaxing', 'search': '跟客乙'})
    assert directory.status_code == 200 and [p['id'] for p in directory.json()['people']] == ['bob']
    accounts['bob'] = replace(accounts['bob'], grants=(), permissions=frozenset())
    command(client, 'draft_transfer', dict(assignee_id='bob', reason='失去权限'), row, status=422)
    with Session(client.engine) as db:
        db.get(AuthUser, 'alice').status = 'suspended'; db.commit()
    command(client, 'draft_transfer', dict(assignee_id='alice', reason='停用账号'), row, status=422)
    command(client, 'draft_transfer', dict(assignee_id='missing', reason='不存在'), row, status=422)
    accounts['manager'] = replace(accounts['manager'], grants=(accounts['alice'].grants[0], replace(accounts['manager'].grants[0], factory_id='huadeng')))
    login(client, accounts, 'manager')
    assert row['id'] not in ids(client)
    command(client, 'draft_transfer', dict(assignee_id='bob', reason='异厂主管'), row, status=403)


def test_legacy_upload_and_shipment_attribution_and_unowned_queue(client, accounts):
    catalog(client); original = preview(client); posted = confirm(client, original)
    shipment_id = posted['data']['shipment_ids'][0]
    with Session(client.engine) as db:
        for id in [original['id'], shipment_id]:
            row = db.get(Record, id); row.data = {k: v for k, v in row.data.items() if k != '_ownership'}
        unknown = ledger.Ledger(db, 'huaxing').save('import', dict(status='preview', import_type='material_master', groups=[], products=[], filename='legacy.xlsx'))
        unknown_id = unknown.id; db.commit()
    assert {original['id'], shipment_id} <= ids(client)
    login(client, accounts, 'bob'); assert not {original['id'], shipment_id, unknown_id} & ids(client)
    login(client, accounts, 'manager'); unknown = next(row for row in workspace(client)['records'] if row['id'] == unknown_id)
    assigned = command(client, 'draft_transfer', dict(assignee_id='bob', reason='核对历史归属'), unknown)
    assert assigned['responsibility']['uploader'] is None
    login(client, accounts, 'bob'); assert unknown_id in ids(client)
    accounts['alice'] = replace(accounts['alice'], identity={'employment_epoch': 2})
    login(client, accounts, 'alice'); assert original['id'] not in ids(client) and shipment_id not in ids(client)


@pytest.mark.parametrize('endpoint', ['command', 'schedule', 'master', 'warehouse'])
def test_identity_generation_change_during_request_does_not_adopt_old_work(client, accounts, monkeypatch, endpoint):
    from app.api import indonesia_materials as api
    product(client, material(client), code='00001')
    before = ids(client)
    monkeypatch.setattr(api, 'refresh_user', lambda request, db: replace(accounts['alice'], identity={'employment_epoch': 2}))
    if endpoint == 'command':
        command(client, 'customer_save', dict(name='不得保存'), status=401)
    elif endpoint == 'schedule':
        response = client.post(BASE + '/imports/preview', data=dict(factory_id='huaxing', customer='合成客户', recipient='RRI'), files={'file': ('x.xlsx', schedule_bytes())})
        assert response.status_code == 401
    elif endpoint == 'warehouse':
        preview(client, status=401)
    else:
        p = next(row for row in workspace(client)['records'] if row['kind'] == 'product')
        master_preview(client, workbook([master_source(item='00001')]), p, status=401)
    assert ids(client) == before
