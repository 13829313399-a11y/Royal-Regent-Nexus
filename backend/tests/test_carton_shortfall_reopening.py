"""Append-only shortfall reopens, using disposable per-test databases only."""
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from threading import Barrier
from uuid import uuid4

import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_special_requests import command, ok

BASE = '/api/carton-unified-deliveries'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)


def detail(client, identifier):
    return ok(client.get(BASE + '/' + identifier, params={'factory_id': 'huaxing'}))


def reopen_body(group, quantity='1', *, special=True):
    payload = dict(factory_id='huaxing', request_id=uuid4().hex, reason='原短送关闭操作有误，核实恢复待收', special=[])
    if group['formal']:
        payload['formal'] = dict(expected_revision=group['formal']['revision'], lines=[
            dict(shipment_line_id=line['id'], quantity=quantity) for line in group['formal']['lines']])
    if special:
        payload['special'] = [dict(request_id=row['id'], shipment_id=shipment['id'], expected_revision=row['revision'],
            lines=[dict(shipment_line_id=paper['id'], quantity=quantity) for paper in shipment['lines']])
            for row in group['special'] for shipment in row['shipments']]
    return payload


def reopen(client, group, payload=None):
    return client.post(BASE + '/' + group['id'] + '/reopen-shortfall', json=payload or reopen_body(group))


def stored_evidence():
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonReceipt
    with SessionLocal() as db:
        return dict(audits={row.id: row.detail_json for row in db.scalars(select(CartonAuditEvent))},
            movements=[row.id for row in db.scalars(select(CartonInventoryMovement))],
            receipts=[row.id for row in db.scalars(select(CartonReceipt))])


@pytest.mark.parametrize('reverse_first', [False, True])
def test_formal_partial_reopen_keeps_gross_closure_and_physical_correction_separate(monkeypatch, reverse_first):
    from test_carton_partial_shipment_receiving import begin, payload, post
    from test_carton_supplier_portal import BASE as PORTAL, supplier_login
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        ended = post(client, shipment, payload(client, shipment, 8, mode='CLOSE'))
        login_as(client, 'admin')
        before = stored_evidence()
        identifier = 'FORMAL:' + shipment['id']
        group = detail(client, identifier)
        receipt_id = ended['receipt_id']

        def reverse():
            receipt = ok(client.get('/api/carton-procurement/receipts/' + receipt_id, params={'factory_id': 'huaxing'}))
            ok(client.post('/api/carton-procurement/receipts/' + receipt_id + '/reverse', json=dict(
                factory_id='huaxing', expected_revision=receipt['revision'], reason='核实实际收料更正原批次')))

        if reverse_first:
            reverse(); group = detail(client, identifier)
        body = reopen_body(group)
        opened = ok(reopen(client, group, body))
        assert ok(reopen(client, group, body)) == opened
        changed = dict(body, reason='同请求不能更改原因')
        assert reopen(client, opened, changed).status_code == 409
        after = stored_evidence()
        if not reverse_first:
            assert after['receipts'] == before['receipts'] and after['movements'] == before['movements']
        assert all(after['audits'][key] == value for key, value in before['audits'].items())
        if not reverse_first: reverse()
        current = detail(client, identifier)
        assert all(D(line['closed_quantity']) == 1 and D(line['receivable_quantity']) == 8 for line in current['lines'])
        data = payload(client, current['formal'], 8, '2026-10-02', 'WAIT')
        data['correction_reason'] = '重新核实实际收到八件'
        if reverse_first:
            from app.db import SessionLocal
            from app.models.carton_supplier_settlement import CartonSupplierSettlement
            from app.services.carton_supplier_portal import fixed_supplier
            identifier = 'RECONFIRMED-' + uuid4().hex
            with SessionLocal() as db:
                db.add(CartonSupplierSettlement(id=identifier, factory_id='huaxing', supplier_id=fixed_supplier(db, 'huaxing').id,
                    period='2026-09', currency='CNY', status='CONFIRMED', source_fingerprint='old-confirmed-fixture',
                    sources_json='[]', statement_json='{"origin":"MANUAL","lines":[]}', result_json='{"marker":"original snapshot"}',
                    created_at='2026-11-05', updated_at='2026-11-05', created_by='user-admin'))
                db.commit()
            frozen = stored_evidence()
            blocked = client.post(PORTAL + '/internal/shipments/' + current['formal']['id'] + '/receive', json=data)
            assert blocked.status_code == 409 and '2026-09' in blocked.text, blocked.text
            assert stored_evidence() == frozen
            login_as(client, 'carton_supervisor')
            ok(client.post('/api/carton-procurement/supplier-settlements/' + identifier + '/reopen', json=dict(
                factory_id='huaxing', expected_revision=1, reason='原短送继承证据需要重新核对')))
            login_as(client, 'admin')
        corrected = post(client, current['formal'], data)
        assert all(D(line['received_quantity']) == 8 and D(line['closed_quantity']) == 1 and D(line['remaining_quantity']) == 1 for line in corrected['lines'])
        supplier_login(client)
        supplier_rows = ok(client.get(PORTAL + '/workspace', params={'factory_id': 'huaxing'}))['shipments']
        vendor = next(row for row in supplier_rows if row['id'] == shipment['id'])
        assert all(D(line['received_quantity']) == 8 and D(line['closed_quantity']) == 1 for line in vendor['lines'])
        login_as(client, 'admin')
        assert ok(client.get(PORTAL + '/internal/shipments/pending', params={'factory_id': 'huaxing'}))['total'] == 1
        september = ok(client.get('/api/carton-procurement/supplier-settlements/workspace', params={'factory_id': 'huaxing', 'period': '2026-09'}))
        october = ok(client.get('/api/carton-procurement/supplier-settlements/workspace', params={'factory_id': 'huaxing', 'period': '2026-10'}))
        closed_rows = [row for row in september['collaboration']['unsettled_shipments'] if row['status'] == 'NOT_RECEIVED']
        assert len(closed_rows) == 2 and all(D(row['quantity']) == 1 for row in closed_rows)
        assert september['sources'] == []
        assert len(october['sources']) == 2 and all(D(row['quantity']) == 8 and D(row['amount']) == 16 for row in october['sources'])
        assert len(october['collaboration']['lines']) == 2 and all(D(row['quantity']) == 8 for row in october['collaboration']['lines'])


