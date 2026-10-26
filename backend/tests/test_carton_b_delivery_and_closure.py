"""B sources and short-close evidence use disposable SQLite only."""
import json
from decimal import Decimal as D
from io import BytesIO
from uuid import uuid4
import pytest
from openpyxl import Workbook
from test_molding_sample_api import make_client, login_as


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def test_pre_close_controls_receipt_retry_identity_is_preserved_and_explicit_close_is_bound():
    import hashlib
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.schemas.carton_special_requests import Receive
    from app.services import carton_special_requests as service
    payload = Receive(factory_id='huaxing', request_id='legacy-close-request', expected_revision=2, acceptance_date='2026-10-18',
        lines=[dict(shipment_line_id='S1', received_quantity='1', location_allocations=[dict(location_id='B1', quantity='1')])])
    old = payload.model_dump(mode='json'); old.pop('remaining_action'); old.pop('close_reason')
    old['lines'][0].pop('close_remaining')
    digest = hashlib.sha256(service.pack(dict(action='RECEIVE', id='R1', payload=old, extra='SHIP1')).encode()).hexdigest()
    db = SimpleNamespace(scalar=lambda statement: SimpleNamespace(detail_json=service.pack(dict(fingerprint=digest, response=dict(id='saved')))))
    user = SimpleNamespace(id='U1')
    assert service.replay(db, user, payload, 'RECEIVE', 'R1', 'SHIP1')[1] == dict(id='saved')
    changed = payload.model_dump(); changed['lines'][0]['close_remaining'] = True
    changed['close_reason'] = '本纸品余货不再送'
    with pytest.raises(HTTPException): service.replay(db, user, Receive(**changed), 'RECEIVE', 'R1', 'SHIP1')


