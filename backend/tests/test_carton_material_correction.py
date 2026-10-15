import json
import pytest
from uuid import uuid4
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, accept_all, supplier_login, ship_payload, receive_payload

@pytest.fixture(autouse=True)
def centimeter_fixture(monkeypatch):
    import test_carton_procurement_api as fixtures
    original = fixtures._order_payload
    def payload():
        value = original()
        value['lines'][0]['dimension_unit'] = 'cm'
        return value
    monkeypatch.setattr(fixtures, '_order_payload', payload)

BASE = '/api/carton-procurement'
SUP = '/api/carton-supplier'

def context(client, order):
    r = client.get(f"{BASE}/orders/{order['order_no']}/material-corrections?factory_id=huaxing")
    assert r.status_code == 200, r.text
    return r.json()

def propose(client, order, reason='原尺寸实际为英寸，单位录错'):
    data = context(client, order)
    line = data['lines'][0]
    payload = dict(factory_id='huaxing', request_id=str(uuid4()), expected_revision=data['revision'],
        issue_id=data['issue_id'], order_line_id=line['id'],
        after={k: line[k] for k in ('packaging_type','paper_quality','specification','dimension_unit')})
    if reason is not None:
        payload['reason'] = reason
    payload['after']['dimension_unit'] = 'inch'
    r = client.post(f"{BASE}/orders/{order['order_no']}/material-corrections", json=payload)
    assert r.status_code == 201, r.text
    return r.json(), payload

def decide(client, row, action='APPROVE', **kwargs):
    data = dict(factory_id='huaxing', request_id=str(uuid4()), expected_revision=row['revision'],
        action=action, note='双方已核实资料与实物', verified=True) | kwargs
    return client.post(f"{SUP}/material-corrections/{row['id']}/actions", json=data), data


@pytest.mark.parametrize('reason', [None, '', '   ', '填错'])
def test_optional_reason_and_action_notes_preserve_explicit_verification(monkeypatch, reason):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        login_as(client, 'admin'); row, _ = propose(client, order, reason=reason)
        assert row['reason'] == ((reason or '').strip() or '填错了')
        supplier_login(client)
        url = f"{SUP}/material-corrections/{row['id']}/actions"
        payload = dict(factory_id='huaxing', request_id=str(uuid4()), expected_revision=row['revision'], action='APPROVE')
        assert client.post(url, json=payload).status_code == 422
        response = client.post(url, json=payload | {'verified': True})
        assert response.status_code == 200, response.text
        assert response.json()['response_note'] == ''
        assert response.json()['status'] == 'APPROVED'