def test_zero_arrival_mixed_note_reopens_only_selected_papers_and_replays_without_stock(monkeypatch):
    from test_carton_special_requests import setup, created
    from test_carton_supplier_portal import supplier_login, accept_all
    from test_carton_unified_deliveries import EXTERNAL, dispatch_body, receive_body
    with make_client(monkeypatch) as client:
        place = setup(client); request = created(client)
        supplier_login(client); order = accept_all(client)
        group = ok(client.post(EXTERNAL, json=dispatch_body(request, order)), 201)
        login_as(client, 'admin')
        body = receive_body(group, place, '0')
        body['formal']['remaining_action'] = 'CLOSE'
        for line in body['formal']['lines']:
            line.update(received_quantity='0', location_allocations=[], difference_reason='本纸品未到，原单短送关闭')
        body['special'][0].update(remaining_action='CLOSE', close_reason='本纸品原单全部未到')
        body['special'][0]['lines'][0]['location_allocations'] = []
        ended = ok(client.post(BASE + '/' + group['id'] + '/receive', json=body))
        assert not ended['receipts']
        before = stored_evidence()
        selected = reopen_body(ended)
        selected['formal']['lines'] = selected['formal']['lines'][:1]
        selected['special'][0]['lines'][0]['quantity'] = '3'
        opened = ok(reopen(client, ended, selected))
        assert ok(reopen(client, ended, selected)) == opened
        after = stored_evidence()
        assert before['movements'] == after['movements'] and before['receipts'] == after['receipts'] == []
        assert all(after['audits'][key] == value for key, value in before['audits'].items())
        formal = [line for line in opened['lines'] if line['source_kind'] == 'FORMAL']
        special = [line for line in opened['lines'] if line['source_kind'] == 'SPECIAL'][0]
        assert [(D(line['closed_quantity']), D(line['remaining_quantity'])) for line in formal] == [(1, 1), (2, 0)]
        assert D(special['closed_quantity']) == 7 and D(special['remaining_quantity']) == 3 and D(special['received_quantity']) == 0
        read_before = stored_evidence(); detail(client, opened['id']); detail(client, opened['id'])
        assert stored_evidence() == read_before  # GET never backfills closure/reopen evidence.
        stale = dict(selected, request_id=uuid4().hex)
        assert reopen(client, opened, stale).status_code == 409
        supplier_login(client)
        assert reopen(client, opened, selected).status_code == 403  # Permission before replay.
        login_as(client, 'admin')
        wrong = dict(reopen_body(opened), factory_id='huakang-a')
        assert reopen(client, opened, wrong).status_code in {403, 404}
        body = receive_body(opened, place, '3')
        body['formal']['lines'][0].update(received_quantity='1', location_allocations=[dict(location_id=place['id'], quantity='1')])
        body['formal']['lines'][1].update(received_quantity='0', location_allocations=[])
        done = ok(client.post(BASE + '/' + group['id'] + '/receive', json=body))
        assert D(next(line for line in done['lines'] if line['id'] == special['id'])['received_quantity']) == 3
        assert all(D(line['remaining_quantity']) == 0 for line in done['lines'])
        assert ok(client.get('/api/carton-supplier/internal/shipments/pending', params={'factory_id': 'huaxing'}))['total'] == 0


