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
    with make_client(monkeypatch) as client:
        prepare(client)
        blank = upload(client, 'blank-po.xlsx', [demand(po='')])
        order, _ = create(client, blank)
        assert order['customer_po'] == ''
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonAuditEvent
        from sqlalchemy import select
        with SessionLocal() as db:
            db.get(CartonOrder, order['id']).customer_po = 'RL-452547-8'
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'SCHEDULE_ORDER_LINKED'))
            data = json.loads(event.detail_json)
            data.pop('po_semantics'); data.pop('customer_po')
            event.detail_json = json.dumps(data)
            db.commit()
        key = blank['parse_summary']['rows'][0]['schedule_identity']
        assert marks(client)[key]['matching_order_ids'] == [order['id']]
