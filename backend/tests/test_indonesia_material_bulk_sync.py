"""Bulk material/cycle synchronization is versioned, atomic and preserves history."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from test_indonesia_materials import (client, command, material, product, order, workspace,
    received_flow, allocation, shipment, service, actor, Record)
from test_indonesia_receipt_template import download, values, FIRST_ROW


def payload(orders, products, materials, **changes):
    refs = lambda rows: [dict(id=r['id'], expected_version=r['version']) for r in rows]
    return dict(customer='合成客户', recipient='RRI', item_no='', orders=refs(orders),
                products=refs(products), materials=refs(materials)) | changes


def pending(client, count=2):
    m = material(client); p = product(client, m)
    orders = [order(client, contract=f'BULK-{i}') for i in range(count)]
    new = material(client, name='新增物料', procurement_days=None)
    p = command(client, 'product_save', p['data'] | {'materials': [*p['data']['materials'], dict(material_id=new['id'], usage='2')]}, p)
    return orders, p, new, payload(orders, [p], [new])


def test_updates_ten_contracts_and_exports_all_preserving_history_and_drafts(client):
    m, p, first, sup = received_flow(client)
    first = command(client, 'demand_adjust', dict(demand_id=first['data']['demands'][0]['id'], quantity='123', reason='人工需求'), first)
    orders = [first, *[order(client, contract=f'BULK-{i}') for i in range(9)]]
    excluded = order(client, contract='RRM-ONLY', recipient='RRM')
    a = allocation(client, sup, first, normal='18', spare='0')
    confirmed = command(client, 'shipment_confirm', {}, shipment(client, a, normal='18', spare='0'))
    new = [material(client, code='53003116', name=name, procurement_days=days)
           for name, days in [('绿色拉杆', None), ('蓝色拉杆', 6)]]
    p = command(client, 'product_save', p['data'] | {'materials': [*p['data']['materials'],
        dict(material_id=new[0]['id'], usage='0.5'), dict(material_id=new[1]['id'], usage='1.00000001')]}, p)
    before = {r['id']: r for r in workspace(client)['records']}
    request = payload(orders, [p], new)
    operation = uuid4().hex
    result = command(client, 'order_materials_sync', request, operation_id=operation)
    assert command(client, 'order_materials_sync', request, operation_id=operation) == result
    after = {r['id']: r for r in workspace(client)['records']}
    for original in orders:
        updated = after[original['id']]
        assert updated['version'] == original['version'] + 1
        assert updated['data']['demands'][:1] == original['data']['demands']
        for key in original['data']:
            if key != 'demands': assert updated['data'][key] == original['data'][key]
        assert [Decimal(d['quantity']) for d in updated['data']['demands'][1:]] == [Decimal('50'), Decimal('100.000001')]
        assert updated['data']['demands'][1]['purchase_start'] is None
        exported = download(client, updated).content
        assert values(exported, FIRST_ROW + 1)['正式报关中文名称'] == '绿色拉杆'
        assert values(exported, FIRST_ROW + 2)['正式报关中文名称'] == '蓝色拉杆'
    assert values(download(client, after[first['id']]).content)['剩余未送货数量'] == '105'
    for record in before.values():
        if record['id'] not in {o['id'] for o in orders}: assert after[record['id']] == record
    assert after[confirmed['id']] == confirmed and after[excluded['id']] == excluded
    command(client, 'order_materials_sync', request, status=409)
    assert {r['id']: r for r in workspace(client)['records']} == after
    # A later recipe addition still blocks incomplete templates.
    later = material(client, name='后新增物料')
    command(client, 'product_save', p['data'] | {'materials': [*p['data']['materials'], dict(material_id=later['id'], usage='1')]}, p)
    download(client, after[first['id']], status=409)


@pytest.mark.parametrize('fault', ['order_version', 'product_version', 'material_version', 'missing_order', 'duplicate_order', 'extra_material', 'new_order'])
def test_batch_scope_or_version_conflict_changes_nothing(client, fault):
    orders, p, new, request = pending(client)
    if fault == 'order_version': request['orders'][-1]['expected_version'] += 1
    if fault == 'product_version': request['products'][0]['expected_version'] += 1
    if fault == 'material_version': request['materials'][0]['expected_version'] += 1
    if fault == 'missing_order': request['orders'].pop()
    if fault == 'duplicate_order': request['orders'].append(request['orders'][0])
    if fault == 'extra_material': request['materials'].append(dict(id=p['data']['materials'][0]['material_id'], expected_version=1))
    if fault == 'new_order':
        # A contract already synchronized is not pending; create a historical unsynchronized one.
        fresh = order(client, contract='NEW-CONCURRENT')
        with Session(client.engine) as db:
            row = db.get(Record, fresh['id']); row.data = row.data | {'demands': deepcopy(orders[0]['data']['demands'])}; db.commit()
    before = workspace(client)['records']
    command(client, 'order_materials_sync', request, status=409)
    assert workspace(client)['records'] == before


def test_preserves_missing_plan_and_limits_scope_to_item_customer_and_recipient(client):
    orders, p, new, request = pending(client)
    other_p = product(client, material(client, name='另一货号物料'), code='OTHER')
    other = order(client, item_no='OTHER', contract='OTHER')
    other_p = command(client, 'product_save', other_p['data'] | {'materials': [*other_p['data']['materials'], dict(material_id=new['id'], usage='5')]}, other_p)
    product(client, new, customer='另一客人')
    other_client = order(client, contract='CLIENT', customer='另一客人')
    with Session(client.engine) as db:
        row = db.get(Record, orders[0]['id']); row.data = row.data | {'plan': None}; db.commit()
    request['item_no'] = 'ITEM01'
    command(client, 'order_materials_sync', request)
    after = {r['id']: r for r in workspace(client)['records']}
    assert after[orders[0]['id']]['data']['plan'] is None
    assert after[orders[0]['id']]['data']['demands'][-1]['purchase_start'] is None
    assert after[other['id']] == other and after[other_client['id']] == other_client


def test_mid_write_failure_rolls_back_every_contract(client, monkeypatch):
    orders, p, new, request = pending(client)
    before = workspace(client)['records']; original = service.Ledger.save; calls = 0
    def fail_second(ledger, kind, data, row=None, key=None):
        nonlocal calls
        if kind == 'order':
            calls += 1
            if calls == 2: raise RuntimeError('synthetic write failure')
        return original(ledger, kind, data, row, key)
    with monkeypatch.context() as patch:
        patch.setattr(service.Ledger, 'save', fail_second)
        with pytest.raises(RuntimeError, match='synthetic write failure'):
            command(client, 'order_materials_sync', request)
    assert workspace(client)['records'] == before
    command(client, 'order_materials_sync', request)


def test_batch_requires_factory_write_and_rechecks_identity(client):
    orders, p, new, request = pending(client)
    client.materials_auth['user'] = actor('read')
    command(client, 'order_materials_sync', request, status=403)
    client.materials_auth['user'] = actor('read', 'write', factory='huadeng')
    command(client, 'order_materials_sync', request, status=403)
    command(client, 'order_materials_sync', request, factory='huadeng', status=409)


@pytest.mark.parametrize('days', [0, 16])
def test_sync_existing_cycles_without_new_materials_and_replay(client, days):
    m = material(client, procurement_days=None); p = product(client, m)
    orders = [order(client, contract=f'CYCLE-{i}') for i in range(2)]
    m = command(client, 'material_save', m['data'] | {'procurement_days': days}, m)
    request = payload(orders, [p], [m], sync_procurement=True)
    operation = uuid4().hex
    updated = command(client, 'order_materials_sync', request, operation_id=operation)
    assert command(client, 'order_materials_sync', request, operation_id=operation) == updated
    after = {r['id']: r for r in workspace(client)['records']}
    for original in orders:
        saved = after[original['id']]
        expected = deepcopy(original['data']['demands'])
        start = (date.fromisoformat(original['data']['plan']['required_date']) - timedelta(days=days)).isoformat()
        expected[0].update(procurement_days=days, purchase_start=start)
        assert saved['data']['demands'] == expected
        assert saved['data']['plan'] == original['data']['plan']
    assert all(row['planning_status'] == 'ready' for row in workspace(client)['board'])
    command(client, 'order_materials_sync', request, status=409)
    assert {r['id']: r for r in workspace(client)['records']} == after


def test_mixed_sync_updates_ten_contract_cycles_but_preserves_quantities_allocations_and_exports(client):
    m, p, first, sup = received_flow(client)
    first = command(client, 'demand_adjust', dict(demand_id=first['data']['demands'][0]['id'], quantity='123', reason='保留人工需求'), first)
    orders = [first, *[order(client, contract=f'CYCLE-{i}') for i in range(9)]]
    excluded = order(client, contract='RRM-ONLY', recipient='RRM')
    a = allocation(client, sup, first, normal='18', spare='0')
    confirmed = command(client, 'shipment_confirm', {}, shipment(client, a, normal='18', spare='0'))
    m = command(client, 'material_save', m['data'] | {'procurement_days': 16, 'price': '2'}, m)
    new = material(client, code=m['data']['code'], name='同编码新物料', procurement_days=3)
    p = command(client, 'product_save', p['data'] | {'daily_capacity': '555', 'transport_days': 55,
        'materials': [*p['data']['materials'], dict(material_id=new['id'], usage='2')]}, p)
    before = {r['id']: r for r in workspace(client)['records']}
    command(client, 'order_materials_sync', payload(orders, [p], [m, new], sync_procurement=True))
    after = {r['id']: r for r in workspace(client)['records']}
    for original in orders:
        saved = after[original['id']]
        expected = deepcopy(original['data']['demands'][0])
        required = date.fromisoformat(original['data']['plan']['required_date'])
        expected.update(procurement_days=16, purchase_start=(required - timedelta(days=16)).isoformat())
        assert saved['data']['demands'][0] == expected
        assert saved['data']['demands'][1]['procurement_days'] == 3
        for key in original['data']:
            if key != 'demands': assert saved['data'][key] == original['data'][key]
        assert values(download(client, saved).content, FIRST_ROW + 1)['正式报关中文名称'] == '同编码新物料'
    for id, record in before.items():
        if id not in {o['id'] for o in orders}: assert after[id] == record
    assert after[confirmed['id']] == confirmed and after[excluded['id']] == excluded


@pytest.mark.parametrize('fault', ['old_material_version', 'missing_material', 'missing_order', 'duplicate_material'])
def test_cycle_sync_checks_existing_material_and_complete_scope_versions_atomically(client, fault):
    m = material(client, procurement_days=None); p = product(client, m)
    orders = [order(client, contract=f'CONFLICT-{i}') for i in range(2)]
    m = command(client, 'material_save', m['data'] | {'procurement_days': 16}, m)
    request = payload(orders, [p], [m], sync_procurement=True)
    if fault == 'old_material_version': request['materials'][0]['expected_version'] -= 1
    if fault == 'missing_order': request['orders'].pop()
    if fault == 'duplicate_material': request['materials'].append(request['materials'][0])
    if fault == 'missing_material': request['materials'] = [dict(id=p['id'], expected_version=p['version'])]
    before = workspace(client)['records']
    command(client, 'order_materials_sync', request, status=409)
    assert workspace(client)['records'] == before


def test_unknown_default_does_not_clear_saved_cycle_and_legacy_requests_do_not_update_it(client):
    orders, p, new, request = pending(client)
    m = next(r for r in workspace(client)['records'] if r['id'] == p['data']['materials'][0]['material_id'])
    m = command(client, 'material_save', m['data'] | {'procurement_days': None}, m)
    command(client, 'order_materials_sync', request | {'sync_procurement': True})
    current = {r['id']: r for r in workspace(client)['records']}
    for original in orders: assert current[original['id']]['data']['demands'][0] == original['data']['demands'][0]
    m = command(client, 'material_save', m['data'] | {'procurement_days': 16}, m)
    later = material(client, name='后补物料')
    p = command(client, 'product_save', p['data'] | {'materials': [*p['data']['materials'], dict(material_id=later['id'], usage='1')]}, p)
    command(client, 'order_materials_sync', payload([current[o['id']] for o in orders], [p], [later]))
    after = {r['id']: r for r in workspace(client)['records']}
    for original in orders: assert after[original['id']]['data']['demands'][0] == original['data']['demands'][0]


def test_cycle_sync_preserves_plan_parameters_and_updates_only_cycle_snapshot(client):
    m = material(client); p = product(client, m); o = order(client)
    o = command(client, 'order_plan_save', dict(product_id=p['id'], product_version=p['version'],
        daily_capacity=p['data']['daily_capacity'], transport_days=p['data']['transport_days'],
        materials=[dict(material_id=m['id'], expected_version=m['version'], procurement_days=18)]), o)
    m = command(client, 'material_save', m['data'] | {'procurement_days': 0}, m)
    updated = command(client, 'order_materials_sync', payload([o], [p], [m], sync_procurement=True))
    snapshot = deepcopy(o['data']['planning_snapshot'])
    snapshot['materials'][m['id']] = dict(version=m['version'], procurement_days=0)
    assert updated['data']['planning_snapshot'] == snapshot
    assert updated['data']['plan'] == o['data']['plan']
    assert updated['data']['demands'][0]['purchase_start'] == o['data']['plan']['required_date']


def test_cycle_date_overflow_rejects_whole_batch_and_missing_plan_stays_missing(client):
    m = material(client, procurement_days=0); p = product(client, m)
    orders = [order(client, contract=f'DATES-{i}') for i in range(2)]
    m = command(client, 'material_save', m['data'] | {'procurement_days': 16}, m)
    request = payload(orders, [p], [m], sync_procurement=True)
    with Session(client.engine) as db:
        row = db.get(Record, orders[1]['id'])
        row.data = row.data | {'plan': row.data['plan'] | {'required_date': '0001-01-01'}}; db.commit()
    before = workspace(client)['records']
    command(client, 'order_materials_sync', request, status=422)
    assert workspace(client)['records'] == before
    with Session(client.engine) as db:
        row = db.get(Record, orders[1]['id']); row.data = row.data | {'plan': None}; db.commit()
    command(client, 'order_materials_sync', request)
    saved = next(r for r in workspace(client)['records'] if r['id'] == orders[1]['id'])
    assert saved['data']['plan'] is None
    assert saved['data']['demands'][0]['procurement_days'] == 16
    assert saved['data']['demands'][0]['purchase_start'] is None