def test_physical_rejected_goods_never_enter_the_shortfall_reopen_pool(monkeypatch):
    from test_carton_partial_shipment_receiving import begin, payload, post
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        body = payload(client, shipment, 10, mode='CLOSE')
        for line in body['lines']:
            line['damaged_quantity'] = 2
            line['location_allocations'][0]['quantity'] = 8
        ended = post(client, shipment, body)
        assert all(D(line['received_quantity']) == 10 and D(line['effective_quantity']) == 8 and D(line['closed_quantity']) == 0 for line in ended['lines'])
        group = detail(client, 'FORMAL:' + shipment['id'])
        before = stored_evidence()
        response = reopen(client, group, reopen_body(group, '2'))
        assert response.status_code == 409 and '真正未到货' in response.text, response.text
        assert stored_evidence() == before


def test_same_revision_concurrent_reopens_have_one_winner_and_no_overallocation(monkeypatch):
    from test_carton_partial_shipment_receiving import begin, payload, post
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        post(client, shipment, payload(client, shipment, 0, mode='CLOSE'))
        group = detail(client, 'FORMAL:' + shipment['id'])
        bodies = [reopen_body(group, '6'), reopen_body(group, '6')]
        barrier = Barrier(2)
        def send(body):
            barrier.wait(timeout=15)
            return reopen(client, group, body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [job.result(timeout=60) for job in [pool.submit(send, body) for body in bodies]]
        assert sorted(response.status_code for response in responses) == [200, 409]
        current = detail(client, group['id'])
        assert all(D(line['closed_quantity']) == 4 and D(line['remaining_quantity']) == 6 for line in current['lines'])
        assert reopen(client, current, reopen_body(current, '5')).status_code == 409
        winner = next(index for index, response in enumerate(responses) if response.status_code == 200)
        assert ok(reopen(client, current, bodies[winner])) == responses[winner].json()
        assert stored_evidence()['receipts'] == [] and stored_evidence()['movements'] == []


def test_incomplete_legacy_acceptance_blocks_repeated_reopens_without_get_backfill(monkeypatch):
    from test_carton_partial_shipment_receiving import begin, payload, post
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        post(client, shipment, payload(client, shipment, 8, mode='CLOSE'))
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        with SessionLocal() as db:
            for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == shipment['id'],
                CartonAuditEvent.event_type == 'SUPPLIER_SHIPMENT_RECEIVED')):
                db.delete(event)  # Disposable fixture reproduces pre-audit legacy shape.
            db.commit()
        before = stored_evidence()
        group = detail(client, 'FORMAL:' + shipment['id'])
        for _ in range(2):
            response = reopen(client, group)
            assert response.status_code == 409 and '缺少完整验收审计' in response.text, response.text
        assert stored_evidence() == before


