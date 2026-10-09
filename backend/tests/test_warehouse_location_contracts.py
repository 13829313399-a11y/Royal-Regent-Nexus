import importlib
import json
from uuid import uuid4
import pytest
from sqlalchemy import select
from test_molding_sample_api import make_client, login_as
from test_warehouse_operations import payload, post, workspace, BASE


def place(client, domain, code='A01', warehouse='一仓'):
    common = dict(factory_id='huakang-c', request_id=str(uuid4()), expected_revision=0)
    if domain == 'fabric':
        response = client.post('/api/fabric-warehouse/master', json={**common, 'kind': 'LOCATION', 'code': code,
            'name': code, 'status': 'ACTIVE', 'data': {'warehouse': warehouse}})
    else:
        response = client.post(BASE + '/semi/locations', json={**common, 'warehouse': warehouse, 'code': code, 'status': 'ACTIVE'})
    assert response.status_code == 200, response.text
    return response.json()


def set_status(client, domain, location, status):
    common = dict(factory_id='huakang-c', request_id=str(uuid4()), expected_revision=location['revision'], id=location['id'], code=location['code'], status=status)
    body = {**common, 'kind': 'LOCATION', 'name': location['name'], 'data': location['data']} if domain == 'fabric' else {**common, 'warehouse': location['warehouse']}
    response = client.post('/api/fabric-warehouse/master' if domain == 'fabric' else BASE + '/semi/locations', json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('domain', ['fabric', 'semi'])
def test_formal_locations_required_and_bulk_issue_atomicity(monkeypatch, domain):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        extra = {'process_state': '车缝完成'} if domain == 'semi' else {}
        body = payload(client, 'RECEIPT', domain, location_id='', **extra)
        post(client, body, domain, 422)
        a, b = place(client, domain), place(client, domain, 'A02')
        other = place(client, 'semi' if domain == 'fabric' else 'fabric')
        post(client, payload(client, 'RECEIPT', domain, location_id=other['id'], **extra), domain, 422)
        receipt = post(client, payload(client, 'RECEIPT', domain, location_id=a['id'], source_no='DN-original', **extra), domain)
        row = next(r for r in workspace(client, domain)['stock'] if r['id'] == receipt['id'])
        assert row['location_verified'] and row['location_id'] == a['id']
        moved = post(client, payload(client, 'TRANSFER', domain, batch_id=receipt['id'], location_id=b['id'], quantity='3', source_no='MOVE-1', business_date='2026-07-19'), domain)
        state = workspace(client, domain)
        rows = {r['id']: r for r in state['stock']}
        assert rows[receipt['id']]['quantity'] == '7' and rows[moved['id']]['quantity'] == '3'
        assert rows[moved['id']]['source_no'] == 'DN-original' and rows[moved['id']]['source_document'] == receipt['id']
        assert rows[moved['id']]['received_on'] == '2026-07-18'
        assert rows[moved['id']]['inbound_quantity'] == '0' and rows[moved['id']]['transfer_quantity'] == '3'
        set_status(client, domain, a, 'INACTIVE')
        post(client, payload(client, 'RECEIPT', domain, location_id=a['id'], **extra), domain, 422)
        post(client, payload(client, 'TRANSFER', domain, batch_id=moved['id'], location_id=a['id'], quantity='1', business_date='2026-07-19'), domain, 422)
        # Outbound from an inactive but identified location remains possible.
        request = dict(factory_id='huakang-c', request_id=str(uuid4()), expected_revision=workspace(client, domain)['revision'],
            business_date='2026-07-19', counterparty='裁床', items=[{'batch_id': receipt['id'], 'quantity': '2'}, {'batch_id': moved['id'], 'quantity': '4'}])
        before = workspace(client, domain)
        assert client.post(f'{BASE}/{domain}/issues/bulk', json=request).status_code == 409
        assert workspace(client, domain) == before
        request['items'][1]['quantity'] = '1'
        result = client.post(f'{BASE}/{domain}/issues/bulk', json=request)
        assert result.status_code == 200, result.text
        assert client.post(f'{BASE}/{domain}/issues/bulk', json=request).json() == result.json()
        assert sorted(r['quantity'] for r in workspace(client, domain)['stock']) == ['2', '5']
        assert client.post(f'{BASE}/{domain}/documents', json={**result.json()['documents'][0]['data'], 'bulk_hash': 'tamper'}).status_code == 422
        duplicate = {**request, 'request_id': str(uuid4()), 'expected_revision': workspace(client, domain)['revision'], 'items': [request['items'][0], request['items'][0]]}
        assert client.post(f'{BASE}/{domain}/issues/bulk', json=duplicate).status_code == 422


def test_legacy_binding_keeps_quantity_and_original_document(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        db_module = importlib.import_module('app.db')
        operations = importlib.import_module('app.services.warehouse_operations')
        model = importlib.import_module('app.models.warehouse_operations').WarehouseOperation
        schema = importlib.import_module('app.schemas.warehouse_operations').WarehouseDocumentRequest
        user_model = importlib.import_module('app.models.auth').AuthUser
        request = operations.request_body(schema(**payload(client, 'RECEIPT', location_id='', location='旧货架')))
        with db_module.SessionLocal() as db:
            actor = db.scalar(select(user_model).where(user_model.username == 'admin'))
            encoded = operations.dump(request)
            db.add(model(id='legacy-receipt', factory_id='huakang-c', warehouse='fabric', sequence=1, request_id=request['request_id'],
                request_hash=operations.digest(['fabric', actor.id, request]), kind='RECEIPT', business_date=request['business_date'],
                payload_json=encoded, actor_id=actor.id, actor_name=actor.display_name, occurred_at='2026-07-18'))
            db.commit()
        # Exact pre-upgrade retries return the historical receipt, before new validation.
        assert post(client, request)['id'] == 'legacy-receipt'
        location = place(client, 'fabric', 'A01')
        assert workspace(client)['stock'][0]['location_verified'] is False
        post(client, payload(client, 'ISSUE', batch_id='legacy-receipt', quantity='1'), status=422)
        binding = payload(client, 'LOCATION_BIND', batch_id='legacy-receipt', location_id=location['id'], confirmed=True, reason='现场核对旧货架对应一仓 A01')
        post(client, {**binding, 'confirmed': False}, status=422)
        bound = post(client, binding)
        assert post(client, binding) == bound
        row = workspace(client)['stock'][0]
        assert row['quantity'] == '10' and row['location_id'] == location['id'] and row['received_on'] == '2026-07-18'
        post(client, payload(client, 'LOCATION_BIND', batch_id='legacy-receipt', location_id=location['id'], confirmed=True), status=409)
        with db_module.SessionLocal() as db:
            assert db.get(model, 'legacy-receipt').payload_json == encoded
        api = importlib.import_module('app.api.warehouse_operations')
        monkeypatch.setattr(api, 'can', lambda actor, code, factory, department: code.endswith((':read', ':operate')))
        post(client, binding, status=403)
        assert client.post(BASE + '/semi/locations', json=dict(factory_id='huakang-c', request_id=str(uuid4()), expected_revision=0, warehouse='一仓', code='A')).status_code == 403


def test_purchase_receiving_rejects_unknown_location_and_freezes_identity(monkeypatch):
    from test_fabric_procurement import book, row, stored
    from test_fabric_procurement_tracking import save
    from test_fabric_receiving import request, receive
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        save(client, book([row()]))
        source = stored(client)['items'][0]
        body = request(source, batches=[{'quantity': '1', 'location': '任意位置', 'location_id': '', 'dye_lot': 'LOT1'}])
        assert receive(client, source, body).status_code == 422
        loc = place(client, 'fabric')
        body['batches'][0]['location_id'] = loc['id']
        receipt = receive(client, source, body)
        assert receipt.status_code == 200, receipt.text
        record = workspace(client)['stock'][0]
        assert record['location_id'] == loc['id'] and record['location'] == '一仓／A01'
        set_status(client, 'fabric', loc, 'INACTIVE')
        assert receive(client, source, body).json() == receipt.json()
        body['request_id'] = str(uuid4()); body['delivery_reference'] = 'DN-next'; body['expected_receipt_count'] = 1
        assert receive(client, source, body).status_code == 422
