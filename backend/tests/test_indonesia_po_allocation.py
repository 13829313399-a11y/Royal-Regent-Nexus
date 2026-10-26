"""PO demand survives schedule revisions; allocation starts only at actual receipt."""
from copy import deepcopy
from io import BytesIO
import openpyxl
from test_indonesia_materials import (client, command, material, product, order, supply, allocation,
    historical_allocation, workspace, schedule_bytes, BASE)
from test_indonesia_warehouse_import import preview as receipt_preview, source, choose, confirm
from test_indonesia_materials import actor
from test_indonesia_materials import Receipt, service
from sqlalchemy.orm import Session


def schedule_preview(client, content):
    response = client.post(BASE + '/imports/preview', data=dict(factory_id='huaxing', customer='合成客户', recipient='RRI'),
                           files={'file': ('schedule.xlsx', content)})
    assert response.status_code == 200, response.text
    return response.json()['record']


def modified_schedule(po='PO-TWO', date='2026-11-30', append=False):
    wb = openpyxl.load_workbook(BytesIO(schedule_bytes()))
    if append:
        wb.active.append(['TEST-I', 'SO-TEST', po, '00001', 50, date, '合成客户'])
    else:
        wb.active['C4'] = po; wb.active['F4'] = date
    result = BytesIO(); wb.save(result); return result.getvalue()


def test_orders_need_no_delivery_batch_and_po_identity_survives_date_change(client):
    product(client, material(client))
    payload = dict(customer='合成客户', recipient='RRI', contract_no='C', po_no='PO-A', item_no='ITEM01', quantity='100', delivery_date='2026-11-30')
    first = command(client, 'order_save', payload)
    assert first['data']['batch'] == ''
    second = command(client, 'order_save', payload | {'po_no': 'PO-B'})
    assert first['id'] != second['id']
    command(client, 'order_save', payload, status=409)
    updated = command(client, 'order_save', payload | {'delivery_date': '2026-12-01', 'reason': '客户改期'}, first)
    assert updated['id'] == first['id']
    command(client, 'order_save', payload, status=409)
    command(client, 'order_save', payload | {'po_no': 'PO-C', 'reason': '改变身份'}, updated, status=422)


def test_schedule_two_pos_without_batch_and_reschedule_never_duplicate_demand(client):
    product(client, material(client), code='00001')
    preview = schedule_preview(client, modified_schedule(append=True))
    assert len(preview['data']['rows']) == 2 and all(not row['blocked'] and row['batch'] == '' for row in preview['data']['rows'])
    command(client, 'import_confirm', {'indexes': [0, 1]}, preview)
    changed = schedule_preview(client, modified_schedule(po='PO-TEST', date='2026-12-15'))
    assert changed['data']['rows'][0]['blocked'] and changed['data']['rows'][0]['match_status'] == 'changed'
    command(client, 'import_confirm', {'indexes': [0]}, changed, status=422)
    assert len([r for r in workspace(client)['records'] if r['kind'] == 'order']) == 2


def test_batchless_schedule_matches_unique_history_but_blocks_ambiguous_or_missing_po(client):
    product(client, material(client), code='00001')
    old = order(client, contract='TEST-I', item_no='00001', po_no='PO-TEST')
    preview = schedule_preview(client, schedule_bytes())
    assert preview['data']['rows'][0]['match_status'] == 'unchanged'
    confirmed = command(client, 'import_confirm', {'indexes': [0]}, preview)
    assert confirmed['data']['order_ids'] == [old['id']]
    order(client, contract='TEST-I', item_no='00001', po_no='PO-TEST', batch='2')
    ambiguous = schedule_preview(client, modified_schedule(po='PO-TEST'))
    assert ambiguous['data']['rows'][0]['blocked']
    order(client, contract='TEST-I', item_no='00001', po_no='', batch='legacy-no-po')
    unknown = schedule_preview(client, modified_schedule(po='PO-NEW'))
    assert unknown['data']['rows'][0]['blocked']