def test_bilateral_correction_holds_one_line_issues_zero_delta_and_replays(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client); order = accept_all(client)
        before_issue = order['issue_id']; pending_ship = ship_payload(order)
        from io import BytesIO
        from openpyxl import Workbook
        workbook = Workbook(); sheet = workbook.active
        sheet.append(['送货单号','日期','客户','客户单号','客户料号','名称','纸质','规格','数量','单价'])
        paper = order['lines'][0]
        sheet.append(['CORRECTED-IMPORT','2026-09-21','华兴',order['contract_no'],order['item_no'],
            paper['packaging_type'],paper['paper_quality'],paper['specification']+'inch',1,2])
        stream=BytesIO();workbook.save(stream);file=('尺寸更正送货.xlsx',stream.getvalue())
        preview=client.post(SUP+'/shipments/import-preview',files={'file':file})
        assert preview.status_code==200,preview.text
        assert preview.json()['groups'][0]['rows'][0]['status']=='BLOCKED'
        assert '尺寸单位' in preview.json()['groups'][0]['rows'][0]['reason']
        login_as(client,'admin'); row, payload = propose(client,order)
        same = client.post(f"{BASE}/orders/{order['order_no']}/material-corrections",json=payload)
        assert same.status_code == 201 and same.json()['id'] == row['id']
        assert context(client,order)['lines'][0]['dimension_unit'] == row['before']['dimension_unit']
        # The replay key cannot be reused for different content; stale clients
        # also cannot create a second pending request.
        url = f"{BASE}/orders/{order['order_no']}/material-corrections"
        assert client.post(url,json=payload|{'reason':'修改了原请求内容'}).status_code == 409
        assert client.post(url,json=payload|{'request_id':str(uuid4())}).status_code == 409
        assert client.post(url,json=payload|{'after':payload['after']|{'required_quantity':999}}).status_code == 422
        supplier_login(client)
        assert client.get(f"{BASE}/orders/{order['order_no']}/material-corrections?factory_id=huaxing").status_code == 403
        assert client.post(SUP+'/shipments',json=pending_ship).status_code == 409
        visible = client.get(SUP+'/workspace?factory_id=huaxing').json()['orders'][0]
        assert visible['lines'][0]['shipping_blocked_reason']
        assert not visible['lines'][1]['shipping_blocked_reason']
        other = ship_payload(order); other['lines'] = other['lines'][1:]; other['delivery_note_no'] = 'UNAFFECTED'
        assert client.post(SUP+'/shipments',json=other).status_code == 201
        unverified,_ = decide(client,row,verified=False)
        assert unverified.status_code == 422
        approved, action = decide(client,row)
        assert approved.status_code == 200, approved.text
        assert approved.json()['status'] == 'APPROVED'
        assert client.post(f"{SUP}/material-corrections/{row['id']}/actions",json=action).status_code == 200
        after = client.get(SUP+'/workspace?factory_id=huaxing').json()['orders'][0]
        assert after['issue_id'] != before_issue
        assert after['lines'][0]['dimension_unit'] == 'inch'
        assert all(line['accepted'] for line in after['lines'])
        preview=client.post(SUP+'/shipments/import-preview',files={'file':file})
        assert preview.status_code==200,preview.text
        assert preview.json()['groups'][0]['rows'][0]['status']=='READY',preview.text
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonPurchaseOrderIssue, CartonInventoryMovement
        from sqlalchemy import select
        with SessionLocal() as db:
            old = json.loads(db.get(CartonPurchaseOrderIssue,before_issue).snapshot_json)
            new = json.loads(db.get(CartonPurchaseOrderIssue,after['issue_id']).snapshot_json)
            assert old['lines'][0]['dimension_unit'] != 'inch'
            assert all(float(line['required_quantity_delta']) == 0 for line in new['lines'])
            assert not list(db.scalars(select(CartonInventoryMovement)))

def test_return_keeps_hold_withdraw_is_internal_and_factory_scoped(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client);order=accept_all(client)
        login_as(client,'admin');row,_=propose(client,order)
        supplier_login(client)
        assert decide(client,row,factory_id='huakang-b')[0].status_code == 403
        assert decide(client,row,action='WITHDRAW')[0].status_code == 403
        returned,_=decide(client,row,action='RETURN',note='',verified=False);assert returned.status_code == 200,returned.text
        assert client.post(SUP+'/shipments',json=ship_payload(order)).status_code == 409
        login_as(client,'admin')
        data=dict(factory_id='huaxing', request_id=str(uuid4()), expected_revision=returned.json()['revision'],action='WITHDRAW',verified=True)
        url=f"{BASE}/material-corrections/{row['id']}/actions"
        assert client.post(url,json=data|{'action':'APPROVE'}).status_code == 403
        response=client.post(url,json=data);assert response.status_code == 200,response.text
        supplier_login(client)
        assert client.post(SUP+'/shipments',json=ship_payload(order)).status_code == 201

def test_in_transit_receipt_waits_for_confirmation_and_refresh(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client);order=accept_all(client)
        shipped=client.post(SUP+'/shipments',json=ship_payload(order)).json()
        login_as(client,'admin');receipt=receive_payload(client,shipped);row,_=propose(client,order)
        url=f"{SUP}/internal/shipments/{shipped['id']}/receive"
        assert client.post(url,json=receipt).status_code == 409
        supplier_login(client);approved,_=decide(client,row);assert approved.status_code == 200,approved.text
        login_as(client,'admin')
        assert client.post(url,json=receipt).status_code == 409
        fresh=next(s for s in client.get(SUP+'/internal/workspace?factory_id=huaxing').json()['shipments'] if s['id']==shipped['id'])
        receipt=receive_payload(client,fresh)
        received=client.post(url,json=receipt);assert received.status_code == 200,received.text
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceiptLine
        from sqlalchemy import select
        with SessionLocal() as db:
            line=db.scalar(select(CartonReceiptLine).where(CartonReceiptLine.order_line_id==row['order_line_id']))
            assert line.specification.endswith('inch')

