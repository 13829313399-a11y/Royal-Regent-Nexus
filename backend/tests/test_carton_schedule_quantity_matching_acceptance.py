"""Independent acceptance of manual no-PO orders through public endpoints."""
from contextlib import contextmanager
from pathlib import Path
import shutil

import pytest

from test_carton_item_schedule import workbook, source_row
from test_carton_procurement_api import _ensure_dickie_customer, _order_payload
import test_molding_sample_api as helper

_TEMPLATE = None


@contextmanager
def isolated_client(monkeypatch, tmp_path):
    global _TEMPLATE
    if _TEMPLATE is None:
        template_dir = tmp_path.parent / 'carton-quantity-template'
        template_dir.mkdir(exist_ok=True)
        monkeypatch.setattr(helper, 'TEST_TMP_DIR', template_dir)
        with helper.make_client(monkeypatch) as client:
            helper.login_as(client, 'admin')
            _ensure_dickie_customer(client)
            from app.db import engine
            _TEMPLATE = Path(engine.url.database)
        engine.dispose()
    test_db = tmp_path / 'isolated.db'
    shutil.copy2(_TEMPLATE, test_db)
    with helper.make_client_with_database(monkeypatch, test_db) as client:
        helper.login_as(client, 'warehouse_keeper')
        yield client


def manual_order(client, **changes):
    payload = _order_payload()
    payload.update(contract_no='0053135', item_no='0040220-1', customer_po='',
                   product_order_quantity=360, customer_due_date='2026-09-17',
                   lines=[{**payload['lines'][0], 'usage_quantity': 6,
                           'quantity_rule': {'mode': 'PACKING'}}])
    payload.update(changes)
    result = client.post('/api/carton-procurement/orders', json=payload)
    assert result.status_code == 201, result.text
    return result.json()


def import_schedule(client, rows, filename='acceptance.xlsx'):
    result = client.post('/api/carton-procurement/weekly-imports',
        params={'factory_id': 'huaxing'}, data={'customer_code': 'DICKIE'},
        files={'file': (filename, workbook(rows))})
    assert result.status_code == 201, result.text
    return result.json()


def row(**changes):
    data = source_row(contract='0053135', item='0040220-1', qty=360)
    indexes = {'po': 3, 'contract': 1, 'item': 5, 'quantity': 7, 'packing': 8}
    for name, value in changes.items():
        data[indexes[name]] = value
    return data


