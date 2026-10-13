"""P1c integration in isolated files: ledger -> receipt -> engineering -> procurement."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, inspect
from sqlalchemy.orm import Session
from app.models.customer_order_ledger import OrderLedgerLine as Line, OrderLedgerDispatch as Dispatch
from app.models.cutting_ops import CuttingOrder, CuttingOrderRevision
from app.services import cutting_orders as orders, customer_order_ledger as ledger
from app.schemas.customer_order_ledger import DispatchIn, AmendIn, ReasonIn
from app.services.auth import AuthOverrideContext
from test_cutting_ops import client, user, command, create, bom_body, state, BASE


@pytest.fixture
def flow(client):
    tables = [t for t in Line.metadata.sorted_tables if t.name.startswith('order_ledger_')]
    Line.metadata.create_all(client.engine, tables=tables + list(orders.TABLES))
    client.cutting_auth['user'] = user('read', 'master_write', 'bom_write', 'bom_publish', 'order_receive', 'requisition_submit', 'eta_write')
    with Session(client.engine) as db:
        line = Line(id='line-1', factory_id='huakang-c', customer_code='sample', customer_name='合成洋行',
            identity_key='sample', reference_no='000123', product_no='00012', quantity=Decimal('100'),
            shipped_quantity=0, status='active', version=1, revision=1,
            data={'quantity': '100', 'requested_ship_date': '2026-10-30', 'unit_price_hkd': '888', 'secret': 'not-public'},
            created_at='2026-10-09', updated_at='2026-10-09')
        db.add(line); db.commit()
        ledger.dispatch(db, line, DispatchIn(expected_revision=1, recipients=['cutting', 'pmc']), 'sales')
        db.commit()
    yield client


def read(client):
    response = client.get(BASE + '/orders?factory_id=huakang-c')
    assert response.status_code == 200, response.text
    return response.json()['data'][0]


def post(client, action, **kwargs):
    return client.post(BASE + '/orders/line-1/' + action, json=command(**kwargs))


def receive(client):
    row = read(client)
    response = post(client, 'receive', dispatch_id=row['dispatch_id'], expected_version=row['current']['version'] if row['current'] else 0)
    assert response.status_code == 200, response.text
    return response.json()


def bound(client):
    row = receive(client)
    material = create(client)
    body = bom_body(material)
    body['data']['requirements'].append(dict(body['data']['requirements'][0], stage='后续', required_for_cutting=False))
    bom = state(client, create(client, body), 'published').json()
    response = post(client, 'bom', expected_version=row['current']['version'], bom_id=bom['id'], bom_version=bom['version'],
                    target_sets=50, quantity_basis='订单100件，每套2件，工程核定50套')
    assert response.status_code == 200, response.text
    return response.json(), bom


def submitted(client):
    row, bom = bound(client)
    response = post(client, 'requisition', expected_version=row['current']['version'], lines=[dict(row=0, quantity='7'), dict(row=1, quantity='8')])
    assert response.status_code == 200, response.text
    return response.json(), bom


def batch(row=0, quantity='3.5'):
    return dict(row=row, quantity=quantity, expected_date='2026-10-16', supplier='合成供应商', purchase_reference='PO-001')


def amend(client, cancelled=False):
    with Session(client.engine) as db:
        line = db.get(Line, 'line-1')
        if cancelled:
            ledger.cancel(db, line, ReasonIn(expected_revision=line.revision, reason='测试订单取消'), 'sales')
        else:
            ledger.amend(db, line, AmendIn(expected_revision=line.revision, quantity='120', requested_ship_date='2026-11-01', reason='测试数量变更'), 'sales')
        db.commit()


def test_complete_chain_pins_bom_and_never_posts_stock(flow):
    initial = read(flow)
    assert initial['needs_receipt'] and 'unit_price_hkd' not in initial['snapshot'] and 'secret' not in initial['snapshot']
    row, bom = submitted(flow)
    req = row['current']['data']['requisition']
    assert req['lines'][0]['theoretical_quantity'] == '6.250000'
    assert req['lines'][0]['quantity'] == '7'
    assert req['lines'][1]['required_for_cutting'] is False
    response = post(flow, 'eta', expected_version=row['current']['version'], requisition_version=req['version'], batches=[batch(), batch(quantity='2')])
    assert response.status_code == 200, response.text
    data = response.json()['current']['data']
    assert len(data['batches']) == 2 and data['bom']['version'] == bom['version']
    assert data['requisition']['lines'][0]['replied_quantity'] == '5.5'
    assert data['requisition']['lines'][0]['awaiting_reply_quantity'] == '1.5'
    assert data['requisition']['lines'][1]['awaiting_reply_quantity'] == '8'
    assert not any('stock' in name or 'inventory' in name for name in inspect(flow.engine).get_table_names())
    history = flow.get(BASE + '/orders/line-1/versions?factory_id=huakang-c').json()['data']
    assert len(history) == 4 and history[-1]['data']['bom'] is None


def test_receive_is_idempotent_and_current_auth_still_required(flow):
    row = read(flow)
    body = command(dispatch_id=row['dispatch_id'])
    url = BASE + '/orders/line-1/receive'
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: flow.post(url, json=body), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert post(flow, 'receive', dispatch_id=row['dispatch_id']).json()['current']['version'] == 1
    assert flow.post(url, json=dict(body, reason='改变同一操作')).status_code == 409
    flow.cutting_auth['user'] = user('read')
    assert flow.post(url, json=body).status_code == 403


@pytest.mark.parametrize('action,department', [('receive', 'engineering'), ('bom', 'production'), ('requisition', 'pmc-warehouse'), ('eta', 'engineering')])
def test_actions_require_responsible_department(flow, action, department):
    row, bom = submitted(flow)
    payloads = dict(receive=dict(dispatch_id=row['dispatch_id']), bom=dict(bom_id=bom['id'], bom_version=2, target_sets=50, quantity_basis='套数核定'),
        requisition=dict(lines=[dict(row=0, quantity='1')]), eta=dict(requisition_version=3, batches=[]))
    flow.cutting_auth['user'] = user('read', 'order_receive', 'bom_write', 'requisition_submit', 'eta_write', department=department)
    assert post(flow, action, expected_version=row['current']['version'], **payloads[action]).status_code == 403


def test_engineering_submits_and_pmc_replies_with_explicit_deny(flow):
    row, _ = bound(flow)
    flow.cutting_auth['user'] = user('read', 'requisition_submit', department='engineering')
    response = post(flow, 'requisition', expected_version=2, lines=[dict(row=0, quantity='7'), dict(row=1, quantity='8')])
    assert response.status_code == 200
    account = user('read', 'eta_write', department='pmc-warehouse')
    flow.cutting_auth['user'] = replace(account, overrides=(AuthOverrideContext(id='deny', permission_code='cutting_ops:eta_write', effect='deny', factory_id='huakang-c', department='pmc-warehouse'),))
    assert post(flow, 'eta', expected_version=3, requisition_version=3, batches=[batch()]).status_code == 403
    flow.cutting_auth['user'] = account
    assert post(flow, 'eta', expected_version=3, requisition_version=3, batches=[batch()]).status_code == 200


@pytest.mark.parametrize('batches', [[batch(quantity='8')], [batch(), batch(quantity='4')], [batch(row=2)], [batch(quantity='0')], [dict(batch(), expected_date='wrong')]])
def test_eta_rejects_bad_rows_quantities_dates_and_overcoverage(flow, batches):
    submitted(flow)
    assert post(flow, 'eta', expected_version=3, requisition_version=3, batches=batches).status_code == 422
    assert read(flow)['current']['version'] == 3


def test_eta_versions_and_concurrent_writes(flow):
    submitted(flow)
    assert post(flow, 'eta', expected_version=3, requisition_version=2, batches=[]).status_code == 409
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(flow, 'eta', expected_version=3, requisition_version=3, batches=[batch()]), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]


def test_source_change_invalidates_chain_and_retains_old_purchase_evidence(flow):
    row, _ = submitted(flow)
    old_dispatch = row['dispatch_id']
    amend(flow)
    assert post(flow, 'eta', expected_version=3, requisition_version=3, batches=[]).status_code == 409
    assert post(flow, 'receive', expected_version=3, dispatch_id=old_dispatch).status_code == 409
    row = receive(flow)
    assert row['current']['data']['purchase_reconciliation_required'] is True
    assert row['current']['data']['requisition'] is None
    historical = flow.get(BASE + '/orders/line-1/versions?factory_id=huakang-c').json()['data']
    assert historical[1]['data']['requisition']['lines'][0]['quantity'] == '7'
    assert historical[1]['data']['order']['quantity'] == '100'
    assert row['snapshot']['quantity'] == '120'


def test_cancellation_can_be_received_but_cannot_write(flow):
    row, bom = submitted(flow)
    amend(flow, cancelled=True)
    assert read(flow)['needs_receipt']
    row = receive(flow)
    assert row['snapshot']['status'] == 'cancelled'
    assert post(flow, 'bom', expected_version=4, bom_id=bom['id'], bom_version=2, target_sets=50, quantity_basis='套数确认').status_code == 409


def test_source_change_racing_submission_has_no_stale_write(flow):
    bound(flow)
    def submit():
        return post(flow, 'requisition', expected_version=2, lines=[dict(row=0, quantity='7'), dict(row=1, quantity='8')])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(amend, flow)
        second = pool.submit(submit)
        first.result(); response = second.result()
    assert response.status_code in {200, 409}
    # If submission won the lock it belongs to the old version and is now blocked.
    assert read(flow)['needs_receipt']
    assert post(flow, 'eta', expected_version=3, requisition_version=3, batches=[]).status_code == 409


def test_explicit_published_selection_and_full_demand_coverage(flow):
    receive(flow)
    material = create(flow)
    draft = create(flow, bom_body(material))
    payload = dict(expected_version=1, bom_id=draft['id'], bom_version=1, target_sets=50, quantity_basis='工程核定')
    assert post(flow, 'bom', **payload).status_code == 422
    published = state(flow, draft, 'published').json()
    body = bom_body(material); body.update(expected_version=2)
    assert flow.put(BASE + '/masters/' + draft['id'], json=body).status_code == 200
    payload['bom_version'] = published['version']
    assert post(flow, 'bom', **payload).status_code == 200
    assert post(flow, 'requisition', expected_version=2, lines=[dict(row=0, quantity='7'), dict(row=0, quantity='1')]).status_code == 422
    assert post(flow, 'requisition', expected_version=2, lines=[dict(row=0, quantity='7')]).status_code == 200
    payload['expected_version'] = 3
    assert post(flow, 'bom', **payload).status_code == 409


def test_scope_unshared_order_feature_flag_and_schema_fail_closed(flow, monkeypatch):
    for factory in ['', 'huakang-d', '*', 'group']:
        assert flow.get(BASE + '/orders', params={'factory_id': factory}).status_code == 422
    assert flow.get(BASE + '/orders?factory_id=huakang-c&factory_id=huakang-d').status_code == 422
    assert flow.post(BASE + '/orders/missing/receive', json=command(dispatch_id='fake')).status_code == 404
    from app.core.config import settings
    monkeypatch.setattr(settings, 'cutting_ops_enabled', False)
    assert flow.get(BASE + '/orders?factory_id=huakang-c').status_code == 503
    with Session(flow.engine) as db:
        line = db.get(Line, 'line-1')
        with pytest.raises(HTTPException) as ex:
            ledger.dispatch(db, line, DispatchIn(expected_revision=line.revision, recipients=['cutting']), 'sales')
        assert ex.value.status_code == 503
        db.rollback()
        line.factory_id = 'huakang-d'; db.commit()
        with pytest.raises(HTTPException) as ex:
            ledger.dispatch(db, line, DispatchIn(expected_revision=line.revision, recipients=['cutting']), 'sales')
        assert ex.value.status_code == 422
    monkeypatch.setattr(settings, 'cutting_ops_enabled', True)
    CuttingOrderRevision.__table__.drop(flow.engine)
    assert flow.get(BASE + '/access?factory_id=huakang-c').json()['orders_schema_ready'] is False
    assert flow.get(BASE + '/orders?factory_id=huakang-c').status_code == 503


def test_mismatched_bom_requires_engineering_evidence_and_disabled_material_blocks_new_demand(flow):
    receive(flow)
    material = create(flow)
    body = bom_body(material); body['data']['item_no'] = 'OTHER'
    bom = state(flow, create(flow, body), 'published').json()
    payload = dict(expected_version=1, bom_id=bom['id'], bom_version=2, target_sets=50, quantity_basis='核定套数')
    assert post(flow, 'bom', **payload).status_code == 422
    assert post(flow, 'bom', **payload, bom_match_basis='商业货号对应内部产品编码').status_code == 200
    assert state(flow, material, 'inactive').status_code == 200
    assert post(flow, 'requisition', expected_version=2, lines=[dict(row=0, quantity='7')]).status_code == 409


def test_received_source_change_cannot_duplicate_existing_purchase_demand(flow):
    _, bom = submitted(flow)
    amend(flow)
    receive(flow)
    assert post(flow, 'bom', expected_version=4, bom_id=bom['id'], bom_version=2, target_sets=60, quantity_basis='新数量核定').status_code == 200
    assert post(flow, 'requisition', expected_version=5, lines=[dict(row=0, quantity='8'), dict(row=1, quantity='9')]).status_code == 409