def test_manual_receipt_requires_refreshed_material_and_keeps_posted_history(monkeypatch):
    with make_client(monkeypatch) as client:
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceiptLine, CartonInventoryMovement
        from sqlalchemy import select
        setup_portal(client); order = accept_all(client)
        shipped = client.post(SUP+'/shipments',json=ship_payload(order)).json()
        login_as(client,'admin')
        received = client.post(f"{SUP}/internal/shipments/{shipped['id']}/receive",json=receive_payload(client,shipped))
        assert received.status_code == 200,received.text
        with SessionLocal() as db:
            original = db.scalar(select(CartonReceiptLine).where(CartonReceiptLine.order_line_id==order['lines'][0]['id']))
            original_id, original_spec, original_qty = original.id, original.specification, original.received_quantity
            stock_before = [(m.id,m.specification,m.quantity) for m in db.scalars(select(CartonInventoryMovement))]
        row,_=propose(client,order)
        manual = dict(factory_id='huaxing',request_id=str(uuid4()),delivery_note_no='MANUAL-CORRECTED',delivery_date='2026-09-21',acceptance_date='2026-09-21',lines=[dict(order_line_id=row['order_line_id'],delivered_quantity=1,received_quantity=1,unit_price=2,location='A-01')])
        assert client.post(BASE+'/receipts',json=manual).status_code == 409
        supplier_login(client);approved,_=decide(client,row);assert approved.status_code == 200,approved.text
        login_as(client,'admin')
        stale=client.post(BASE+'/receipts',json=manual)
        assert stale.status_code == 409 and '刷新' in stale.text
        fresh = client.get(BASE+'/orders?factory_id=huaxing').json()['items'][0]
        assert fresh['lines'][0]['material_correction_id'] == row['id']
        assert fresh['material_corrections'][0]['status'] == 'APPROVED'
        with SessionLocal() as db:
            original=db.get(CartonReceiptLine,original_id)
            assert (original.specification,original.received_quantity)==(original_spec,original_qty)
            assert [(m.id,m.specification,m.quantity) for m in db.scalars(select(CartonInventoryMovement))]==stock_before
        manual['lines'][0]['material_correction_id']=row['id']
        created=client.post(BASE+'/receipts',json=manual);assert created.status_code==201,created.text
        assert created.json()['lines'][0]['specification'].endswith('inch')
        # An unfinished receipt cannot be silently reinterpreted by another correction.
        current=context(client,order)
        proposal=dict(factory_id='huaxing',request_id=str(uuid4()),expected_revision=current['revision'],issue_id=current['issue_id'],order_line_id=row['order_line_id'],after=row['before'],reason='再次核对发现规格需调整')
        blocked=client.post(f"{BASE}/orders/{order['order_no']}/material-corrections",json=proposal)
        assert blocked.status_code==409 and '草稿' in blocked.text


def test_supplier_approval_permission_and_self_approval_are_enforced(monkeypatch):
    from test_carton_supplier_portal import revoke_supplier_permission, grant_supplier_permissions
    with make_client(monkeypatch) as client:
        setup_portal(client);order=accept_all(client)
        login_as(client,'admin');row,_=propose(client,order)
        supplier_login(client);revoke_supplier_permission('carton_supplier:approve')
        assert decide(client,row)[0].status_code==403
        admin=login_as(client,'admin');grant_supplier_permissions(admin['id'])
        # Even an internal administrator with supplier privileges cannot attest for both sides.
        login_as(client,'admin')
        result,_=decide(client,row)
        assert result.status_code==403 and '发起人' in result.text