def test_unique_manual_order_matches_import_and_blocks_duplicate(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        batch = import_schedule(client, [row()])
        actual = batch['parse_summary']['rows'][0]
        assert actual['match_status'] == 'MATCHED'
        assert actual['order_id'] == order['id']
        assert actual['match_basis'] == 'CONTRACT_ITEM_QUANTITY_PACKING'
        source = {'batch_id': batch['id'], 'source_sheet': '子弹枪ITEM表', 'source_row': 4}
        payload = _order_payload()
        payload.update(contract_no='0053135', item_no='0040220-1', customer_po='0989551378',
                       product_order_quantity=360, schedule_source=source)
        duplicate = client.post('/api/carton-procurement/orders', json=payload)
        assert duplicate.status_code == 409, duplicate.text
        assert any(word in duplicate.text for word in ('核对', '重复'))
        assert client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['total'] == 1
        saved = client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['items'][0]
        assert not saved.get('customer_po')


@pytest.mark.parametrize('changes', [
    {'contract': '53135'}, {'item': '40220-1'}, {'quantity': 361}, {'packing': 12},
    {'quantity': None}, {'quantity': 0}, {'packing': None}, {'packing': 0},
])
def test_incomplete_or_different_business_facts_never_match(monkeypatch, tmp_path, changes):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        actual = import_schedule(client, [row(**changes)])['parse_summary']['rows'][0]
        assert actual.get('order_id') != order['id']
        assert actual['match_status'] != 'MATCHED'


def test_two_nonempty_conflicting_pos_do_not_fallback(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client, customer_po='OTHER-PO')
        actual = import_schedule(client, [row()])['parse_summary']['rows'][0]
        assert actual.get('order_id') != order['id']
        assert actual['match_status'] != 'MATCHED'


def test_existing_exact_po_matching_remains_available(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client, customer_po='0989551378')
        actual = import_schedule(client, [row()])['parse_summary']['rows'][0]
        assert actual['match_status'] == 'MATCHED'
        assert actual['order_id'] == order['id']


def test_other_customer_is_not_a_fallback_candidate(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        helper.login_as(client, 'admin')
        created = client.post('/api/carton-procurement/customers', json={
            'factory_id': 'huaxing', 'customer_code': 'OTHER', 'customer_name': 'Other'})
        assert created.status_code == 201, created.text
        order = manual_order(client, customer_code='OTHER', customer_name='Other')
        actual = import_schedule(client, [row()])['parse_summary']['rows'][0]
        assert actual.get('order_id') != order['id']
        assert actual['match_status'] != 'MATCHED'


def test_other_factory_is_not_a_fallback_candidate(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        helper.login_as(client, 'admin')
        result = client.post('/api/carton-procurement/customers', json={'factory_id': 'huadeng',
                             'customer_code': 'DICKIE', 'customer_name': 'Dickie'})
        assert result.status_code == 201, result.text
        order = manual_order(client, factory_id='huadeng')
        actual = import_schedule(client, [row()])['parse_summary']['rows'][0]
        assert actual.get('order_id') != order['id']
        assert actual['match_status'] != 'MATCHED'


@pytest.mark.parametrize('side', ['schedule', 'schedule_blank_po', 'orders'])
def test_competing_candidates_remain_ambiguous_and_cannot_create_again(monkeypatch, tmp_path, side):
    with isolated_client(monkeypatch, tmp_path) as client:
        manual_order(client)
        if side == 'orders':
            manual_order(client)
        rows = ([row(), row(po='ANOTHER-PO')] if side == 'schedule' else
                [row(), row(po='')] if side == 'schedule_blank_po' else [row()])
        batch = import_schedule(client, rows)
        # A blank PO is not a wildcard that can consume a purchase competing
        # with another current demand; both sources require review.
        for actual in batch['parse_summary']['rows']:
            assert actual['match_status'] == 'AMBIGUOUS'
            assert not actual.get('order_id')
        payload = _order_payload()
        payload.update(contract_no='0053135', item_no='0040220-1', customer_po='0989551378',
                       product_order_quantity=360, schedule_source={'batch_id': batch['id'],
                       'source_sheet': '子弹枪ITEM表', 'source_row': 4})
        duplicate = client.post('/api/carton-procurement/orders', json=payload)
        assert duplicate.status_code == 409, duplicate.text
        assert any(word in duplicate.text for word in ('核对', '重复'))


def test_manual_override_quantity_is_not_reliable_packing_evidence(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        payload = _order_payload()
        line = {**payload['lines'][0], 'usage_quantity': 6,
                'quantity_rule': {'mode': 'PACKING', 'manual_quantity': 61}}
        order = manual_order(client, lines=[line])
        actual = import_schedule(client, [row()])['parse_summary']['rows'][0]
        assert actual.get('order_id') != order['id']
        assert actual['match_status'] != 'MATCHED'


@pytest.mark.parametrize('packaging_type', ['普通箱', '半翼箱'])
def test_supported_outer_carton_names_match(monkeypatch, tmp_path, packaging_type):
    with isolated_client(monkeypatch, tmp_path) as client:
        payload = _order_payload()
        line = {**payload['lines'][0], 'packaging_type': packaging_type, 'usage_quantity': 6,
                'quantity_rule': {'mode': 'PACKING'}}
        order = manual_order(client, lines=[line])
        actual = import_schedule(client, [row()])['parse_summary']['rows'][0]
        assert actual['match_status'] == 'MATCHED'
        assert actual['order_id'] == order['id']


@pytest.mark.parametrize(('packing', 'cartons', 'should_match'), [
    ('6/12', [('内箱', 6), ('普通箱', 12)], True),
    ('0/12', [('普通箱', 12)], True),
    (12, [('普通箱', 12)], True),
    ('6/12', [('内箱', 6)], False),
    (12, [('普通箱', 12), ('半翼箱', 12)], False),
])
def test_packing_interpretation_requires_unambiguous_carton_lines(monkeypatch, tmp_path, packing, cartons, should_match):
    with isolated_client(monkeypatch, tmp_path) as client:
        template = _order_payload()['lines'][0]
        lines = [{**template, 'packaging_type': kind, 'usage_quantity': count,
                  'quantity_rule': {'mode': 'PACKING'}} for kind, count in cartons]
        order = manual_order(client, lines=lines)
        actual = import_schedule(client, [row(packing=packing)])['parse_summary']['rows'][0]
        if should_match:
            assert actual['match_status'] == 'MATCHED'
            assert actual['order_id'] == order['id']
        else:
            assert actual.get('order_id') != order['id']
            assert actual['match_status'] != 'MATCHED'


def test_legacy_calculated_packing_without_rule_still_matches(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        line = {**_order_payload()['lines'][0], 'packaging_type': '普通箱', 'usage_quantity': 6}
        order = manual_order(client, lines=[line])
        actual = import_schedule(client, [row()])['parse_summary']['rows'][0]
        assert actual['match_status'] == 'MATCHED'
        assert actual['order_id'] == order['id']


def test_explicit_paper_quantity_is_not_a_product_quantity_proof(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        line = {**_order_payload()['lines'][0], 'packaging_type': '普通箱',
                'usage_quantity': 6, 'required_quantity': 60}
        order = manual_order(client, quantity_basis='EXPLICIT', product_order_quantity=None, lines=[line])
        actual = import_schedule(client, [row()])['parse_summary']['rows'][0]
        assert actual.get('order_id') != order['id']
        assert actual['match_status'] != 'MATCHED'


def test_fallback_order_id_does_not_expose_explicit_order_asset():
    from types import SimpleNamespace as S
    from app.services.carton_schedule_marks import project
    order = S(id='order-1', customer_code='DICKIE', contract_no='0053135',
              item_no='0040220-1', customer_po='')
    file = S(id='asset-1', workflow=S(status='READY'), recognition_source='manual_order',
             bound_order_id=order.id, contract_number=order.contract_no,
             orders=[order], file_name='private.png')
    source = {'source_sheet': 'ITEM', 'source_row': 4, 'contract_no': order.contract_no,
              'schedule_customer_code': order.customer_code, 'item_no': order.item_no,
              'customer_po': 'PO-A', 'order_id': order.id,
              'match_basis': 'CONTRACT_ITEM_QUANTITY_PACKING'}
    result, assets = project([source], [source], [order], [file])
    assert result[0]['asset_ids'] == []
    assert assets == []
    # An explicit link still grants exactly the previous order-specific visibility.
    explicit = {**source, 'match_basis': 'SCHEDULE_SOURCE'}
    result, assets = project([explicit], [explicit], [order], [file])
    assert result[0]['asset_ids'] == ['asset-1']
    assert [entry['id'] for entry in assets] == ['asset-1']


def test_fallback_does_not_create_explicit_schedule_asset_provenance(monkeypatch, tmp_path):
    from types import SimpleNamespace as S
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        batch = import_schedule(client, [row()])
        assert batch['parse_summary']['rows'][0]['order_id'] == order['id']
        from app.db import SessionLocal
        from app.services.carton_asset_targets import source_purchase_order_ids, identity
        target = {'kind': 'SCHEDULE', 'id': batch['id'], 'sheet': '子弹枪ITEM表', 'row': 4,
                  'identity': identity({'customer_code': 'DICKIE', 'contract_no': '0053135',
                                        'item_no': '0040220-1', 'customer_po': '0989551378'})}
        with SessionLocal() as db:
            assert source_purchase_order_ids(db, S(factory_id='huaxing'), schedule_target=target) == set()


def test_old_fallback_snapshot_is_rechecked_after_order_quantity_changes(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        batch = import_schedule(client, [row()])
        assert batch['parse_summary']['rows'][0]['order_id'] == order['id']
        payload = _order_payload()
        payload.update(contract_no='0053135', item_no='0040220-1', customer_po='',
                       product_order_quantity=361, customer_due_date='2026-09-17',
                       lines=[{**payload['lines'][0], 'usage_quantity': 6,
                               'quantity_rule': {'mode': 'PACKING'}}],
                       expected_revision=order['revision'], reason='核对产品数量')
        changed = client.patch('/api/carton-procurement/orders/' + order['order_no'], json=payload)
        assert changed.status_code == 200, changed.text
        current = client.get('/api/carton-procurement/imports/' + batch['id'],
                             params={'factory_id': 'huaxing'})
        assert current.status_code == 200, current.text
        reread = current.json()['parse_summary']['rows'][0]
        assert reread.get('order_id') != order['id']
        new = _order_payload()
        new.update(contract_no='0053135', item_no='0040220-1', customer_po='0989551378',
                   product_order_quantity=360, schedule_source={'batch_id': batch['id'],
                   'source_sheet': '子弹枪ITEM表', 'source_row': 4})
        created = client.post('/api/carton-procurement/orders', json=new)
        assert created.status_code == 201, created.text


def test_cancelling_competitor_restores_unique_current_proof(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        remaining = manual_order(client)
        competing = manual_order(client)
        batch = import_schedule(client, [row()])
        source = batch['parse_summary']['rows'][0]
        assert source['match_status'] == 'AMBIGUOUS'
        stopped = client.post('/api/carton-procurement/orders/' + competing['order_no'] + '/cancel',
            json={'factory_id': 'huaxing', 'expected_revision': competing['revision'], 'reason': '重复测试单取消'})
        assert stopped.status_code == 200, stopped.text
        result = client.get('/api/carton-procurement/schedule-orders', params={'factory_id': 'huaxing'})
        assert result.status_code == 200, result.text
        current = next(x for x in result.json()['items'] if x['id'] == remaining['id'])
        proof = next(p for p in current['schedule_quantity_matches'] if p['schedule_identity'] == source['schedule_identity'])
        assert proof['ambiguous'] is False
        workspace = client.get('/api/carton-procurement/dashboard/workspace',
                               params={'factory_id': 'huaxing', 'status': 'ALL'})
        assert workspace.status_code == 200, workspace.text
        alert = next(a for a in workspace.json()['items'] if a['contractNo'] == '0053135')
        assert alert['reminder']['state'] != 'REVIEW'
        assert alert['order']['id'] == remaining['id']


def test_paginated_orders_keep_full_factory_competition(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        first = manual_order(client)
        second = manual_order(client)
        batch = import_schedule(client, [row()])
        source = batch['parse_summary']['rows'][0]
        results = []
        for offset in (0, 1):
            response = client.get('/api/carton-procurement/schedule-orders',
                                  params={'factory_id': 'huaxing', 'offset': offset, 'limit': 1})
            assert response.status_code == 200, response.text
            results.extend(response.json()['items'])
        assert {x['id'] for x in results} == {first['id'], second['id']}
        for order in results:
            proof = next(p for p in order['schedule_quantity_matches'] if p['schedule_identity'] == source['schedule_identity'])
            assert proof['ambiguous'] is True


def test_real_independent_split_parent_and_child_are_not_guessed(monkeypatch, tmp_path):
    from uuid import uuid4
    with isolated_client(monkeypatch, tmp_path) as client:
        original = manual_order(client)
        split = client.post('/api/carton-procurement/orders/' + original['order_no'] + '/independent-splits',
            json={'factory_id': 'huaxing', 'expected_revision': original['revision'],
                  'request_id': uuid4().hex, 'reason': '客户要求分开采购',
                  'targets': [{'contract_no': 'QA-CHILD', 'customer_po': '', 'product_quantity': 120,
                               'due_date': '2026-09-17',
                               'lines': [{'order_line_id': original['lines'][0]['id'], 'quantity': 20}]}]})
        assert split.status_code == 201, split.text
        orders = client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['items']
        assert len(orders) == 2
        batch = import_schedule(client, [row(quantity=240), row(contract='QA-CHILD', quantity=120, po='CHILD-PO')])
        for source in batch['parse_summary']['rows']:
            assert not source.get('order_id')
            assert source['match_status'] != 'MATCHED'


def test_competing_import_then_withdraw_recomputes_existing_proof(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        first = import_schedule(client, [row()], 'first.xlsx')
        identity = first['parse_summary']['rows'][0]['schedule_identity']
        assert first['parse_summary']['rows'][0]['order_id'] == order['id']
        second = import_schedule(client, [row(po='ANOTHER-PO')], 'competing.xlsx')
        def proof():
            response = client.get('/api/carton-procurement/schedule-orders', params={'factory_id': 'huaxing'})
            assert response.status_code == 200, response.text
            item = next(x for x in response.json()['items'] if x['id'] == order['id'])
            return next(x for x in item['schedule_quantity_matches'] if x['schedule_identity'] == identity)
        assert proof()['ambiguous'] is True
        before = client.get('/api/carton-procurement/imports/' + first['id'], params={'factory_id': 'huaxing'}).json()
        assert not before['parse_summary']['rows'][0].get('order_id')
        assert before['parse_summary']['matched_count'] == 0
        assert before['parse_summary']['issue_count'] == 1
        undone = client.post('/api/carton-procurement/imports/' + second['id'] + '/undo',
                             json={'factory_id': 'huaxing', 'reason': '撤回错误竞争排期'})
        assert undone.status_code == 200, undone.text
        assert proof()['ambiguous'] is False
        after = client.get('/api/carton-procurement/imports/' + first['id'], params={'factory_id': 'huaxing'}).json()
        assert after['parse_summary']['rows'][0]['order_id'] == order['id']
        assert after['parse_summary']['matched_count'] == 1
        assert after['parse_summary']['issue_count'] == 0


def test_full_missing_pending_source_still_prevents_other_po_taking_order(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        def scoped(rows, day):
            result = client.post('/api/carton-procurement/weekly-imports', params={'factory_id': 'huaxing'},
                data={'customer_code': 'DICKIE', 'scope_mode': 'FULL', 'as_of_date': day,
                      'coverage_start': '2026-09-01', 'coverage_end': '2026-09-30',
                      'full_scope_confirmed': 'true'}, files={'file': (day + '.xlsx', workbook(rows))})
            assert result.status_code == 201, result.text
            return result.json()
        first = scoped([row()], '2026-10-10')
        next_batch = scoped([row(po='ANOTHER-PO')], '2026-10-11')
        next_source = next_batch['parse_summary']['rows'][0]
        assert next_source.get('order_id') != order['id']
        current = client.get('/api/carton-procurement/schedule-orders', params={'factory_id': 'huaxing'}).json()
        candidate = next(x for x in current['items'] if x['id'] == order['id'])
        relevant = [p for p in candidate['schedule_quantity_matches']
                    if p['schedule_identity'] == next_source['schedule_identity']]
        assert not relevant or all(p['ambiguous'] for p in relevant)
        original = first['parse_summary']['rows'][0]
        payload = _order_payload()
        payload.update(contract_no='0053135', item_no='0040220-1', customer_po='0989551378',
                       product_order_quantity=360, schedule_source={'batch_id': first['id'],
                       'source_sheet': original['source_sheet'], 'source_row': original['source_row']})
        assert client.post('/api/carton-procurement/orders', json=payload).status_code == 409
        from test_carton_schedule_coverage_integrated import missing, review
        helper.login_as(client, 'admin')
        case = missing(client, '0053135')
        review(client, case, 'NO_LONGER_REQUIRED')
        current = client.get('/api/carton-procurement/schedule-orders', params={'factory_id': 'huaxing'}).json()
        candidate = next(x for x in current['items'] if x['id'] == order['id'])
        assert any(p['schedule_identity'] == next_source['schedule_identity'] and not p['ambiguous']
                   for p in candidate['schedule_quantity_matches'])
        assert client.post('/api/carton-procurement/orders', json=payload).status_code == 409


def test_staff_send_and_complete_receipt_preserves_proof_and_real_status(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        batch = import_schedule(client, [row()])
        assert batch['parse_summary']['rows'][0]['procurement_state'] == 'NEEDS_ORDER'
        sent = client.post('/api/carton-procurement/orders/' + order['order_no'] + '/submit-supplier',
                           json={'factory_id': 'huaxing', 'expected_revision': order['revision']})
        assert sent.status_code == 200, sent.text
        assert sent.json()['status'] == 'PENDING_SUPPLIER'
        receipt = client.post('/api/carton-procurement/receipts', json={
            'factory_id': 'huaxing', 'delivery_note_no': 'QA-COMPLETE', 'delivery_date': '2026-09-17',
            'lines': [{'order_line_id': order['lines'][0]['id'], 'delivered_quantity': 60,
                       'received_quantity': 60, 'damaged_quantity': 0, 'rejected_quantity': 0,
                       'unusable_quantity': 0, 'location': '纸箱仓 A-03'}]})
        assert receipt.status_code == 201, receipt.text
        confirmed = client.post('/api/carton-procurement/receipts/' + receipt.json()['id'] + '/confirm',
                                json={'factory_id': 'huaxing', 'expected_revision': receipt.json()['revision']})
        assert confirmed.status_code == 200, confirmed.text
        current = client.get('/api/carton-procurement/schedule-orders', params={'factory_id': 'huaxing'}).json()
        item = next(x for x in current['items'] if x['id'] == order['id'])
        assert item['status'] == 'COMPLETED'
        assert any(not p['ambiguous'] and p['schedule_identity'] == batch['parse_summary']['rows'][0]['schedule_identity']
                   for p in item['schedule_quantity_matches'])
        from app.services.carton_dashboard import reminder
        from datetime import date
        status = reminder(batch['parse_summary']['rows'][0], today=date(2026, 10, 20),
                          lead_days=3, production_days=7, orders=[item])
        assert status['label'] == '已完单'


def test_fallback_snapshot_remains_private_after_manually_adding_equal_po(monkeypatch, tmp_path):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        batch = import_schedule(client, [row()])
        payload = _order_payload()
        payload.update(contract_no='0053135', item_no='0040220-1', customer_po='0989551378',
                       product_order_quantity=360, customer_due_date='2026-09-17',
                       lines=[{**payload['lines'][0], 'usage_quantity': 6, 'quantity_rule': {'mode': 'PACKING'}}],
                       expected_revision=order['revision'], reason='补填已核实客户PO')
        changed = client.patch('/api/carton-procurement/orders/' + order['order_no'], json=payload)
        assert changed.status_code == 200, changed.text
        current = client.get('/api/carton-procurement/imports/' + batch['id'], params={'factory_id': 'huaxing'})
        assert current.status_code == 200, current.text
        source = current.json()['parse_summary']['rows'][0]
        assert source['order_id'] == order['id']
        assert source['match_basis'] == 'CONTRACT_ITEM_QUANTITY_PACKING'
        new = _order_payload()
        new.update(contract_no='0053135', item_no='0040220-1', customer_po='0989551378', product_order_quantity=360,
                   schedule_source={'batch_id': batch['id'], 'source_sheet': '子弹枪ITEM表', 'source_row': 4})
        assert client.post('/api/carton-procurement/orders', json=new).status_code == 409


@pytest.mark.parametrize('change', ['quantity', 'packing', 'cancelled', 'shipped'])
def test_newest_source_replaces_old_proof_without_reactivating_closed_rows(monkeypatch, tmp_path, change):
    with isolated_client(monkeypatch, tmp_path) as client:
        order = manual_order(client)
        first = import_schedule(client, [row()], 'first.xlsx')
        identity = first['parse_summary']['rows'][0]['schedule_identity']
        assert first['parse_summary']['rows'][0]['order_id'] == order['id']
        values = row(quantity=361) if change == 'quantity' else row(packing=12) if change == 'packing' else row()
        if change in ('cancelled', 'shipped'):
            values = [['取消单' if change == 'cancelled' else '已走货订单'], values]
        else:
            values = [values]
        import_schedule(client, values, 'changed.xlsx')
        response = client.get('/api/carton-procurement/schedule-orders', params={'factory_id': 'huaxing'})
        assert response.status_code == 200, response.text
        current = next(x for x in response.json()['items'] if x['id'] == order['id'])
        assert not any(p['schedule_identity'] == identity and not p['ambiguous']
                       for p in current['schedule_quantity_matches'])