def test_b_sources_original_excel_independent_commitments_capacity_and_responsibility(monkeypatch):
    from test_carton_partial_shipment_receiving import begin, payload, post
    from test_carton_supplier_portal import BASE, supplier_login, receive_payload
    from test_carton_replenishment_api import body, replenish
    from test_carton_history_identity_api import _orders
    with make_client(monkeypatch) as client:
        original, shipment = begin(client, monkeypatch)
        post(client, shipment, payload(client, shipment, 6, "2026-09-30", "CLOSE"))
        login_as(client, "admin")
        order = _orders(client)[0]
        stocks = client.get('/api/carton-procurement/inventory/positions', params={'factory_id': 'huaxing'}).json()
        own = replenish(client, order, body(order, stocks, "OWN", 1))
        assert own.status_code == 201, own.text
        order = own.json()["order"]
        free = replenish(client, order, body(order, stocks, "SUPPLIER", 2))
        assert free.status_code == 201, free.text
        order = free.json()['order']
        overflow = dict(factory_id='huaxing', request_id=uuid4().hex, delivery_note_no='B-OVER-' + uuid4().hex[:8],
            delivery_date='2026-10-01', acceptance_date='2026-10-01', order_revisions={order['order_no']: order['revision']},
            formal_lines=[dict(order_line_id=order['lines'][0]['id'], replenishment_issue_id=free.json()['issue']['id'],
                delivered_quantity=4, received_quantity=2, unit_price=None, location_allocations=[dict(
                    location_id=next(item['location_id'] for item in stocks if item['order_line_id'] == order['lines'][0]['id']), quantity=2)])])
        rejected = client.post('/api/carton-unified-deliveries/warehouse-receive', json=overflow)
        assert rejected.status_code == 409 and '补单版本的可送额度' in rejected.text, rejected.text
        supplier_login(client)
        workspace = client.get(BASE + '/workspace', params={'factory_id': 'huaxing'}).json()
        row = workspace['orders'][0]
        assert D(row['lines'][0]['remaining_to_ship']) == D(original['lines'][0]['required_quantity']) - 6
        assert row['lines'][0]['accepted']  # B cannot overwrite the ordinary commitment.
        for source in row['replenishment_sources']:
            accepted = client.put(BASE + '/commitments/batch', json={'factory_id': 'huaxing', 'lines': [
                {'order_line_id': paper['id'], 'issue_id': source['issue_id'], 'expected_revision': 0, 'promised_date': '2026-10-20'} for paper in source['lines']]})
            assert accepted.status_code == 200, accepted.text
            stale = client.put(BASE + '/commitments/batch', json={'factory_id': 'huaxing', 'lines': [
                {'order_line_id': paper['id'], 'issue_id': source['issue_id'], 'expected_revision': 0, 'promised_date': '2026-10-21'} for paper in source['lines']]})
            assert stale.status_code == 409
        for source, price in [(own.json()['issue'], 3), (free.json()['issue'], 0)]:
            source_id = source['id']
            book = Workbook(); sheet = book.active; sheet.title = '送货明细'
            sheet.append(['送货单号', '日期', '客户', '客户单号', '客户料号', '纸质', '规格', '数量', '单价'])
            note = 'B-EXCEL-' + uuid4().hex[:8]
            paper = row['lines'][0]
            sheet.append([note, '2026-10-01', '华兴', row['contract_no'], row['item_no'], paper['paper_quality'], paper['specification'], 1 if price else 2, price])
            if price:
                other = row['lines'][1]
                sheet.append([note, '2026-10-01', '华兴', row['contract_no'], row['item_no'], other['paper_quality'], other['specification'], 2, 2])
            output = BytesIO(); book.save(output); upload = {'file': ('original.xlsx', output.getvalue())}
            preview = client.post(BASE + '/shipments/import-preview', files=upload)
            assert preview.status_code == 200, preview.text
            group = preview.json()['groups'][0]
            first = group['rows'][0]
            choice = next(item for item in first['candidates'] if item['issue_id'] == source_id)
            selections = [dict(source_sheet=first['source_sheet'], source_row=first['source_row'],
                order_line_id=choice['order_line_id'], issue_id=source_id, order_revision=choice['order_revision'])]
            preview = client.post(BASE + '/shipments/import-preview', files=upload, data={'row_selections': json.dumps(selections)})
            assert preview.status_code == 200 and preview.json()['groups'][0]['ready'], preview.text
            data = {'sha256': preview.json()['sha256'], 'selections': json.dumps([{'factory_id': 'huaxing', 'delivery_note_no': note}]), 'row_selections': json.dumps(selections)}
            sent = client.post(BASE + '/shipments/import-confirm', files=upload, data=data)
            assert sent.status_code == 200, sent.text
            shipped = sent.json()['shipments'][0]
            assert client.post(BASE + '/shipments/import-confirm', files=upload, data=data).json()['shipments'][0]['id'] == shipped['id']
            excess = client.post(BASE + '/shipments', json=dict(factory_id='huaxing', request_id=uuid4().hex,
                delivery_note_no='EXCESS-' + uuid4().hex[:8], delivery_date='2026-10-01',
                lines=[dict(order_line_id=row['lines'][0]['id'], issue_id=source_id, quantity=1, unit_price=price, free_confirmed=not price)]))
            assert excess.status_code == 409, excess.text
            login_as(client, 'warehouse_keeper')
            receipt = receive_payload(client, shipped); receipt['acceptance_date'] = '2026-10-01'
            for line, saved in zip(receipt['lines'], shipped['lines']):
                qty = float(saved['quantity']); unit_price = price if saved.get('replenishment_issue_id') else 2
                line.update(received_quantity=qty, unit_price=unit_price, location_allocations=[dict(line['location_allocations'][0], quantity=qty)])
                if unit_price == 0: line.update(price_action='FREE', zero_price_kind='FREE')
            forged = json.loads(json.dumps(receipt))
            forged['request_id'] = uuid4().hex
            forged['lines'][0]['replenishment_issue_id'] = free.json()['issue']['id'] if price else own.json()['issue']['id']
            assert client.post(BASE + f"/internal/shipments/{shipped['id']}/receive", json=forged).status_code == 409
            received = post(client, shipped, receipt)
            login_as(client, 'admin')
            physical = client.get('/api/carton-procurement/receipts/' + received['receipt_id'], params={'factory_id': 'huaxing'})
            assert physical.status_code == 200, physical.text
            linked = next(line for line in physical.json()['lines'] if line['replenishment_issue_id'] == source_id)
            assert linked['responsibility'] == ('OWN' if price else 'SUPPLIER')
            monthly = client.get('/api/carton-procurement/supplier-settlements/workspace', params={'factory_id': 'huaxing', 'period': '2026-10'}).json()
            payable = [item for item in monthly['sources'] if item['source_key'] == 'RECEIPT:' + linked['id']]
            assert len(payable) == (1 if price else 0)
            if price: assert D(payable[0]['amount']) == 3
            supplier_login(client)
        from test_carton_settlement_collaboration import save, review
        from test_carton_supplier_settlement_api import action
        login_as(client, 'admin')
        monthly = client.get('/api/carton-procurement/supplier-settlements/workspace', params={'factory_id': 'huaxing', 'period': '2026-10'}).json()
        assert any('供应商责任补单' in item['reason'] and '不计应结' in item['reason'] for item in monthly['collaboration']['unsettled_shipments'])
        document = save(client, monthly)
        assert document['result']['issues'] == []
        supplier_login(client)
        approved = review(client, document)
        assert approved.status_code == 200, approved.text
        login_as(client, 'admin')
        closed = action(client, approved.json())
        assert closed.status_code == 200, closed.text
        assert D(closed.json()['result']['net_amount']) == 7  # OWN B=3, normal other paper=4, SUPPLIER B=0.