def test_expected_stock_cannot_allocate_or_reallocate_and_history_remains_readable(client):
    m = material(client); product(client, m); first = order(client); second = order(client, contract='OTHER')
    sup = supply(client, m)
    payload = dict(supply_id=sup['id'], order_id=first['id'], demand_id=first['data']['demands'][0]['id'], normal_quantity='90', spare_quantity='10')
    command(client, 'allocate', payload, status=422)
    old = historical_allocation(client, sup, first)
    command(client, 'reallocate', dict(order_id=second['id'], demand_id=second['data']['demands'][0]['id'], normal_quantity='90', spare_quantity='10', reason='未回料'), old, status=422)
    unchanged = next(r for r in workspace(client)['records'] if r['id'] == old['id'])
    assert unchanged['version'] == old['version']
    assert {key: unchanged['data'][key] for key in old['data']} == old['data']
    sup = command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, sup)
    moved = command(client, 'reallocate', dict(order_id=second['id'], demand_id=second['data']['demands'][0]['id'], normal_quantity='90', spare_quantity='10', reason='已实收点选 PO'), old)
    assert moved['data']['order_id'] == second['id']


def test_actual_receipt_can_be_split_to_selected_pos_without_delivery_batches(client):
    m = material(client); product(client, m)
    first = order(client, batch='', po_no='PO-A', quantity='60'); second = order(client, batch='', po_no='PO-B', quantity='40')
    received = receipt_preview(client, source())
    row = received['data']['rows'][0]; targets = row['targets'][m['id']]
    assert all('PO ' in target['label'] and '历史批次' not in target['label'] for target in targets)
    plans = []
    for target in targets:
        quantities = ('60', '0') if target['order_id'] == first['id'] else ('30', '10')
        plans.append({k: target[k] for k in ('order_id', 'demand_id', 'order_version')} | dict(normal_quantity=quantities[0], spare_quantity=quantities[1]))
    posted = confirm(client, received, [choose(received, targets=plans)])
    data = workspace(client)
    assert all(row['status'] == 'complete' for row in data['board'])
    shipment = next(row for row in data['records'] if row['id'] in posted['data']['shipment_ids'])
    assert len(shipment['data']['lines']) == 2 and shipment['data']['packages'] == []


def test_receipt_customer_po_hint_is_enforced_at_confirm(client):
    m = material(client); product(client, m)
    a = order(client, batch='', po_no='PO-A'); b = order(client, batch='', po_no='PO-B')
    received = receipt_preview(client, source(po_no='PO-B'))
    targets = received['data']['rows'][0]['targets'][m['id']]
    assert len(targets) == 1 and targets[0]['order_id'] == b['id']
    selection = choose(received)
    selection['allocations'][0].update(order_id=a['id'], demand_id=a['data']['demands'][0]['id'], order_version=a['version'])
    confirm(client, received, [selection], status=422)
    assert not any(row['kind'] in ('supply', 'allocation', 'shipment') for row in workspace(client)['records'])


def test_old_explicit_batch_file_cannot_duplicate_a_new_po_order(client):
    product(client, material(client), code='00001')
    original = order(client, contract='TEST-I', item_no='00001', batch='', po_no='PO-TEST')
    order_data = {k: v for k, v in original['data'].items() if k in ('customer', 'recipient', 'contract_no', 'po_no', 'item_no', 'quantity', 'unit', 'delivery_date')}
    command(client, 'order_save', order_data | {'batch': '1'}, status=409)
    wb = openpyxl.load_workbook(BytesIO(schedule_bytes()))
    wb.active['H3'] = '交付批次'; wb.active['H4'] = '1'
    stream = BytesIO(); wb.save(stream)
    preview = schedule_preview(client, stream.getvalue())
    row = preview['data']['rows'][0]
    assert row['blocked'] and row['existing_order_id'] == original['id']
    command(client, 'import_confirm', {'indexes': [0]}, preview, status=422)
    assert len([r for r in workspace(client)['records'] if r['kind'] == 'order']) == 1


def test_missing_po_never_creates_a_second_demand_and_can_be_filled_once(client):
    product(client, material(client), code='00001')
    existing = order(client, contract='TEST-I', item_no='00001', batch='', po_no='PO-A')
    preview = schedule_preview(client, modified_schedule(po=''))
    assert preview['data']['rows'][0]['blocked']
    command(client, 'import_confirm', {'indexes': [0]}, preview, status=422)
    incomplete = order(client, contract='TEST-EMPTY', item_no='00001', batch='', po_no='')
    data = {k: incomplete['data'][k] for k in ('customer', 'recipient', 'contract_no', 'item_no', 'quantity', 'delivery_date')}
    command(client, 'order_save', data | {'po_no': 'LATER'}, status=409)
    command(client, 'order_save', data | {'po_no': 'LATER', 'batch': '1'}, status=409)
    saved = command(client, 'order_save', data | {'po_no': 'LATER', 'reason': '补齐客户 PO'}, incomplete)
    assert saved['id'] == incomplete['id']
    command(client, 'order_save', data | {'po_no': 'AGAIN', 'reason': '换 PO'}, saved, status=422)
    assert len([r for r in workspace(client)['records'] if r['kind'] == 'order']) == 2


