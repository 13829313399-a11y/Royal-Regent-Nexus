"""Location zoning protects new postings without reinterpreting historical stock."""
from uuid import uuid4
from warehouse_location_fixtures import make_client
from test_molding_sample_api import login_as
from test_warehouse_operations import payload, post, workspace, quality


def zone(client, code, category):
    result = client.post('/api/fabric-warehouse/master', json=dict(factory_id='huakang-c',
        request_id=str(uuid4()), kind='LOCATION', code=code, name=code, status='ACTIVE',
        data={'warehouse': '原料仓', 'category': category}))
    assert result.status_code == 200, result.text
    return result.json()


def test_manual_returns_transfers_and_history_use_authoritative_category(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        fabric = zone(client, '布料1架', 'FABRIC')
        thread = zone(client, '配线1区', 'THREAD')
        before = workspace(client)
        post(client, payload(client, 'RECEIPT', location_id=thread['id'], material_category='FABRIC'), status=422)
        assert workspace(client)['stock'] == before['stock']
        request = payload(client, 'RECEIPT', location_id=fabric['id'])
        received = post(client, request)
        # Changing the current catalog must not rewrite stock evidence or block exact retries.
        changed = client.post('/api/fabric-warehouse/master', json=dict(factory_id='huakang-c',
            request_id=str(uuid4()), id=fabric['id'], expected_revision=fabric['revision'], kind='LOCATION',
            code=fabric['code'], name=fabric['name'], status='ACTIVE', data={'warehouse': '原料仓', 'category': 'THREAD'}))
        assert changed.status_code == 200, changed.text
        assert post(client, request)['id'] == received['id']
        assert workspace(client)['stock'][0]['material_category'] == 'FABRIC'
        quality(client, received['id'])
        issue = post(client, payload(client, 'ISSUE', batch_id=received['id'], quantity='2'))
        post(client, payload(client, 'TRANSFER', batch_id=received['id'], quantity='1',
             location_id=thread['id'], material_category='THREAD'), status=422)
        post(client, payload(client, 'RETURN', original_id=issue['id'], quantity='1',
             location_id=thread['id'], material_category='THREAD'), status=422)
        returned = post(client, payload(client, 'RETURN', original_id=issue['id'], quantity='1',
             location_id='fabric-A01', material_category='THREAD'))
        assert returned['data']['material_category'] == 'FABRIC'
        # A confirmed material's category cannot be spoofed on a new manual receipt.
        material = client.post('/api/fabric-warehouse/master', json=dict(factory_id='huakang-c', request_id=str(uuid4()),
            kind='MATERIAL', code='00012', name='白色布', status='ACTIVE', data={'category':'FABRIC','unit':'码'}))
        assert material.status_code == 200, material.text
        post(client, payload(client, 'RECEIPT', location_id=thread['id'], material_category='THREAD', lot=''), status=422)


def test_purchase_splits_and_opening_import_reject_mixed_wrong_zones_atomically(monkeypatch):
    from test_fabric_procurement import book, row, stored, BASE
    from test_fabric_procurement_tracking import save
    from test_fabric_receiving import request, receive
    from test_fabric_inventory_setup import book as opening_book, line, preview, apply
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        fabric = zone(client, '布料1架', 'FABRIC')
        thread = zone(client, '配线1区', 'THREAD')
        save(client, book([row()]))
        source = stored(client)['items'][0]
        detail = client.get(f"{BASE}/lines/{source['id']}", params={'factory_id':'huakang-c'}).json()
        assert next(r for r in detail['available_locations'] if r['id'] == fabric['id'])['category'] == 'FABRIC'
        body = request(source, batches=[{'quantity':'1','location':'布料1架','location_id':fabric['id'],'dye_lot':'A'},
                                        {'quantity':'1','location':'配线1区','location_id':thread['id'],'dye_lot':'B'}])
        failed = receive(client, source, body)
        assert failed.status_code == 422, failed.text
        assert workspace(client)['stock'] == []
        body['batches'][1]['location_id'] = 'fabric-A01'
        received = receive(client, source, body)
        assert received.status_code == 200, received.text
        before = workspace(client)['stock']
        content = opening_book([line(), line(**{'来源行号':'002','仓库':'原料仓','仓位':'配线1区','缸号':'B'})])
        plan = preview(client, content).json()
        assert plan['error_count'] == 1
        assert apply(client, content, plan).status_code == 422
        assert workspace(client)['stock'] == before