def test_special_short_close_zero_arrival_and_receipt_reversal_preserve_real_quantities(monkeypatch):
    from test_carton_special_requests import BASE, SUP, setup, created, command, ok, ship, receive_body
    from test_carton_supplier_portal import supplier_login
    with make_client(monkeypatch) as client:
        place = setup(client); row = created(client)
        supplier_login(client)
        row = ok(client.get(SUP + '/' + row['id'], params={'factory_id': 'huaxing'}))
        row = ship(client, row, quantity='10', price='2')
        login_as(client, 'admin')
        data = receive_body(row, place, '8'); data.update(remaining_action='CLOSE', close_reason='供应商确认余货不再送')
        url = BASE + f"/{row['id']}/shipments/{row['shipments'][0]['id']}/receive"
        done = ok(client.post(url, json=data))
        assert ok(client.post(url, json=data)) == done
        line = done['shipments'][0]['lines'][0]
        assert D(line['gross_received_quantity']) == 8 and D(line['closed_quantity']) == 2 and D(line['remaining_quantity']) == 0
        assert client.get('/api/carton-supplier/internal/shipments/pending', params={'factory_id': 'huaxing'}).json()['total'] == 0
        assert D(done['lines'][0]['quantity']) == 100  # No demand reduction.
        receipt = done['shipments'][0]['receipts'][0]
        reverse = client.post('/api/carton-procurement/receipts/' + receipt['id'] + '/reverse', json=dict(factory_id='huaxing', expected_revision=receipt['revision'], reason='核对实际收料重新登记'))
        assert reverse.status_code == 200, reverse.text
        current = ok(client.get(BASE + '/' + row['id'], params={'factory_id': 'huaxing'}))
        line = current['shipments'][0]['lines'][0]
        assert D(line['remaining_quantity']) == 8 and D(line['closed_quantity']) == 2 and D(line['gross_received_quantity']) == 0
        assert client.get('/api/carton-supplier/internal/shipments/pending', params={'factory_id': 'huaxing'}).json()['total'] == 1
        data = receive_body(current, place, '8')
        corrected = ok(client.post(url, json=data))
        assert D(corrected['shipments'][0]['lines'][0]['gross_received_quantity']) == 8
        row = ship(client, corrected, quantity='2', price='2')
        login_as(client, 'admin')
        shipment = next(item for item in row['shipments'] if not item['receipts'])
        data = command(row, acceptance_date='2026-10-18', remaining_action='CLOSE', close_reason='本张送货全未到且不再送',
            lines=[dict(shipment_line_id=shipment['lines'][0]['id'], received_quantity='0')])
        result = ok(client.post(BASE + f"/{row['id']}/shipments/{shipment['id']}/receive", json=data))
        target = next(item for item in result['shipments'] if item['id'] == shipment['id'])
        assert target['receipts'] == [] and D(target['lines'][0]['gross_received_quantity']) == 0 and D(target['lines'][0]['closed_quantity']) == 2
        assert client.get('/api/carton-supplier/internal/shipments/pending', params={'factory_id': 'huaxing'}).json()['total'] == 0


