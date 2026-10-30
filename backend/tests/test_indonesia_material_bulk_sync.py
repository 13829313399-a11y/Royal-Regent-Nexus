"""Bulk material synchronization is append-only, versioned and atomic."""
from copy import deepcopy
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
