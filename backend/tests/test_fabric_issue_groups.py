"""Kit allocation acceptance on isolated SQLite; never write real warehouse data."""
from decimal import Decimal
from uuid import uuid4
import importlib
import pytest
from warehouse_location_fixtures import make_client
from test_molding_sample_api import login_as
from test_warehouse_operations import payload, post, workspace, quality

URL = '/api/warehouse-operations/fabric/issue-groups'


def save_group(client, requests, status=200, **changes):
    body = dict(factory_id='huakang-c', request_id=str(uuid4()), expected_revision=workspace(client)['revision'],
                order_no='O-001', name='衣身及捆条', request_ids=[r['id'] for r in requests]) | changes
    response = client.post(URL, json=body)
    assert response.status_code == status, response.text
    return response.json(), body


def preview(client, group, status=200):
    response = client.post(URL+'/preview', json=dict(factory_id='huakang-c', group_id=group['group_id'], business_date='2026-07-18'))
    assert response.status_code == status, response.text
    return response.json()


def issue_body(plan, **changes):
    return dict(factory_id='huakang-c', request_id=str(uuid4()), group_id=plan['group']['group_id'],
                expected_revision=plan['revision'], token=plan['token'], business_date='2026-07-18',
                confirmed=True, items=plan['items']) | changes


def create_request(client, quantity='6', **changes):
    return post(client, payload(client, 'REQUEST', production_no='O-001', quantity=quantity, **changes))


def stock(client, lot, amount, day='2026-07-16', **changes):
    return post(client, payload(client, 'RECEIPT', lot=lot, quantity=amount, business_date=day, **changes))