def test_reopen_b_requires_its_own_agreement_and_exact_remaining_quota(monkeypatch):
    from test_carton_partial_shipment_receiving import begin, payload, post
    from test_carton_supplier_portal import BASE as PORTAL, supplier_login
    from test_carton_replenishment_api import body, replenish
    from test_carton_history_identity_api import _orders
    from test_carton_p1_lifecycle import task_for, respond
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        post(client, shipment, payload(client, shipment, 6, mode='CLOSE'))
        login_as(client, 'admin')
        order = _orders(client)[0]
        stocks = ok(client.get('/api/carton-procurement/inventory/positions', params={'factory_id': 'huaxing'}))
        made = ok(replenish(client, order, body(order, stocks, 'OWN', 2)), 201)
        order, issue = made['order'], made['issue']
        supplier_login(client)
        ok(respond(client, task_for(client, 'REPLENISHMENT', order['id']), 'ACCEPT', promised_date='2026-10-20'))
        def send_b():
            return ok(client.post(PORTAL + '/shipments', json=dict(factory_id='huaxing', request_id=uuid4().hex,
                delivery_note_no='B-REOPEN-' + uuid4().hex[:8], delivery_date='2026-10-01', lines=[dict(
                    order_line_id=order['lines'][0]['id'], issue_id=issue['id'], quantity='2', unit_price='2')])), 201)
        b = send_b()
        login_as(client, 'admin')
        ended = post(client, b, payload(client, b, 0, '2026-10-01', 'CLOSE'))
        group = detail(client, 'FORMAL:' + b['id'])
        supplier_login(client)
        ok(respond(client, task_for(client, 'REPLENISHMENT', order['id']), 'DISPUTE', reason='本补单责任需重新核实'))
        login_as(client, 'admin')
        disputed = reopen(client, group)
        assert disputed.status_code == 409 and '异议' in disputed.text, disputed.text
        supplier_login(client)
        ok(respond(client, task_for(client, 'REPLENISHMENT', order['id']), 'ACCEPT', promised_date='2026-10-20'))
        send_b()  # This B's whole allowance is now reserved on another genuine note.
        ordinary = ok(client.get(PORTAL + '/workspace', params={'factory_id': 'huaxing'}))['orders'][0]
        ordinary_note = client.post(PORTAL + '/shipments', json=dict(factory_id='huaxing', request_id=uuid4().hex,
            delivery_note_no='REG-WITH-B-' + uuid4().hex[:8], delivery_date='2026-10-01', lines=[dict(
                order_line_id=order['lines'][0]['id'], issue_id=ordinary['issue_id'], quantity='1', unit_price='2')]))
        assert ordinary_note.status_code == 201, ordinary_note.text
        login_as(client, 'admin')
        before = stored_evidence()
        exhausted = reopen(client, group)
        assert exhausted.status_code == 409 and '额度' in exhausted.text, exhausted.text
        assert stored_evidence() == before
        assert D(detail(client, group['id'])['lines'][0]['closed_quantity']) == 2


def test_special_reopen_checks_both_original_delivery_and_closure_months(monkeypatch):
    from datetime import datetime
    from test_carton_special_requests import setup, created, SUP, BASE as SPECIAL
    from test_carton_supplier_portal import supplier_login
    from app.services import carton_procurement as core
    with make_client(monkeypatch) as client:
        setup(client); row = created(client)
        monkeypatch.setattr(core, 'business_now', lambda: datetime(2026, 11, 5, 12))
        supplier_login(client)
        shipped = ok(client.post(SUP + '/' + row['id'] + '/ship', json=command(row,
            version_id=row['current_version_id'], delivery_note_no='CROSS-CLOSE-' + uuid4().hex[:8], delivery_date='2026-09-30',
            lines=[dict(line_id=row['lines'][0]['id'], quantity='10', unit_price='2')])))
        login_as(client, 'admin')
        shipment = shipped['shipments'][0]
        ended = ok(client.post(SPECIAL + '/' + row['id'] + '/shipments/' + shipment['id'] + '/receive', json=command(shipped,
            acceptance_date='2026-10-01', remaining_action='CLOSE', close_reason='原送货未到本单先关闭',
            lines=[dict(shipment_line_id=shipment['lines'][0]['id'], received_quantity='0')])))
        from app.db import SessionLocal
        from app.models.carton_supplier_settlement import CartonSupplierSettlement
        from app.services.carton_supplier_portal import fixed_supplier
        with SessionLocal() as db:
            for period in ['2026-09', '2026-10']:
                db.add(CartonSupplierSettlement(id='TEST-' + period, factory_id='huaxing', supplier_id=fixed_supplier(db, 'huaxing').id,
                    period=period, currency='CNY', status='CONFIRMED', source_fingerprint='fixture',
                    created_at='2026-11-05', updated_at='2026-11-05', created_by='user-admin'))
            db.commit()
        group = detail(client, 'SPECIAL:' + shipment['id'])
        for period in ['2026-09', '2026-10']:
            before = stored_evidence()
            response = reopen(client, group)
            assert response.status_code == 409 and period in response.text, response.text
            assert stored_evidence() == before
            with SessionLocal() as db:
                db.get(CartonSupplierSettlement, 'TEST-' + period).status = 'SUPERSEDED'  # Isolated guard fixture, not a production correction.
                db.commit()
        opened = ok(reopen(client, group))
        assert D(opened['lines'][0]['closed_quantity']) == 9 and D(opened['lines'][0]['remaining_quantity']) == 1
