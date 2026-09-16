from datetime import date
from decimal import Decimal

from test_customer_order_ledger import engine, db, client, preview, ingest, user, ship_body
from app.services import customer_order_ledger as ledger
from app.schemas.customer_order_ledger import ReasonIn, AmendIn, DispatchIn
from app.services.auth import get_current_user


def make_order(db, ref, qty='100', customer='buzzbee', due='2026-10-01', **fields):
    data = preview(qty=qty, reference=ref)
    data['customer_code'] = customer
    data['customer_name'] = customer
    data['rows'][0].update(requested_ship_date=due, **fields)
    return ingest(db, data)


def schedule(client, **params):
    return client.get('/api/customer-order-ledger/schedule', params={'factory_id': 'huaxing', 'customer_code': 'buzzbee', **params})


def test_schedule_customer_and_factory_permissions(client, db):
    response = client.get('/api/customer-order-ledger/schedule/customers?factory_id=huaxing')
    assert response.status_code == 200
    assert response.json()['factory_id'] == 'huaxing'
    assert 'buzzbee' in {c['code'] for c in response.json()['items']}
    assert 'jakks' not in {c['code'] for c in response.json()['items']}
    assert schedule(client, customer_code='jakks').status_code == 400
    assert schedule(client, factory_id='huadeng').status_code == 403
    assert schedule(client, factory_id='group').status_code == 400
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['inbox_read'], 'pmc-warehouse')
    assert schedule(client).status_code == 403


def test_customer_sections_partial_delivery_totals_count_order_once(client, db):
    partial = make_order(db, 'PARTIAL', packaging='客户包装', carton_mark='保留箱唛')
    full = make_order(db, 'FULL', qty='50')
    cancelled = make_order(db, 'CANCELLED', qty='70')
    make_order(db, 'UNKNOWN', qty='', due='')
    make_order(db, 'OTHER-CUSTOMER', customer='disney', qty='1000', printing_requirement='别的客户要求')
    for line, amount in ((partial, '30'), (full, '50'), (cancelled, '10')):
        ledger.ship(db, line, ship_body(line, qty=amount, key='ship-' + line.id, document='DOC-' + line.id), '业务员')
    ledger.cancel(db, cancelled, ReasonIn(expected_revision=cancelled.revision, reason='客户取消余数'), '业务员')
    db.commit()
    result = schedule(client).json()
    assert result['summary'] == dict(order_count=4, ordered_quantity='220', shipped_quantity='90', remaining_quantity='70', unknown_quantity_count=1, cancelled_count=1)
    assert {r['id'] for r in result['sections']['unshipped']['items']} == {partial.id, next(r['id'] for r in result['sections']['unshipped']['items'] if r['reference_no'] == 'UNKNOWN')}
    assert result['sections']['shipped']['total'] == 3
    assert result['sections']['cancelled']['items'][0]['remaining_quantity'] == '0'
    columns = {c['key'] for c in result['columns']}
    assert 'packaging' in columns and 'carton_mark' in columns
    assert not {'unit_price_hkd', 'amount_hkd', 'printing_requirement', 'import_controls'} & columns


def test_schedule_pagination_dates_search_and_stable_columns(client, db):
    first = make_order(db, 'EARLY', due='2026-10-01', barcode='001234')
    make_order(db, 'LATE', due='2026-10-02')
    make_order(db, 'UNSET', due='')
    result = schedule(client, page_size=1, unshipped_page=2).json()
    assert result['sections']['unshipped']['total'] == 3
    assert result['sections']['unshipped']['items'][0]['reference_no'] == 'LATE'
    assert result['summary']['order_count'] == 3
    assert schedule(client, page_size=1, unshipped_page=99).json()['sections']['unshipped']['page'] == 3
    result = schedule(client, date_from='2026-10-02', date_to='2026-10-02').json()
    assert result['summary']['order_count'] == 1
    upper_only = schedule(client, date_to='2026-10-02').json()
    assert upper_only['summary']['order_count'] == 2
    assert {row['reference_no'] for row in upper_only['sections']['unshipped']['items']} == {'EARLY', 'LATE'}
    assert any(c['key'] == 'barcode' for c in result['columns'])
    assert schedule(client, q='EARLY').json()['sections']['unshipped']['items'][0]['id'] == first.id
    assert schedule(client, q='%').json()['summary']['order_count'] == 0
    assert schedule(client, date_from='2026-11-01', date_to='2026-10-01').status_code == 400
    assert schedule(client, unshipped_page=0).status_code == 422


def test_schedule_reflects_existing_amend_dispatch_ship_and_reversal(client, db):
    line = make_order(db, '00001', qty='0.3', barcode='00000001')
    ledger.dispatch(db, line, DispatchIn(expected_revision=line.revision, recipients=['pmc']), '业务员')
    ledger.amend(db, line, AmendIn(expected_revision=line.revision, quantity='0.2', requested_ship_date='2026-10-03', note='客户变更', reason='核对客户通知'), '业务员')
    ledger.ship(db, line, ship_body(line, qty='0.2'), '业务员')
    db.commit()
    result = schedule(client).json()
    assert result['summary']['ordered_quantity'] == '0.2'
    assert result['summary']['remaining_quantity'] == '0'
    assert result['sections']['unshipped']['total'] == 0
    row = result['sections']['shipped']['items'][0]
    assert row['id'] == line.id and row['version'] == 2
    assert row['dispatch_status'] == 'sent' and row['data']['note'] == '客户变更'
    assert row['data']['barcode'] == '00000001'
    from sqlalchemy import select
    from app.models.customer_order_ledger import OrderLedgerShipment as Shipment
    shipment = db.scalar(select(Shipment).where(Shipment.line_id == line.id))
    ledger.reverse_shipment(db, line, shipment, ReasonIn(expected_revision=line.revision, reason='走货单据更正'), '业务员')
    db.commit()
    assert schedule(client).json()['sections']['unshipped']['total'] == 1


def test_empty_customer_does_not_show_demo_rows(client):
    result = schedule(client).json()
    assert result['summary']['order_count'] == 0
    assert result['columns'] == []
    assert all(section['items'] == [] for section in result['sections'].values())