def test_zero_arrival_closes_only_selected_papers_of_one_mixed_original_note(monkeypatch):
    from test_carton_special_requests import BASE, setup, create_body, command, ok, accept
    from test_carton_supplier_portal import supplier_login, accept_all
    from test_carton_unified_deliveries import EXTERNAL, INTERNAL
    with make_client(monkeypatch) as client:
        setup(client)
        body = create_body(); body['lines'].append(dict(body['lines'][0], specification='22*11*9'))
        request = ok(client.post(BASE, json=body), 201)
        request = ok(client.post(BASE + '/' + request['id'] + '/send', json=command(request)))
        request = accept(client, request)
        supplier_login(client); formal = accept_all(client)
        group = ok(client.post(EXTERNAL, json=command(delivery_note_no='PARTIAL-CLOSE-' + uuid4().hex[:8], delivery_date='2026-10-18',
            formal_lines=[dict(order_line_id=paper['id'], issue_id=formal['issue_id'], quantity='10', unit_price='2') for paper in formal['lines']],
            special_requests=[dict(id=request['id'], expected_revision=request['revision'], version_id=request['current_version_id'],
                lines=[dict(line_id=paper['id'], quantity='10', unit_price='2') for paper in request['lines']])])), 201)
        login_as(client, 'admin')
        special = group['special'][0]; shipment = special['shipments'][0]
        payload = command(acceptance_date='2026-10-18', formal=dict(expected_revision=group['formal']['revision'], remaining_action='WAIT',
            lines=[dict(shipment_line_id=paper['id'], received_quantity='0', unit_price='2', close_remaining=index == 0,
                difference_reason='此纸品未到且确认不再送' if index == 0 else '') for index, paper in enumerate(group['formal']['lines'])]),
            special=[dict(request_id=special['id'], shipment_id=shipment['id'], expected_revision=special['revision'],
                remaining_action='WAIT', close_reason='仅第一纸品本单不再送', lines=[dict(shipment_line_id=paper['id'],
                    received_quantity='0', close_remaining=index == 0) for index, paper in enumerate(shipment['lines'])])])
        result = ok(client.post(INTERNAL + '/' + group['id'] + '/receive', json=payload))
        assert ok(client.post(INTERNAL + '/' + group['id'] + '/receive', json=payload)) == result
        assert not result['receipts'] and result['status'] == 'SENT'
        formal_lines = [line for line in result['lines'] if line['source_kind'] == 'FORMAL']
        special_lines = [line for line in result['lines'] if line['source_kind'] == 'SPECIAL']
        for papers in [formal_lines, special_lines]:
            assert D(papers[0]['received_quantity']) == 0 and D(papers[0]['closed_quantity']) == 10 and D(papers[0]['remaining_quantity']) == 0
            assert D(papers[1]['received_quantity']) == 0 and D(papers[1]['closed_quantity']) == 0 and D(papers[1]['remaining_quantity']) == 10


