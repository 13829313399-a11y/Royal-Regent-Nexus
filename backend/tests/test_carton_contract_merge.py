from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import pytest
from sqlalchemy import select, func
from fastapi import HTTPException
from test_molding_sample_api import make_client
from test_carton_master_api import prepare
from test_carton_procurement_api import _order_payload, _submit_order

BASE = '/api/carton-procurement'


def setup_orders(client, count=3):
    prepare(client)
    result = []
    for i in range(count):
        response = client.post(BASE + '/orders', json={**_order_payload(), 'customer_code': 'dickie',
            'contract_no': f'SC70014536{i}', 'customer_po': f'PO-{i}', 'item_no': f'20330204{i}'})
        assert response.status_code == 201, response.text
        result.append(response.json())
    return result


def request_for(orders):
    return {'factory_id': 'huaxing', 'request_id': uuid4().hex, 'contract_no': 'SC700145399',
        'expected_revisions': {o['order_no']: o['revision'] for o in orders}, 'reason': '客户要求归入新合同'}


def read_orders(client):
    return client.get(BASE + '/orders', params={'factory_id': 'huaxing'}).json()['items']


def test_merge_preserves_all_demand_and_sources_and_replays_without_duplicates(monkeypatch):
    with make_client(monkeypatch) as client:
        original = setup_orders(client)
        body = request_for(original)
        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = list(pool.map(lambda _: client.post(BASE + '/orders/merge-contract', json=body), range(2)))
        response = attempts[0]
        assert response.status_code == 200, response.text
        assert attempts[1].status_code == 200, attempts[1].text
        assert attempts[1].json() == response.json()
        results = response.json()
        assert len(results) == 3
        for before in original:
            after = next(o for o in results if o['id'] == before['id'])
            assert after['contract_no'] == body['contract_no']
            assert after['revision'] == before['revision'] + 1
            for key in ['order_no', 'status', 'customer_po', 'item_no', 'product_order_quantity', 'due_date', 'order_date', 'supplier_id', 'quantity_basis', 'note']:
                assert after[key] == before[key]
            for old, new in zip(before['lines'], after['lines']):
                assert new == old  # Line API omits redundant contract_no; check stored rows below.
        assert client.post(BASE + '/orders/merge-contract', json=body).json() == results
        changed = deepcopy(body); changed['contract_no'] = 'SC700145398'
        assert client.post(BASE + '/orders/merge-contract', json=changed).status_code == 409
        assert len(read_orders(client)) == 3
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord, CartonMasterSource
        from app.models.carton_procurement import CartonAuditEvent, CartonPurchaseOrderIssue, CartonOrderLine
        with SessionLocal() as db:
            assert all(line.contract_no == body['contract_no'] for line in db.scalars(select(CartonOrderLine)))
            contracts = list(db.scalars(select(CartonMasterRecord).where(CartonMasterRecord.kind == 'CONTRACT')))
            assert len(contracts) == 1
            assert json.loads(contracts[0].data_json)['item_nos'] == sorted(o['item_no'] for o in original)
            sources = list(db.scalars(select(CartonMasterSource)))
            assert {json.loads(s.snapshot_json)['original_contract_no'] for s in sources} == {o['contract_no'] for o in original}
            assert db.scalar(select(func.count(CartonPurchaseOrderIssue.id))) == 0
            events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'ORDER_CONTRACT_MERGED')))
            assert len(events) == 3
        assert client.get(BASE + '/inventory/movements', params={'factory_id': 'huaxing'}).json()['total'] == 0
        # The merged demand still follows the original confirmation/supplier workflow.
        issued = _submit_order(client, results[0])
        assert issued['contract_no'] == body['contract_no']
        assert issued['lines'] == results[0]['lines']
        from app.models.carton_procurement import CartonOrder
        with SessionLocal() as db:
            db.get(CartonOrder, results[1]['id']).deleted_at = '2026-10-15T10:00:00+08:00'
            db.commit()
        replay = client.post(BASE + '/orders/merge-contract', json=body)
        assert replay.status_code == 409
        assert '原合单请求已完成' in replay.json()['detail']


