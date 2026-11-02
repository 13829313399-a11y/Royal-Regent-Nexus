"""Mixed-unit custody and costing through API commands in disposable SQLite."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import runpy

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy.orm import Session

from app.models.fabric_master import FabricMasterRecord
from test_cutting_materials import (bridge, client, flow, planned, actor, request_body, send,
    decision, warehouse_post, warehouse_view)
from test_cutting_ops import BASE, command, create, state
from test_cutting_orders import read as order_read, post as order_post
from test_cutting_planning import task, save, publish
from test_cutting_reporting import send as report, ok
from test_cutting_usage import read, write
from test_cutting_cost_allocation import allocation_body


@pytest.fixture
def mixed(bridge):
    p = bridge
    for name in ['20261010_0155_cutting_production_events.py', '20261014_0156_cutting_material_usage.py']:
        migration = runpy.run_path(str(Path(__file__).parents[1] / 'alembic/versions' / name))
        with p.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration['upgrade']()
    p.cutting_auth['user'] = actor('master_write', 'bom_write', 'bom_publish', 'requisition_submit',
        'requisition_reconcile', 'plan_write', 'plan_publish', 'material_request', 'material_receive',
        'usage_write', 'cost_read', 'cost_write', 'allocation_confirm', 'report_write')
    kg = create(p, command(kind='material', code='CUT-KG', data=dict(name='公斤验收布料', category='fabric',
        unit='公斤', color='蓝', specification='规格A', source_reference='合成验收，不用于真实库存')))
    current = order_read(p)['current']['data']
    bom = current['bom']
    data = deepcopy(bom['data'])
    data['requirements'][1].update(material_id=kg['id'], material_version=kg['version'], unit='公斤', required_for_cutting=True)
    edited = p.put(BASE + '/masters/' + bom['id'], json=command(kind='bom', code=bom['code'],
        expected_version=bom['version'], data=data))
    assert edited.status_code == 200, edited.text
    published = state(p, edited.json(), 'published')
    assert published.status_code == 200, published.text

    def change(action, **kw):
        response = order_post(p, action, expected_version=order_read(p)['current']['version'], **kw)
        assert response.status_code == 200, response.text

    req_version = current['requisition']['version']
    change('withdraw', requisition_version=req_version)
    change('reconcile', requisition_version=req_version, disposition='cancelled_or_reallocated',
           evidence='合成原采购承诺已核对处置', all_handled=True)
    change('bom', bom_id=bom['id'], bom_version=published.json()['version'], target_sets=50, quantity_basis='订单100件按50套')
    change('requisition', lines=[dict(row=i, quantity='0', purchase_mode='no_purchase', no_purchase_reason='合成库存供料') for i in range(2)])
    old = current['planning']['published']['tasks'][0]
    ref = dict(id=old['resource_id'], version=old['resource_version'])
    t = task(ref, materials=[dict(row=i, expected_date='2026-10-12') for i in range(2)])
    assert save(p, [t]).status_code == 200
    assert publish(p).status_code == 200
    with Session(p.engine) as db:
        db.add(FabricMasterRecord(id='fabric-kg', factory_id='huakang-c', kind='MATERIAL', code='FAB-KG',
            name='公斤验收布料', status='ACTIVE', revision=1, updated_at='2026-10-10',
            data_json=json.dumps(dict(category='FABRIC', unit='公斤', spec='规格A', color='蓝'))))
        db.commit()
    kg_stock = warehouse_post(p, 'RECEIPT', quantity='20', source_no='mixed-kg', source_line='1',
        item_code='FAB-KG', item_name='公斤验收布料', unit='公斤', location_id='bin', lot='KG', counterparty='合成供方')
    p.mixed_kg_batch = kg_stock['id']
    receipts, p.mixed_issues = [], {}
    for unit, row, material, quantity, batch in [('米', 0, 'fabric-mat', '2', p.stock_id), ('公斤', 1, 'fabric-kg', '3', kg_stock['id'])]:
        requested = send(p, 'request', request_body(p) | dict(row=row, material_id=material, quantity=quantity))
        issued = warehouse_post(p, 'ISSUE', original_id=requested['id'], batch_id=batch, quantity=quantity, counterparty='R01')
        received = send(p, 'receive', decision(p, issued, quantity=quantity))
        p.mixed_issues[unit] = issued['id']
        receipts.append(received['id'])
    t.update(date_basis='actual', actual_issue_date='2026-10-10', actual_issue_reference='两行实收及前置条件核对', material_receipt_ids=receipts)
    assert save(p, [t]).status_code == 200
    assert publish(p).status_code == 200
    ok(report(p, sets=4, exception_reason=''))
    p.issue_id = p.mixed_issues['米']
    return p


def confirm(p):
    current = read(p, True)
    group = current['cost_allocation']['groups'][0]
    body = allocation_body(p) | dict(allocations=[dict(issue_id=p.mixed_issues[u], completed_quantity=q)
        for u, q in [('米', '0.8'), ('公斤', '0.9')]], basis_token=group['basis_token'])
    response = p.post(BASE + '/orders/line-1/usage/allocate', json=body)
    assert response.status_code == 200, response.text
    return read(p, True)['cost_allocation']['groups'][0]


def test_mixed_units_reconcile_returns_cents_corrections_and_currency_without_conversion(mixed):
    p = mixed
    stock = warehouse_view(p)['stock']
    m_doc, _ = write(p, 'post', issue_id=p.mixed_issues['米'], consumed_quantity='1.2', loss_quantity='0.2', counted_remaining='0.6')
    write(p, 'post', issue_id=p.mixed_issues['公斤'], consumed_quantity='1.5', loss_quantity='0.3', counted_remaining='1.2')
    assert warehouse_view(p)['stock'] == stock
    pending = read(p, True)
    assert pending['pending_pricing'] == 2 and all(r['normal_cost'] is None for r in pending['issues'])
    assert 'cost_summary' not in read(p)
    for unit, quantity in [('米', '0.1'), ('公斤', '0.2')]:
        warehouse_post(p, 'RETURN', original_id=p.mixed_issues[unit], quantity=quantity, location_id='bin')
    for unit, price in [('米', '3.125'), ('公斤', '7.333333')]:
        write(p, 'price', issue_id=p.mixed_issues[unit], unit_cost=price, currency='CNY', price_reference='原批次实际成本合成凭据')
    group = confirm(p)
    assert group['completed_sets'] == 4 and group['status'] == 'confirmed'
    assert group['costs'] == {'CNY': dict(completed='9.10', wip='5.65', loss='2.83', unit_cost='2.275000')}
    assert read(p, True)['cost_summary']['tasks'][0]['costs']['CNY'] == dict(normal='14.75', loss='2.83', total='17.58')
    before = read(p, True)
    write(p, 'correct', document_id=m_doc['document_id'], issue_id=p.mixed_issues['米'],
          consumed_quantity='1.1', loss_quantity='0.2', counted_remaining='0.7')
    corrected = read(p, True)
    assert corrected['cost_allocation']['groups'][0]['status'] == 'stale'
    old = next(d for d in corrected['documents'] if d['id'] == m_doc['document_id'])
    assert old['voided'] and old['entry']['counted_remaining'] == '0.6'
    replacement = next(d for d in corrected['documents'] if d.get('replaces_document_id') == old['id'])
    assert replacement['warehouse_cutoff'] == old['warehouse_cutoff']
    assert replacement['cost_at_post']['currency'] == 'CNY'
    quantities = {r['context']['unit']: r for r in corrected['issues']}
    assert quantities['米']['remaining_quantity'] == '0.6' and quantities['公斤']['remaining_quantity'] == '1.0'
    group = confirm(p)
    assert group['costs']['CNY'] == dict(completed='9.10', wip='5.34', loss='2.83', unit_cost='2.275000')
    assert read(p, True)['cost_allocation']['history'][-1]['replaces_id'] == before['cost_allocation']['history'][-1]['id']
    write(p, 'price', issue_id=p.mixed_issues['米'], unit_cost='3.125', currency='HKD', price_reference='更正币种合成凭据，未锁批次')
    changed = read(p, True)
    assert changed['cost_allocation']['groups'][0]['costs'] == {
        'CNY': dict(completed='6.60', wip='4.40', loss='2.20', unit_cost='1.650000'),
        'HKD': dict(completed='2.50', wip='0.94', loss='0.63', unit_cost='0.625000')}
    assert next(d for d in changed['documents'] if d['id'] == replacement['id'])['cost_at_post']['currency'] == 'CNY'
    write(p, 'price', issue_id=p.mixed_issues['米'], unit_cost='0', currency='HKD', price_reference='客户供料显式零成本合成凭据')
    zero = read(p, True)
    assert zero['pending_pricing'] == 0
    assert zero['cost_allocation']['groups'][0]['costs']['HKD'] == dict(completed='0.00', wip='0.00', loss='0.00', unit_cost='0.000000')
    assert len(zero['price_history']) == 4
    totals = {unit: sum(Decimal(r['quantity']) for r in warehouse_view(p)['stock'] if r['unit'] == unit) for unit in ['米', '公斤']}
    assert totals == {'米': Decimal('18.1'), '公斤': Decimal('17.2')}


def test_same_kg_root_rounds_each_original_issue_before_summing(mixed):
    p = mixed
    requested = send(p, 'request', request_body(p) | dict(row=1, material_id='fabric-kg', quantity='0.1'))
    second = warehouse_post(p, 'ISSUE', original_id=requested['id'], batch_id=p.mixed_kg_batch,
                            quantity='0.1', counterparty='R01')
    send(p, 'receive', decision(p, second, quantity='0.1'))
    write(p, 'post', issue_id=p.mixed_issues['公斤'], consumed_quantity='0.25', loss_quantity='0', counted_remaining='2.75')
    write(p, 'post', issue_id=second['id'], consumed_quantity='0.1', loss_quantity='0', counted_remaining='0')
    write(p, 'price', issue_id=second['id'], unit_cost='7.333333', currency='CNY', price_reference='同原公斤批次实际成本凭据')
    value = read(p, True)
    kg = next(m for m in value['cost_summary']['materials'] if m['unit'] == '公斤')
    assert kg['consumed_quantity'] == '0.35'
    # 1.83 + 0.73 = 2.56, instead of repricing aggregated 0.35 kg as 2.57.
    assert kg['costs'] == {'CNY': dict(normal='2.56', loss='0.00', total='2.56')}
    assert value['cost_summary']['tasks'][0]['costs'] == kg['costs']
    issues = [r for r in value['issues'] if r['context']['unit'] == '公斤']
    assert {r['normal_cost'] for r in issues} == {'1.83', '0.73'}
    assert len({r['price']['version'] for r in issues}) == 1
