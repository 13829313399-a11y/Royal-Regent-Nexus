"""Contract-local planning changes must never regenerate commercial/demand history."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from test_indonesia_materials import (client, command, material, product, order, workspace,
    received_flow, allocation, shipment, service, actor, Record)


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
