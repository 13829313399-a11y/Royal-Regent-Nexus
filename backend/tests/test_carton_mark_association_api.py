"""Owner regressions: file evidence stays outside the purchase approval state."""
import json
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login
from test_carton_mark_asset_images import photo_bytes
from test_carton_special_requests import ok, command, create_body, BASE as SPECIAL, SUP as SPECIAL_SUP

BASE = '/api/carton-mark/assets'
SUP = '/api/carton-supplier/carton-mark'
SCOPE = {'factory_id': 'huaxing'}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)


def target(row):
    return {key: row[key] for key in ('order_kind', 'order_id', 'issue_id')} | {'expected_revision': row['revision']}


def test_supplier_upload_and_direct_special_order_association_retries_without_duplicate_or_state_change(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin')
        row = ok(client.post(SPECIAL, json=create_body()), 201)
        row = ok(client.post(SPECIAL + f"/{row['id']}/send", json=command(row)))
        supplier_login(client)
        selected = next(x for x in ok(client.get(SUP + '/binding-targets', params=SCOPE)) if x['order_id'] == row['id'])
        body = {**SCOPE, 'request_id': 'supplier-upload-simple1', 'targets_json': json.dumps([target(selected)])}
        def upload():
            return ok(client.post(SUP + '/assets/upload', data=body,
                files=[('files', ('camera.png', photo_bytes(), 'image/png'))]), 201)
        first, repeated = upload(), upload()
        assert first[0]['asset']['id'] == repeated[0]['asset']['id']
        asset = first[0]['asset']
        assert asset['associations'][0]['order_id'] == row['id']
        assert asset['associations'][0]['line_id'] == ''
        assert asset['workflow']['status'] == 'PENDING' and not asset['pending_bindings']
        current = ok(client.get(SPECIAL_SUP + f"/{row['id']}", params=SCOPE))
        assert (current['revision'], current['current_version_id'], current['quote_version_id'], current['promised_date']) == (
            row['revision'], row['current_version_id'], row['quote_version_id'], row['promised_date'])
        assert current['mark_assets'][0]['id'] == asset['id']
        clear = {'revision': asset['revision'], 'request_id': 'supplier-clear-simple1', 'targets': []}
        cleared = ok(client.put(SUP + f"/assets/{asset['id']}/associations", params=SCOPE, json=clear))
        assert not cleared['associations'] and not cleared['special_orders']
        assert ok(client.put(SUP + f"/assets/{asset['id']}/associations", params=SCOPE, json=clear))['id'] == asset['id']
        assert len(ok(client.get(SUP + '/assets', params=SCOPE))) == 1
        body['targets_json'] = '[]'
        assert client.post(SUP + '/assets/upload', data=body,
            files=[('files', ('camera.png', photo_bytes(), 'image/png'))]).status_code == 409


def test_internal_upload_association_is_atomic_idempotent_and_validates_target_version(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin')
        selected = next(x for x in ok(client.get(BASE + '/binding-targets', params=SCOPE)) if x['order_id'] == order['id'])
        option = {'request_id': 'internal-upload-simple1', 'targets': [target(selected)], 'sharing_mode': 'SUPPLIER'}
        def upload(options):
            return ok(client.post(BASE + '/batch', data={**SCOPE, 'options_json': json.dumps([options])},
                files=[('files', ('camera.png', photo_bytes(), 'image/png'))]))[0]
        first, again = upload(option), upload(option)
        assert first['asset']['id'] == again['asset']['id'] and again['status'] == 'duplicate'
        asset = first['asset']
        bad = {**option, 'request_id': 'internal-upload-stale1', 'targets': [{**target(selected), 'expected_revision': 999}]}
        assert upload(bad)['status'] == 'failed'
        assert len(ok(client.get(BASE, params=SCOPE))) == 1
        response = client.put(BASE + f"/{asset['id']}/associations", params=SCOPE,
            json={'revision': asset['revision'], 'request_id': 'internal-stale-simple1', 'targets': bad['targets']})
        assert response.status_code == 409


def test_new_special_attachments_never_replace_historical_confirmed_material_or_execution_version(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin')
        row = ok(client.post(SPECIAL, json=create_body()), 201)
        row = ok(client.post(SPECIAL + f"/{row['id']}/send", json=command(row)))
        uploaded = ok(client.post(SPECIAL + f"/{row['id']}/attachments", data={**command(row), 'role': 'CONFIRMED'},
            files={'file': ('photo.png', photo_bytes(), 'image/png')}), 201)
        assert uploaded['current_version_id'] == row['current_version_id'] and uploaded['revision'] == row['revision']
        assert uploaded['attachments'][-1]['role'] == 'DRAFT'
        assert uploaded['lines'][0]['mark_attachment_id'] == row['lines'][0]['mark_attachment_id']
        assert ok(client.get(BASE, params=SCOPE))[0]['workflow']['status'] == 'PENDING'


def test_revision_inherits_special_evidence_without_changing_regular_contract_matching(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin')
        body = create_body(); body['customer_code'] = order['customer_code']
        special = ok(client.post(SPECIAL, json=body), 201)
        special = ok(client.post(SPECIAL + f"/{special['id']}/send", json=command(special)))
        def upload(name, options):
            return ok(client.post(BASE + '/batch', data={**SCOPE, 'options_json': json.dumps([options])},
                files=[('files', (name, photo_bytes(), 'image/png'))]))[0]['asset']
        first = upload(order['contract_no'] + '.png', {'sharing_mode': 'SUPPLIER'})
        ok(client.post(SPECIAL + f"/{special['id']}/lines/{special['lines'][0]['id']}/mark",
            json=command(special, mark_mode='EXISTING', asset_id=first['id'], asset_revision=first['revision'])))
        first = next(x for x in ok(client.get(BASE, params=SCOPE)) if x['id'] == first['id'])
        second = upload('revised.png', {'status': 'PENDING', 'previous_asset_id': first['id'], 'previous_revision': first['revision']})
        assert second['recognition_source'] == first['recognition_source']
        assert second['contract_number'] == first['contract_number']
        assert second['orders'] == first['orders']
        assert second['special_orders'][0]['order_id'] == special['id']
        assert not second['special_orders'][0]['confirmed'] and second['workflow']['status'] == 'PENDING'
        ready = ok(client.put(BASE + f"/{second['id']}/classification", params=SCOPE,
            json={'revision': second['revision'], 'status': 'READY', 'note': '经办人独立分类核实'}))
        assert ready['workflow']['status'] == 'READY'
        current = ok(client.get(SPECIAL + f"/{special['id']}", params=SCOPE))
        assert (current['revision'], current['current_version_id']) == (special['revision'], special['current_version_id'])