def test_same_lot_fifo_proportional_fallback_atomic_issue_replay_and_reversal(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        old = stock(client, 'L1', '2', '2026-07-14')
        newer = stock(client, 'L1', '6', '2026-07-15')
        other = stock(client, 'L2', '3', '2026-07-13')
        requests = [create_request(client, '6', purpose='衣身'), create_request(client, '4', counterparty='捆条组', purpose='捆条')]
        group, command = save_group(client, requests)
        assert client.post(URL, json=command).json() == group
        plan = preview(client, group)
        assert plan['items'] == [
            dict(original_id=requests[0]['id'], batch_id=old['id'], quantity='2'),
            dict(original_id=requests[0]['id'], batch_id=newer['id'], quantity='2.8'),
            dict(original_id=requests[1]['id'], batch_id=newer['id'], quantity='3.2'),
            dict(original_id=requests[0]['id'], batch_id=other['id'], quantity='1.2'),
            dict(original_id=requests[1]['id'], batch_id=other['id'], quantity='0.8')]
        body = issue_body(plan)
        response = client.post(URL+'/issue', json=body)
        assert response.status_code == 200, response.text
        issued = response.json()['documents']
        assert client.post(URL+'/issue', json=body).json() == response.json()
        assert client.post(URL+'/issue', json=body | {'reason': 'changed'}).status_code == 409
        view = workspace(client)
        assert {r['id']: Decimal(r['issued_quantity']) for r in view['documents'] if r['kind']=='REQUEST'} == {r['id']: Decimal(r['data']['quantity']) for r in requests}
        assert all(r['data']['issue_group']['request_ids'] == group['request_ids'] for r in issued)
        assert next(r for r in view['stock'] if r['id']==other['id'])['quantity'] == '1.0'
        post(client, payload(client, 'CORRECTION', original_id=issued[-1]['id']))
        followup = preview(client, group)
        assert followup['demands'][0]['remaining'] == '0.8'
        assert client.post(URL+'/issue', json=body).json() == response.json()
        # Stored child UUIDs cannot be replayed separately through ordinary posting.
        assert client.post('/api/warehouse-operations/fabric/documents', json={k:v for k,v in issued[0]['data'].items()
            if k not in {'bulk_hash','bulk_request_id','issue_group','issue_plan_token'}}).status_code == 409


def test_complete_lot_preferred_then_existing_lot_and_transfer_keeps_age(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        stock(client, 'OLD-SMALL', '3', '2026-07-12')
        full = stock(client, 'FULL', '10', '2026-07-13')
        moved = post(client, payload(client, 'TRANSFER', batch_id=full['id'], quantity='4', location='A02'))
        requests = [create_request(client, '3'), create_request(client, '3')]
        group, _ = save_group(client, requests)
        plan = preview(client, group)
        assert {r['batch_id'] for r in plan['items']} <= {full['id'], moved['id']}
        assert next(b for b in plan['candidates'] if b['id']==moved['id'])['received_on']=='2026-07-13'
        post(client, payload(client, 'ISSUE', batch_id=full['id'], original_id=requests[0]['id'], quantity='1'))
        stock(client, 'NEW-FULL', '100')
        plan = preview(client, group)
        assert {r['batch_id'] for r in plan['items']} <= {full['id'], moved['id']}


def test_shortage_units_restrictions_dates_and_manual_adjustment(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        usable = stock(client, 'A', '1.000001')
        held = stock(client, 'H', '30')
        quality(client, held['id'], state='HOLD')
        stock(client, 'WRONG-UNIT', '20', unit='米')
        stock(client, 'FUTURE', '20', day='2026-07-19')
        stock(client, 'WRONG-CATEGORY', '20', material_category='ACCESSORY', location='辅料位')
        requests = [create_request(client, '1'), create_request(client, '1')]
        group, _ = save_group(client, requests)
        plan = preview(client, group)
        assert [r['quantity'] for r in plan['items']] == ['0.500001','0.5']
        assert [d['shortage'] for d in plan['demands']] == ['0.499999','0.5']
        assert [b['id'] for b in plan['candidates']] == [usable['id']]
        # Warehouse can deliberately change the split, while retaining exact total limits.
        adjusted = [dict(original_id=r['id'],batch_id=usable['id'],quantity=q) for r,q in zip(requests,['0.7','0.3'])]
        response = client.post(URL+'/issue', json=issue_body(plan, items=adjusted))
        assert response.status_code==200,response.text
        assert next(b for b in workspace(client)['stock'] if b['id']==usable['id'])['quantity']=='0.000001'


def test_stale_plan_over_issue_and_mid_transaction_failure_never_partially_post(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        batch=stock(client,'A','10')
        requests=[create_request(client,'3'),create_request(client,'3')]
        group,_=save_group(client,requests)
        plan=preview(client,group)
        before=workspace(client)
        items=[dict(original_id=r['id'],batch_id=batch['id'],quantity=q) for r,q in zip(requests,['3','4'])]
        response=client.post(URL+'/issue',json=issue_body(plan,items=items))
        assert response.status_code==409,response.text
        assert workspace(client)==before
        stock(client,'B','20')
        assert client.post(URL+'/issue',json=issue_body(plan)).status_code==409
        fresh=preview(client,group)
        assert client.post(URL+'/issue',json=issue_body(fresh,confirmed=False)).status_code==422
        duplicate=fresh['items']+[fresh['items'][0]]
        assert client.post(URL+'/issue',json=issue_body(fresh,items=duplicate)).status_code==422


def test_explicit_group_membership_extension_order_and_permissions(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,'admin')
        a,b,c=[create_request(client) for _ in range(3)]
        group,body=save_group(client,[a,b])
        save_group(client,[a,c],status=409)
        save_group(client,[a,b],status=422,order_no='OTHER',group_id=group['group_id'])
        save_group(client,[a,a],status=422)
        extended,_=save_group(client,[a,b,c],group_id=group['group_id'])
        assert len(extended['request_ids'])==3
        save_group(client,[a,b],status=422,group_id=group['group_id'])
        assert len(workspace(client)['issue_groups'])==1
        assert all(r['kind']!='FABRIC_ISSUE_GROUP' for r in workspace(client)['documents'])
        assert client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id':'huakang-c','month':'2026-07'}).status_code==200
        assert client.get('/api/warehouse-operations/fabric/order-summary', params={'factory_id':'huakang-c'}).status_code==200
        assert client.get('/api/warehouse-operations/fabric/inventory-setup', params={'factory_id':'huakang-c'}).status_code==200
        api=importlib.import_module('app.api.warehouse_operations')
        monkeypatch.setattr(api,'can',lambda actor,permission,*args: permission.endswith(':read'))
        assert client.post(URL,json=body).status_code==403
        assert client.post(URL+'/preview',json=dict(factory_id='huakang-c',group_id=group['group_id'],business_date='2026-07-18')).status_code==403
        assert client.post(URL,json=body|{'factory_id':'huakang-a'}).status_code==422


def test_proportional_allocation_conserves_six_decimal_quantities():
    service=importlib.import_module('app.services.fabric_issue_groups')
    for needs in ([Decimal('0.000001')]*3,[Decimal('999999999999.999999'),Decimal('0.000001')],
                  [Decimal('6'),Decimal('4')]):
        for total in (Decimal('0.000001'), sum(needs), sum(needs)/2 if sum(needs)>=1 else Decimal('0.000002')):
            shares=service.proportional(total,needs)
            assert sum(shares)==total
            assert all(0<=a<=b for a,b in zip(shares,needs))


def test_uncertain_commands_can_be_fenced_or_confirmed_and_scope_stays_private(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,'admin')
        stock(client,'A','20')
        requests=[create_request(client),create_request(client)]
        group,creation=save_group(client,requests)
        assert client.post(URL+'/recover',json={'kind':'group','body':creation}).json()=={'state':'committed'}
        plan=preview(client,group)
        body=issue_body(plan)
        assert client.post(URL+'/recover',json={'kind':'issue','body':body}).json()=={'state':'abandoned'}
        assert client.post(URL+'/issue',json=body).status_code==409
        plan=preview(client,group); body=issue_body(plan)
        assert client.post(URL+'/issue',json=body).status_code==200
        assert client.post(URL+'/recover',json={'kind':'issue','body':body}).json()=={'state':'committed'}
        assert client.post(URL+'/recover',json={'kind':'issue','body':body|{'reason':'spoof'}}).status_code==409


def test_master_change_invalidates_preview_even_without_operation_revision(monkeypatch):
    import json
    with make_client(monkeypatch) as client:
        login_as(client,'admin')
        stock(client,'A','20')
        requests=[create_request(client),create_request(client)]
        group,_=save_group(client,requests); plan=preview(client,group)
        db_module=importlib.import_module('app.db')
        model=importlib.import_module('app.models.fabric_master').FabricMasterRecord
        with db_module.SessionLocal() as db:
            db.add(model(id='test-inactive-material',factory_id='huakang-c',kind='MATERIAL',code='00012',name='白色布',
                status='INACTIVE',revision=1,data_json=json.dumps({'unit':'码','category':'FABRIC'}),updated_at='2026-07-18'))
            db.commit()
        response=client.post(URL+'/issue',json=issue_body(plan))
        assert response.status_code==409,response.text
        assert all(d['shortage']=='6' for d in preview(client,group)['demands'])


def test_equal_lot_labels_from_different_suppliers_are_not_one_dye_lot():
    service=importlib.import_module('app.services.fabric_issue_groups')
    a=dict(id='a',lot='001',counterparty='supplier-A')
    b=dict(id='b',lot='001',counterparty='supplier-B')
    assert service.lot_identity(a)!=service.lot_identity(b)
    assert service.lot_identity(a)==service.lot_identity(a|{'id':'a-transfer'})
    assert service.lot_identity(a|{'lot':''})!=service.lot_identity(a|{'id':'a-transfer','lot':''})