def test_manual_warehouse_bridge_free_b_freezes_source_and_keeps_supplier_original_unknown(monkeypatch):
    from test_carton_replenishment_api import setup, body, replenish
    from test_carton_supplier_portal import supplier_login, setup_portal
    from test_carton_p1_lifecycle import task_for, respond
    with make_client(monkeypatch) as client:
        order, stocks = setup(client, monkeypatch)
        made = replenish(client, order, body(order, stocks, 'SUPPLIER', 2))
        assert made.status_code == 201, made.text
        order, issue = made.json()['order'], made.json()['issue']
        setup_portal(client)  # Provision the separate supplier actor without altering this B's ledger.
        supplier_login(client)
        b_task = task_for(client, 'REPLENISHMENT', order['id'])
        accepted = respond(client, b_task, 'ACCEPT', promised_date='2026-08-05')
        assert accepted.status_code == 200, accepted.text
        b_disputed = respond(client, task_for(client, 'REPLENISHMENT', order['id']), 'DISPUTE', reason='先核实本补单责任说明')
        assert b_disputed.status_code == 200, b_disputed.text
        workspace = client.get('/api/carton-supplier/workspace', params={'factory_id': 'huaxing'}).json()
        source = next(source for target in workspace['orders'] if target['id'] == order['id']
            for source in target['replenishment_sources'] if source['issue_id'] == issue['id'])
        assert not source['lines'][0]['accepted'] and '异议' in source['lines'][0]['shipping_blocked_reason']
        accepted = respond(client, task_for(client, 'REPLENISHMENT', order['id']), 'ACCEPT', promised_date='2026-08-05')
        assert accepted.status_code == 200, accepted.text
        disputed = respond(client, task_for(client, 'REGULAR', order['id']), 'DISPUTE', reason='普通版本交期另行核实，不涉及本补单')
        assert disputed.status_code == 200, disputed.text
        login_as(client, 'admin')
        location = next(item['location_id'] for item in stocks if item['order_line_id'] == order['lines'][0]['id'])
        payload = dict(factory_id='huaxing', request_id=uuid4().hex, delivery_note_no='MANUAL-B-' + uuid4().hex[:8],
            delivery_date='2026-08-05', acceptance_date='2026-08-05', order_revisions={order['order_no']: order['revision']},
            formal_lines=[dict(order_line_id=order['lines'][0]['id'], replenishment_issue_id=issue['id'], delivered_quantity=2,
                received_quantity=2, unit_price=None, location_allocations=[dict(location_id=location, quantity=2)])])
        received = client.post('/api/carton-unified-deliveries/warehouse-receive', json=payload)
        assert received.status_code == 200, received.text
        line = received.json()['receipts'][0]['lines'][0]
        assert line['replenishment_issue_id'] == issue['id'] and line['responsibility'] == 'SUPPLIER'
        assert D(line['unit_price']) == 2 and D(line['settlement_unit_price']) == 0
        rows = client.get('/api/carton-price-reviews/internal', params={'factory_id': 'huaxing'}).json()['items']
        review = next(item for item in rows if item['receipt_line_id'] == line['id'])
        assert review['status'] == 'CONFIRMED' and review['original_unit_price'] is None and D(review['effective_unit_price']) == 0
        from datetime import datetime
        from app.services import carton_procurement as core
        from test_carton_supplier_settlement_api import payload as statement_payload, action
        login_as(client, 'carton_supervisor')
        monkeypatch.setattr(core, 'business_now', lambda: datetime(2026, 9, 5, 12))
        monthly = client.get('/api/carton-procurement/supplier-settlements/workspace', params={'factory_id': 'huaxing', 'period': '2026-08'}).json()
        assert not any(source['source_key'] == 'RECEIPT:' + line['id'] for source in monthly['sources'])
        assert not any('核价' in issue for source in monthly['sources'] for issue in source['issues'])
        saved = client.post('/api/carton-procurement/supplier-settlements', json=statement_payload(monthly))
        assert saved.status_code == 200 and not saved.json()['result']['issues'], saved.text
        confirmed = action(client, saved.json())
        assert confirmed.status_code == 200, confirmed.text