def test_sales_can_explicitly_replace_legacy_expected_allocation_when_actual_po_differs(client):
    m = material(client); product(client, m)
    a = order(client, batch='', po_no='PO-A'); b = order(client, batch='', po_no='PO-B')
    sup = supply(client, m); old = historical_allocation(client, sup, a)
    client.materials_auth['user'] = actor('read', 'write')
    received = receipt_preview(client, source(po_no='PO-B', purchase_no=sup['data']['purchase_no']))
    picked = choose(received, supply_id=sup['id'], supply_version=sup['version'])
    confirm(client, received, [picked], status=409)  # Never silently cancel the old PO's allocation.
    assert next(r for r in workspace(client)['records'] if r['id'] == sup['id'])['data']['status'] == 'expected'
    picked.update(replace_allocations=[dict(allocation_id=old['id'], version=old['version'] + 1)], replacement_reason='本次原单明确给 PO-B')
    confirm(client, received, [picked], status=409)
    picked['replace_allocations'][0]['version'] = old['version']
    done = confirm(client, received, [picked])
    actual = workspace(client)
    prior = next(r for r in actual['records'] if r['id'] == old['id'])
    assert prior['data']['normal_quantity'] == prior['data']['spare_quantity'] == '0'
    assert prior['data']['order_id'] == a['id'] and prior['data']['replaced_by_import_id'] == received['id']
    current = next(r for r in actual['records'] if r['kind'] == 'allocation' and r['id'] != old['id'])
    assert current['data']['order_id'] == b['id']
    saved_supply = next(r for r in actual['records'] if r['id'] == sup['id'])
    assert saved_supply['data']['material_snapshot'] == sup['data']['material_snapshot']
    assert done['data']['shipment_ids']


def test_explicit_legacy_replacement_can_keep_part_of_the_original_po(client):
    m = material(client); product(client, m)
    a = order(client, batch='', po_no='PO-A'); b = order(client, batch='', po_no='PO-B')
    sup = supply(client, m); old = historical_allocation(client, sup, a)
    received = receipt_preview(client, source(purchase_no=sup['data']['purchase_no']))
    targets = received['data']['rows'][0]['targets'][m['id']]
    plans = [{k: target[k] for k in ('order_id', 'demand_id', 'order_version')} |
        dict(normal_quantity='60' if target['order_id'] == a['id'] else '30', spare_quantity='0' if target['order_id'] == a['id'] else '10') for target in targets]
    choice = choose(received, targets=plans, supply_id=sup['id'], supply_version=sup['version'],
        replace_allocations=[dict(allocation_id=old['id'], version=old['version'])], replacement_reason='分供两个 PO')
    confirm(client, received, [choice])
    allocations = [r for r in workspace(client)['records'] if r['kind'] == 'allocation']
    assert len(allocations) == 3
    assert next(r for r in allocations if r['id'] == old['id'])['data']['normal_quantity'] == '0'
    assert next(r for r in allocations if r['data']['order_id'] == a['id'] and r['id'] != old['id'])['data']['normal_quantity'] == '60'


def test_completed_legacy_expected_allocation_command_replays_its_original_receipt(client):
    m = material(client); product(client, m); o = order(client); sup = supply(client, m)
    prior = historical_allocation(client, sup, o)
    payload = dict(supply_id=sup['id'], order_id=o['id'], demand_id=o['data']['demands'][0]['id'], normal_quantity='90', spare_quantity='10')
    body = service.s.Command(factory_id='huaxing', action='allocate', operation_id='legacy-allocation', expected_version=0, data=payload)
    with Session(client.engine) as db:
        db.add(Receipt(operation_id=body.operation_id, factory_id='huaxing', actor_id='synthetic-user', action='allocate',
            fingerprint=service.digest(body.model_dump(mode='json')), result=dict(record=prior), changes=[], created_at=service.now_text()))
        db.commit()
    assert command(client, 'allocate', payload, operation_id=body.operation_id) == prior
    command(client, 'allocate', payload, status=422)
    assert len([r for r in workspace(client)['records'] if r['kind'] == 'allocation']) == 1