@pytest.mark.parametrize('failure', ['stale', 'issued', 'other_customer', 'other_supplier', 'factory', 'existing_contract', 'duplicate_po_item', 'after_first_write'])
def test_merge_rejects_invalid_group_without_partial_changes(monkeypatch, failure):
    with make_client(monkeypatch) as client:
        original = setup_orders(client)
        body = request_for(original)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonAuditEvent
        from app.models.carton_master import CartonMasterRecord
        if failure == 'stale': body['expected_revisions'][original[-1]['order_no']] += 1
        elif failure == 'issued': _submit_order(client, original[-1])
        elif failure == 'factory': body['factory_id'] = 'huakang-a'
        elif failure == 'existing_contract': body['contract_no'] = original[-1]['contract_no']
        elif failure in {'other_customer', 'other_supplier', 'duplicate_po_item'}:
            with SessionLocal() as db:
                row = db.get(CartonOrder, original[-1]['id'])
                if failure == 'other_customer': row.customer_code = 'OTHER'
                elif failure == 'other_supplier': row.supplier_id = 'OTHER'
                else: row.customer_po = original[0]['customer_po']; row.item_no = original[0]['item_no']
                db.commit()
        else:
            from app.services import carton_procurement as core
            audit = core._audit
            def fail_after_first_write(*args, **kwargs):
                if args[3] == 'ORDER_CONTRACT_MERGED': raise HTTPException(409, '模拟写入中断')
                return audit(*args, **kwargs)
            monkeypatch.setattr(core, '_audit', fail_after_first_write)
        before = read_orders(client)
        response = client.post(BASE + '/orders/merge-contract', json=body)
        assert response.status_code in {403, 404, 409, 422}, response.text
        assert read_orders(client) == before
        with SessionLocal() as db:
            assert not db.scalar(select(CartonMasterRecord.id).where(CartonMasterRecord.code == 'SC700145399'))
            assert not db.scalar(select(CartonAuditEvent.id).where(CartonAuditEvent.event_type == 'ORDER_CONTRACT_MERGED'))


def test_fresh_customer_authorization_is_checked_for_every_order_and_replay(monkeypatch):
    with make_client(monkeypatch) as client:
        original = setup_orders(client)
        body = request_for(original)
        from app.services import carton_contract_merge as service
        def deny(*args, **kwargs): raise HTTPException(403, '客户操作权已撤销')
        from app.api import carton_procurement as api
        with monkeypatch.context() as patch:
            patch.setattr(api, 'get_current_user', deny)
            assert client.post(BASE + '/orders/merge-contract', json=body).status_code == 403
        with monkeypatch.context() as patch:
            patch.setattr(service, 'ensure_customer_operation', deny)
            assert client.post(BASE + '/orders/merge-contract', json=body).status_code == 403
        assert {o['contract_no'] for o in read_orders(client)} == {o['contract_no'] for o in original}
        assert client.post(BASE + '/orders/merge-contract', json=body).status_code == 200
        monkeypatch.setattr(service, 'ensure_customer_operation', deny)
        assert client.post(BASE + '/orders/merge-contract', json=body).status_code == 403


def test_blank_po_keeps_legacy_same_item_orders_distinct(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        original = []
        for i in range(2):
            response = client.post(BASE + '/orders', json={**_order_payload(), 'customer_code': 'dickie',
                'contract_no': f'SC70014536{i}', 'customer_po': ''})
            assert response.status_code == 201, response.text
            original.append(response.json())
        merged = client.post(BASE + '/orders/merge-contract', json=request_for(original))
        assert merged.status_code == 200, merged.text
        assert {o['id'] for o in merged.json()} == {o['id'] for o in original}
        assert all(o['customer_po'] == '' for o in merged.json())
