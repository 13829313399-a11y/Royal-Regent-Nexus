import importlib
import json

from sqlalchemy import select

from test_molding_sample_api import login_as, make_client
from test_carton_mark_api import _pdf_bytes
from test_carton_mark_assets import seed_order


def upload(client, status='DRAFT', note='', previous=None, name='4500222793.pdf'):
    options = dict(status=status, note=note)
    if previous:
        options.update(previous_asset_id=previous['id'], previous_revision=previous['revision'])
    response = client.post('/api/carton-mark/assets/batch', data={
        'factory_id': 'huaxing', 'options_json': json.dumps([options])}, files=[('files', (name, _pdf_bytes()))])
    assert response.status_code == 200, response.text
    return response.json()[0]


def change(client, asset, status, note=''):
    return client.put(f"/api/carton-mark/assets/{asset['id']}/classification?factory_id=huaxing",
        json=dict(revision=asset['revision'], status=status, note=note))


def listing(client):
    response = client.get('/api/carton-mark/assets?factory_id=huaxing')
    assert response.status_code == 200, response.text
    return {row['id']: row for row in response.json()}


def test_upload_classify_audits_legacy_and_qc_independence(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        first = upload(client, 'READY', '客户邮件确认')['asset']
        assert first['workflow']['status'] == 'READY'
        assert first['workflow']['confirmed_by_name'] and first['workflow']['confirmed_at']
        assert first['workflow']['confirmation_note'] == '客户邮件确认'
        changed = change(client, first, 'DRAFT', '客户要求改地址')
        assert changed.status_code == 200, changed.text
        assert changed.json()['workflow']['status'] == 'DRAFT'
        assert change(client, first, 'READY').status_code == 409
        history = client.get(f"/api/carton-mark/assets/{first['id']}/classification-history?factory_id=huaxing").json()
        assert [event['workflow']['status'] for event in history] == ['DRAFT', 'READY']
        assert history[1]['workflow']['confirmation_note'] == '客户邮件确认'
        db_module = importlib.import_module('app.db')
        models = importlib.import_module('app.models.carton_mark')
        with db_module.SessionLocal() as db:
            assert list(db.scalars(select(models.CartonMarkTemplate))) == []
            # Legacy originals have no classification event: never infer approval.
            original = db.get(models.CartonMarkAsset, first['id'])
            legacy = models.CartonMarkAsset(id='CMA-legacy', factory_id='huaxing', file_name='old.pdf',
                kind='pdf', content_type='application/pdf', size_bytes=original.size_bytes,
                sha256=original.sha256, content=original.content, created_by='seed', created_by_name='seed',
                created_at='2020-01-01', updated_at='2020-01-01')
            db.add(legacy); db.commit()
        assert listing(client)['CMA-legacy']['workflow']['status'] == 'UNCLASSIFIED'


def test_new_version_inherits_binding_requires_confirmation_and_preserves_original(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        db_module = importlib.import_module('app.db')
        carton = importlib.import_module('app.models.carton_procurement')
        with db_module.SessionLocal() as db:
            seed_order(db, carton, 'version-order')
        first = upload(client, 'READY', '历史确认稿')['asset']
        original_bytes = client.get(f"/api/carton-mark/assets/{first['id']}/document?factory_id=huaxing").content
        rejected = upload(client, 'READY', previous=first)
        assert rejected['status'] == 'failed'
        assert len(listing(client)) == 1
        second = upload(client, 'PENDING', '修改地址', first, '修订稿.pdf')['asset']
        assert second['workflow']['version'] == 2
        assert second['workflow']['previous_asset_id'] == first['id']
        assert second['workflow']['confirmed_at'] == ''
        assert second['orders'] == first['orders']
        rows = listing(client)
        assert rows[first['id']]['workflow']['status'] == 'READY'
        assert upload(client, previous=first)['status'] == 'failed'  # stale parent revision
        assert upload(client, previous=rows[first['id']])['status'] == 'failed'  # parallel successor
        # An original manually retired while its revision is pending must still
        # become permanently superseded when the new revision is confirmed.
        assert change(client, rows[first['id']], 'HISTORY').status_code == 200
        approved = change(client, second, 'READY', '客户同意新稿')
        assert approved.status_code == 200, approved.text
        rows = listing(client)
        assert rows[first['id']]['workflow']['status'] == 'HISTORY'
        assert rows[first['id']]['workflow']['superseded_by_asset_id'] == second['id']
        assert rows[second['id']]['workflow']['status'] == 'READY'
        assert change(client, rows[first['id']], 'READY').status_code == 409
        assert client.get(f"/api/carton-mark/assets/{first['id']}/document?factory_id=huaxing").content == original_bytes
        # Simple archival is reversible until a later version actually supersedes it.
        history = change(client, rows[second['id']], 'HISTORY', '暂时停用').json()
        assert change(client, history, 'PENDING', '重新核实').status_code == 200


def test_classification_factory_and_write_permissions_and_invalid_batch(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        asset = upload(client)['asset']
        url = f"/api/carton-mark/assets/{asset['id']}/classification"
        payload = dict(revision=asset['revision'], status='READY', note='')
        assert client.put(url + '?factory_id=huakang-a', json=payload).status_code == 404
        assert client.get(f"/api/carton-mark/assets/{asset['id']}/classification-history?factory_id=huakang-a").status_code == 404
        bad = client.post('/api/carton-mark/assets/batch', data={'factory_id': 'huaxing', 'options_json': '[{"status":"INVALID"}]'},
            files=[('files', ('bad.pdf', _pdf_bytes()))])
        assert bad.status_code == 422
        assert len(listing(client)) == 1
        login_as(client, 'qc_inspector')
        assert client.put(url + '?factory_id=huaxing', json=payload).status_code == 403


def test_changed_binding_blocks_new_version_approval_atomically(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        first = upload(client, 'READY')['asset']
        second = upload(client, previous=first)['asset']
        bound = client.put(f"/api/carton-mark/assets/{second['id']}/binding?factory_id=huaxing",
            json=dict(revision=second['revision'], contract_number='OTHER-CONTRACT')).json()
        response = change(client, bound, 'READY')
        assert response.status_code == 409
        rows = listing(client)
        assert rows[first['id']]['workflow']['status'] == 'READY'
        assert rows[second['id']]['revision'] == bound['revision']
        assert rows[second['id']]['workflow']['status'] == 'DRAFT'


def test_supplier_sees_classification_but_cannot_confirm_or_read_internal_history(monkeypatch):
    from test_carton_supplier_portal import setup_portal, supplier_login
    from test_carton_supplier_mark_assets import add_asset
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin')
        db_module = importlib.import_module('app.db')
        with db_module.SessionLocal() as db:
            add_asset(db, 'supplier-workflow', order['contract_no'])
            db.commit()
        asset = listing(client)['supplier-workflow']
        confirmed = change(client, asset, 'READY', '客户签样确认').json()
        supplier_login(client)
        rows = client.get('/api/carton-supplier/carton-mark/assets?factory_id=huaxing').json()
        assert rows[0]['workflow']['status'] == 'READY'
        assert rows[0]['workflow']['confirmation_note'] == '客户签样确认'
        assert change(client, confirmed, 'DRAFT').status_code == 403
        assert client.get('/api/carton-mark/assets/supplier-workflow/classification-history?factory_id=huaxing').status_code == 403
