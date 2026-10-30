"""Contract-local planning changes must never regenerate commercial/demand history."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from test_indonesia_materials import (client, command, material, product, order, workspace,
    received_flow, allocation, shipment, service, actor, Record)
from test_indonesia_receipt_template import download, values, FIRST_ROW


def plan_payload(p, m, **changes):
    return dict(product_id=p['id'], product_version=p['version'], daily_capacity='20', transport_days=10,
                materials=[dict(material_id=m['id'], expected_version=m['version'], procurement_days=5)]) | changes


def test_current_plan_only_preserves_overrides_commercial_snapshots_and_confirmed_shipment(client):
    m, p, original, sup = received_flow(client)
    other = order(client, contract='TEST-B')
    a = allocation(client, sup, original)
    ship = command(client, 'shipment_confirm', {}, shipment(client, a))
    before = deepcopy(workspace(client)['records'])
    payload = plan_payload(p, m)
    key = uuid4().hex
    updated = command(client, 'order_plan_save', payload, original, operation_id=key)
    assert command(client, 'order_plan_save', payload, original, operation_id=key) == updated
    for key in ('product_snapshot', 'quantity', 'batch', 'po_no', 'item_no', 'delivery_date'):
        assert updated['data'].get(key) == original['data'].get(key)
    expected = deepcopy(original['data']['demands'])
    for d in expected:
        d.update(procurement_days=5, purchase_start='2026-11-08')
    assert updated['data']['demands'] == expected
    assert updated['data']['plan']['required_date'] == '2026-11-13'
    after = {r['id']: r for r in workspace(client)['records']}
    for old in before:
        if old['id'] not in {m['id'], p['id'], original['id']}:
            assert after[old['id']] == old
    assert after[m['id']]['data'] == m['data'] | {'procurement_days': 5}
    assert after[p['id']]['data'] == p['data'] | {'daily_capacity': '20', 'transport_days': 10}
    assert after[other['id']] == other and after[ship['id']] == ship


@pytest.mark.parametrize('fault', ['product_version', 'material_version', 'order_version', 'missing', 'duplicate', 'extra', 'wrong_product'])
def test_rejects_stale_or_mismatched_plan_without_partial_master_changes(client, fault):
    m = material(client); p = product(client, m); o = order(client)
    extra = material(client, code='EXTRA'); other = product(client, extra, code='OTHER')
    payload = plan_payload(p, m); target = deepcopy(o)
    if fault == 'product_version': payload['product_version'] += 1
    if fault == 'material_version': payload['materials'][0]['expected_version'] += 1
    if fault == 'order_version': target['version'] += 1
    if fault == 'missing': payload['materials'] = []
    if fault == 'duplicate': payload['materials'] *= 2
    if fault == 'extra': payload['materials'].append(dict(material_id=extra['id'], expected_version=extra['version'], procurement_days=3))
    if fault == 'wrong_product': payload.update(product_id=other['id'], product_version=other['version'])
    before = deepcopy(workspace(client)['records'])
    command(client, 'order_plan_save', payload, target, status=409 if fault.endswith('version') else 422)
    assert workspace(client)['records'] == before


def test_uses_frozen_demand_materials_despite_changed_recipe_and_price(client):
    m = material(client); p = product(client, m); o = order(client)
    replacement = material(client, code='REPLACEMENT')
    p = command(client, 'product_save', p['data'] | {'materials': [dict(material_id=replacement['id'], usage='9')]}, p)
    m = command(client, 'material_save', m['data'] | {'price': '99'}, m)
    updated = command(client, 'order_plan_save', plan_payload(p, m), o)
    assert updated['data']['demands'][0]['id'] == o['data']['demands'][0]['id']
    assert updated['data']['demands'][0]['material_snapshot'] == o['data']['demands'][0]['material_snapshot']
    assert updated['data']['product_snapshot'] == o['data']['product_snapshot']


def test_invalid_dates_roll_back_and_inactive_historical_customer_can_plan(client):
    m = material(client); p = product(client, m); o = order(client)
    c = next(r for r in workspace(client)['records'] if r['kind'] == 'customer')
    command(client, 'customer_save', c['data'] | {'status': 'inactive'}, c)
    updated = command(client, 'order_plan_save', plan_payload(p, m), o)
    with Session(client.engine) as db:
        row = db.get(Record, o['id']); row.data = row.data | {'delivery_date': '0001-01-01'}; db.commit()
    records = workspace(client)['records']
    current = {r['id']: r for r in records}
    command(client, 'order_plan_save', plan_payload(current[p['id']], current[m['id']]), updated, status=422)
    assert workspace(client)['records'] == records


def test_plan_write_requires_current_factory_write_permission(client):
    m = material(client); p = product(client, m); o = order(client)
    client.materials_auth['user'] = actor('read')
    command(client, 'order_plan_save', plan_payload(p, m), o, status=403)
    client.materials_auth['user'] = actor('read', 'write', factory='huadeng')
    command(client, 'order_plan_save', plan_payload(p, m), o, factory='huadeng', status=404)


@pytest.mark.parametrize('code', ['53003116', ''])
def test_sync_appends_distinct_materials_and_exports_all_without_changing_history(client, code):
    m, p, original, sup = received_flow(client)
    original = command(client, 'demand_adjust', dict(demand_id=original['data']['demands'][0]['id'], quantity='123', reason='保留人工需求'), original)
    other = order(client, contract='TEST-OTHER')
    a = allocation(client, sup, original, normal='18', spare='0')
    ship = command(client, 'shipment_confirm', {}, shipment(client, a, normal='18', spare='0'))
    added = [material(client, code=code, name=name) for name in ('塑胶件-绿色拉杆', '塑胶件-蓝色拉杆', '塑胶件-推杆')]
    p = command(client, 'product_save', p['data'] | {'materials': [*p['data']['materials'],
        *[dict(material_id=row['id'], usage=usage) for row, usage in zip(added, ['2', '0.5', '1.00000001'])]]}, p)
    before = deepcopy(workspace(client)['records'])
    assert '新增物料待同步' in download(client, original, status=409).text
    assert workspace(client)['records'] == before
    payload = plan_payload(p, m, sync_materials=True)
    payload['materials'] += [dict(material_id=row['id'], expected_version=row['version'], procurement_days=6) for row in added]
    key = uuid4().hex
    updated = command(client, 'order_plan_save', payload, original, operation_id=key)
    assert command(client, 'order_plan_save', payload, original, operation_id=key) == updated
    demands = updated['data']['demands']
    assert len(demands) == len({d['id'] for d in demands}) == 4
    expected = deepcopy(original['data']['demands'][0])
    expected.update(procurement_days=5, purchase_start='2026-11-08')
    assert demands[0] == expected
    assert [Decimal(d['quantity']) for d in demands] == list(map(Decimal, ['123', '200', '50', '100.000001']))
    assert [d['material_snapshot']['id'] for d in demands[1:]] == [r['id'] for r in added]
    assert updated['data']['product_snapshot'] == original['data']['product_snapshot']
    after = {r['id']: r for r in workspace(client)['records']}
    for row in before:
        if row['id'] not in {original['id'], p['id'], m['id'], *(r['id'] for r in added)}:
            assert after[row['id']] == row
    assert after[a['id']]['data']['normal_quantity'] == '18'
    assert after[ship['id']] == ship and after[other['id']] == other
    book = download(client, updated).content
    rows = [values(book, FIRST_ROW + i) for i in range(4)]
    assert [Decimal(r['本次订单物料需求数量']) for r in rows] == list(map(Decimal, ['123', '200', '50', '100.000001']))
    assert [Decimal(r['剩余未送货数量']) for r in rows] == list(map(Decimal, ['105', '200', '50', '100.000001']))
    assert rows[0]['已实收并分配数量'] == '18'
    assert [r['正式报关中文名称'] for r in rows[1:]] == [r['data']['name'] for r in added]
    current = plan_payload(after[p['id']], after[m['id']], sync_materials=True)
    current['materials'] += [dict(material_id=r['id'], expected_version=after[r['id']]['version'], procurement_days=6) for r in added]
    again = command(client, 'order_plan_save', current, updated)
    assert again['data']['demands'] == demands


@pytest.mark.parametrize('fault', ['missing_new', 'new_version', 'recipe_version', 'extra'])
def test_material_sync_rejects_incomplete_or_stale_versions_atomically(client, fault):
    m = material(client); p = product(client, m); o = order(client)
    added = material(client, name='新增拉杆'); extra = material(client, name='非本货号物料')
    p = command(client, 'product_save', p['data'] | {'materials': [*p['data']['materials'], dict(material_id=added['id'], usage='2')]}, p)
    payload = plan_payload(p, m, sync_materials=True)
    payload['materials'].append(dict(material_id=added['id'], expected_version=added['version'], procurement_days=10))
    if fault == 'missing_new': payload['materials'].pop()
    if fault == 'new_version': payload['materials'][-1]['expected_version'] += 1
    if fault == 'recipe_version': payload['product_version'] -= 1
    if fault == 'extra': payload['materials'].append(dict(material_id=extra['id'], expected_version=extra['version'], procurement_days=10))
    before = deepcopy(workspace(client)['records'])
    command(client, 'order_plan_save', payload, o, status=409 if fault.endswith('version') else 422)
    assert workspace(client)['records'] == before


def test_material_sync_keeps_removed_recipe_demands_and_existing_usage_changes_frozen(client):
    m = material(client); p = product(client, m); o = order(client)
    added = material(client, name='替换物料')
    p = command(client, 'product_save', p['data'] | {'materials': [dict(material_id=added['id'], usage='2')]}, p)
    payload = plan_payload(p, m, sync_materials=True)
    payload['materials'].append(dict(material_id=added['id'], expected_version=added['version'], procurement_days=10))
    updated = command(client, 'order_plan_save', payload, o)
    assert [d['material_id'] for d in updated['data']['demands']] == [m['id'], added['id']]
    assert updated['data']['demands'][0]['quantity'] == o['data']['demands'][0]['quantity']


def test_material_sync_preserves_large_eight_decimal_multiplication(client):
    m = material(client); p = product(client, m, daily_capacity='1000000000000')
    amount = '999999999999.12345678'
    o = order(client, quantity=amount)
    added = material(client, name='大数精度物料')
    p = command(client, 'product_save', p['data'] | {'materials': [*p['data']['materials'], dict(material_id=added['id'], usage=amount)]}, p)
    payload = plan_payload(p, m, sync_materials=True, daily_capacity='1000000000000')
    payload['materials'].append(dict(material_id=added['id'], expected_version=added['version'], procurement_days=10))
    updated = command(client, 'order_plan_save', payload, o)
    with localcontext() as ctx:
        ctx.prec = 80
        expected = service.decimal_text(Decimal(amount) * Decimal(amount))
    assert updated['data']['demands'][1]['quantity'] == expected


def test_missing_procurement_cycles_do_not_block_material_sync_or_receipt_template(client):
    m = material(client); p = product(client, m); o = order(client)
    added = material(client, name='未填采购周期物料', procurement_days=None)
    p = command(client, 'product_save', p['data'] | {'materials': [*p['data']['materials'], dict(material_id=added['id'], usage='2')]}, p)
    payload = plan_payload(p, m, sync_materials=True)
    payload['materials'].append(dict(material_id=added['id'], expected_version=added['version'], procurement_days=None))
    updated = command(client, 'order_plan_save', payload, o)
    new_demand = updated['data']['demands'][1]
    assert new_demand['quantity'] == '200' and new_demand['procurement_days'] is None and new_demand['purchase_start'] is None
    assert values(download(client, updated).content, FIRST_ROW + 1)['本次订单物料需求数量'] == '200'
    data = workspace(client)
    board = next(row for row in data['board'] if row['id'] == o['id'])
    assert board['planning_status'] == 'missing_parameters' and len(board['demands']) == 2
    current = {r['id']: r for r in data['records']}
    payload = plan_payload(current[p['id']], current[m['id']], sync_materials=True)
    payload['materials'].append(dict(material_id=added['id'], expected_version=current[added['id']]['version'], procurement_days=0))
    completed = command(client, 'order_plan_save', payload, updated)
    assert completed['data']['demands'][1]['id'] == new_demand['id']
    assert completed['data']['demands'][1]['purchase_start'] == completed['data']['plan']['required_date']


@pytest.mark.parametrize('omit_days', [False, True])
def test_legacy_plan_commands_still_reject_unknown_cycles_without_partial_writes(client, omit_days):
    m = material(client); p = product(client, m); o = order(client)
    payload = plan_payload(p, m)
    if omit_days:
        payload['materials'][0].pop('procurement_days')
    else:
        payload['materials'][0]['procurement_days'] = None
    before = deepcopy(workspace(client)['records'])
    command(client, 'order_plan_save', payload, o, status=422)
    assert workspace(client)['records'] == before
