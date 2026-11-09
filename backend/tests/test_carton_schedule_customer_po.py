"""Source P/O# is purchase data; SO remains the stable schedule identity."""
import json
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client
from test_carton_master_api import prepare
from test_carton_schedule_coverage_integrated import upload, row, source, order_body

BASE = '/api/carton-procurement'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    monkeypatch.setenv('COLLABORATION_ENABLED', 'false')


def demand(contract='RL-452547-8', so=None, po='0004685'):
    values = row(contract, quantity=104, due='2026-12-08')
    values[2] = contract if so is None else so
    values[3] = po
    values[5] = '1423020051'
    return values


def marks(client):
    response = client.get(BASE + '/schedule-order-marks', params={'factory_id': 'huaxing'})
    assert response.status_code == 200, response.text
    return response.json()


def create(client, batch, *, index=0):
    value = batch['parse_summary']['rows'][index]
    body = order_body(batch, value['contract_no'])
    body.update(customer_po=value['customer_po'], schedule_source=dict(batch_id=batch['id'],
        source_sheet=value['source_sheet'], source_row=value['source_row']))
    response = client.post(BASE + '/orders', json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_actual_source_po_and_explicit_link_survive_refresh(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        batch = upload(client, 'actual-po.xlsx', [demand()])
        body = order_body(batch, 'RL-452547-8')
        wrong = {**body, 'customer_po': 'RL-452547-8'}
        assert client.post(BASE + '/orders', json=wrong).status_code == 422
        order, body = create(client, batch)
        assert order['customer_po'] == '0004685'
        key = batch['parse_summary']['rows'][0]['schedule_identity']
        state = marks(client)[key]
        assert state['order_ids'] == state['matching_order_ids'] == [order['id']]
        assert not state['ambiguous_order_ids']
        assert client.post(BASE + '/orders', json={**body, 'request_id': uuid4().hex}).status_code == 409


def test_shared_po_keeps_distinct_so_orders_and_reimport_links(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        values = [demand(so='SO-A'), demand(so='SO-B')]
        batch = upload(client, 'shared-po.xlsx', values)
        first, _ = create(client, batch)
        second_key = batch['parse_summary']['rows'][1]['schedule_identity']
        assert marks(client)[second_key]['matching_order_ids'] == []
        second, _ = create(client, batch, index=1)
        values[0][10] = '2026-12-09'
        newer = upload(client, 'shared-po-new.xlsx', values)
        assert [r.get('order_id') for r in newer['parse_summary']['rows']] == [first['id'], second['id']]
        assert all(o['customer_po'] == '0004685' for o in (first, second))


def test_manual_shared_po_is_ambiguous_and_blocks_duplicate_creation(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        from test_carton_procurement_api import _order_payload
        body = {**_order_payload(), 'contract_no': 'RL-452547-8', 'item_no': '1423020051',
                'customer_po': '0004685', 'product_order_quantity': 104}
        order = client.post(BASE + '/orders', json=body)
        assert order.status_code == 201, order.text
        batch = upload(client, 'ambiguous-po.xlsx', [demand(so='SO-A'), demand(so='SO-B')])
        for value in batch['parse_summary']['rows']:
            state = marks(client)[value['schedule_identity']]
            assert state['matching_order_ids'] == []
            assert state['ambiguous_order_ids'] == [order.json()['id']]
        assert client.post(BASE + '/orders', json=order_body(batch, 'RL-452547-8')).status_code == 409


def test_po_change_invalidates_old_source_even_when_so_demand_is_unchanged(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        old = upload(client, 'old-po.xlsx', [demand()])
        upload(client, 'new-po.xlsx', [demand(po='0004686')])
        response = client.post(BASE + '/orders', json=order_body(old, 'RL-452547-8'))
        assert response.status_code == 409, response.text
        assert 'PO' in response.text


def test_blank_source_po_stays_blank_and_legacy_so_links_remain_readable(monkeypatch):
    from test_carton_asset_quick import enable, ok, upload as upload_asset

    with make_client(monkeypatch) as client:
        prepare(client)
        enable(monkeypatch)
        blank = upload(client, 'blank-po.xlsx', [demand(po='')])
        asset = ok(upload_asset(client, contract_number='RL-452547-8', target_scope='PENDING_SCHEDULE'))
        order, _ = create(client, blank)
        assert order['customer_po'] == ''
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from app.models.carton_procurement import CartonOrder, CartonAuditEvent
        from app.services.carton_asset_targets import source_purchase_order_ids
        from sqlalchemy import select
        with SessionLocal() as db:
            assert source_purchase_order_ids(db, db.get(CartonMarkAsset, asset['id'])) == {order['id']}
            db.get(CartonOrder, order['id']).customer_po = 'RL-452547-8'
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'SCHEDULE_ORDER_LINKED'))
            data = json.loads(event.detail_json)
            data.pop('po_semantics'); data.pop('customer_po')
            event.detail_json = json.dumps(data)
            db.commit()
        key = blank['parse_summary']['rows'][0]['schedule_identity']
        assert marks(client)[key]['matching_order_ids'] == [order['id']]
        upload(client, 'blank-po-removed.xlsx', [demand(contract='UNRELATED')])
        with SessionLocal() as db:
            assert source_purchase_order_ids(db, db.get(CartonMarkAsset, asset['id'])) == {order['id']}


def test_schedule_material_follows_its_purchase_after_source_row_is_removed(monkeypatch):
    from test_carton_asset_quick import BASE as ASSETS, F, enable, ok, upload as upload_asset
    from test_carton_procurement_api import _submit_order
    from test_carton_supplier_portal import setup_portal, supplier_login
    from test_molding_sample_api import login_as

    with make_client(monkeypatch) as client:
        unrelated = setup_portal(client)
        login_as(client, 'admin')
        enable(monkeypatch)
        first, second = demand(so='SO-A'), demand(so='SO-B')
        marked = demand(contract='MANUAL-MARK', so='', po='0004720')
        original = upload(client, 'schedule-original.xlsx', [demand(contract='LEADING'), first, second, marked])
        rows = original['parse_summary']['rows']
        candidates = ok(client.get(ASSETS + '/candidates', params={
            **F, 'owner_department': 'sales-business', 'target_scope': 'PENDING_SCHEDULE',
            'contract_number': first[1],
        }))['items']
        first_target = next(target for target in candidates if target['row'] == rows[1]['source_row'])
        ref = {field: first_target[field] for field in ('kind', 'id', 'sheet', 'row', 'fingerprint')}
        asset = ok(upload_asset(client, contract_number=first[1], target_scope='PENDING_SCHEDULE',
                                association='MANUAL', targets=[ref]))
        first_order, first_body = create(client, original, index=1)
        second_order, _ = create(client, original, index=2)
        first_order = _submit_order(client, first_order)
        assert client.post(BASE + '/schedule-order-marks', json={
            **F, **source(original, marked[1]), 'marked': True, 'reason': '已按原采购记录核对',
        }).status_code == 200

        shifted = upload(client, 'schedule-shifted.xlsx', [first, second, marked])
        shifted_rows = shifted['parse_summary']['rows']
        assert shifted_rows[0]['source_row'] != rows[1]['source_row']
        assert [row.get('order_id') for row in shifted_rows[:2]] == [first_order['id'], second_order['id']]
        assert marks(client)[shifted_rows[2]['schedule_identity']]['marked']
        assert client.post(BASE + '/orders', json={**first_body, 'request_id': uuid4().hex,
            'schedule_source': source(shifted, first[1]),
        }).status_code == 409
        detail_url = ASSETS + '/' + asset['id']
        assert [target['id'] for target in ok(client.get(detail_url, params=F))['targets']] == [shifted['id']]

        changed_po = demand(so='SO-A', po='0009999')
        upload(client, 'schedule-po-changed.xlsx', [changed_po, second, marked])
        assert [target['id'] for target in ok(client.get(detail_url, params=F))['targets']] == [original['id']]

        latest = upload(client, 'schedule-removed.xlsx', [second, marked])
        assert latest['parse_summary']['rows'][0]['order_id'] == second_order['id']
        assert marks(client)[rows[1]['schedule_identity']]['order_ids'] == [first_order['id']]
        ledger = ok(client.get(BASE + '/orders', params=F))['items']
        assert {order['id'] for order in ledger} == {first_order['id'], second_order['id'], unrelated['id']}
        assert next(order for order in ledger if order['id'] == first_order['id'])['status'] == 'PENDING_SUPPLIER'

        detail = ok(client.get(detail_url, params=F))
        assert [(target['kind'], target['id'], target['row']) for target in detail['targets']] == [
            ('SCHEDULE', original['id'], rows[1]['source_row']),
        ]
        supplier_login(client)
        supplier_view = {**F, 'supplier_view': True}
        detail = ok(client.get(detail_url, params=supplier_view))
        assert [(target['kind'], target['id']) for target in detail['targets']] == [('REGULAR', first_order['id'])]
        assert client.get(ASSETS + '/' + asset['id'] + '/document', params=supplier_view).content == b'synthetic text'


@pytest.mark.parametrize('second_kind', ['正单', '备料单'])
def test_duplicate_schedule_material_does_not_move_to_a_later_singleton(monkeypatch, second_kind):
    from test_carton_asset_quick import BASE as ASSETS, F, enable, ok, upload as upload_asset

    with make_client(monkeypatch) as client:
        prepare(client)
        enable(monkeypatch)
        first = demand()
        sibling = [second_kind, *first[1:]]
        upload(client, 'schedule-unique-before-duplicates.xlsx', [first])
        earlier = ok(upload_asset(client, contract_number=first[1], target_scope='PENDING_SCHEDULE', text='earlier source'))
        original = upload(client, 'schedule-duplicates.xlsx', [first, sibling])
        candidates = ok(client.get(ASSETS + '/candidates', params={
            **F, 'owner_department': 'sales-business', 'target_scope': 'PENDING_SCHEDULE',
            'contract_number': first[1],
        }))['items']
        second_target = max(candidates, key=lambda row: row['row'])
        ref = {field: second_target[field] for field in ('kind', 'id', 'sheet', 'row', 'fingerprint')}
        asset = ok(upload_asset(client, contract_number=first[1], target_scope='PENDING_SCHEDULE',
                                association='MANUAL', targets=[ref]))
        assert asset['targets'][0]['row'] == original['parse_summary']['rows'][1]['source_row']
        create(client, original)
        assert ok(client.get(ASSETS + '/' + earlier['id'], params=F))['targets'] == []
        upload(client, 'schedule-singleton.xlsx', [first])
        detail = ok(client.get(ASSETS + '/' + asset['id'], params=F))
        assert detail['targets'] == []
        assert client.get(ASSETS + '/' + asset['id'] + '/document', params=F).content == b'synthetic text'
