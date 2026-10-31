"""Customer-specific item identity and customer-independent split provenance."""
from io import BytesIO

import pytest
from openpyxl import Workbook

from test_carton_item_schedule import HEADERS, source_row, _prepare_schedule_customer
from test_molding_sample_api import make_client, login_as

BASE = '/api/carton-procurement'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')


def schedule(shipping='001021884', *, source='A', kind='正单'):
    book = Workbook()
    book.active.title = 'ITEM表'
    book.active.append(HEADERS + ['出货货号', '拆单来源'])
    book.active.append(source_row(contract='A', item='10218840069', qty=700) + [shipping, ''])
    book.active.append(source_row(kind, contract='B', item='10218840069', qty=300) + [shipping, source])
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


@pytest.mark.parametrize('customer', ['360', 'DICKIE'])
@pytest.mark.parametrize('sales', [False, True])
def test_both_intakes_keep_split_quantities_and_only_360_uses_shipping(monkeypatch, customer, sales):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client)
        login_as(client, 'admin')
        response = client.post(BASE + '/customers', json=dict(factory_id='huaxing', customer_code='360', customer_name='360'))
        assert response.status_code == 201, response.text
        content = schedule()

        def upload():
            if sales:
                return client.post(f'/api/customer-orders/{customer.lower()}/warehouse-schedule',
                    data=dict(factory_id='huaxing', source_kind='UPLOADED'),
                    files={'schedule_file': ('schedule.xlsx', content)})
            return client.post(BASE + '/weekly-imports', params={'factory_id': 'huaxing'},
                data={'customer_code': customer}, files={'file': ('schedule.xlsx', content)})

        first = upload()
        assert first.status_code == (200 if sales else 201), first.text
        batch_id = first.json()['batch_id' if sales else 'id']
        batch = client.get(BASE + '/imports/' + batch_id, params={'factory_id': 'huaxing'}).json()
        rows = batch['parse_summary']['rows']
        assert [row['quantity'] for row in rows] == [700, 300]
        assert [row['contract_no'] for row in rows] == ['A', 'B']
        assert [row['split_source'] for row in rows] == ['', 'A']
        assert all(row['order_type'] == '正单' for row in rows)
        assert all(row['item_no'] == ('001021884' if customer == '360' else '10218840069') for row in rows)
        assert all(row['match_status'] == 'MISSING_ORDER' for row in rows)
        assert rows[0]['schedule_identity'] != rows[1]['schedule_identity']
        if customer == '360':
            assert all(row['source_item_no'] == '10218840069' for row in rows)
        assert upload().json()['duplicate'] is True
        assert client.get(BASE + '/orders', params={'factory_id': 'huaxing'}).json()['total'] == 0


def test_missing_shipping_never_falls_back_and_split_is_not_an_order_type(monkeypatch):
    from app.services.carton_procurement_imports import _parse_weekly, match_carton_import
    # No database is needed to examine the row contract before reconciliation.
    monkeypatch.setattr('app.services.carton_procurement_imports._match_rows', lambda *args: None)
    parsed = _parse_weekly('schedule.xlsx', schedule(shipping='', source='A拆单', kind='拆单'))
    result = match_carton_import(None, 'huaxing', 'WEEKLY_SCHEDULE', parsed,
        dict(customer_code='360', customer_name='360'))
    assert all(row['item_no'] == '' and row['match_status'] == 'REVIEW_REQUIRED' for row in result['rows'])
    assert result['rows'][1]['split_source'] == 'A拆单'
    assert result['rows'][1]['order_type'] == '拆单'
    assert all('补齐' in row['suggestion'] for row in result['rows'])
    assert result['review_count'] == 2


def test_legacy_headers_preserve_generic_split_source():
    from app.services.carton_procurement_imports import _parse_weekly
    book = Workbook()
    book.active.append(['Reference', '货号', '数量', '出货货号', '拆单来源'])
    book.active.append(['B', 'FULL', 300, 'SHIP', 'A'])
    stream = BytesIO()
    book.save(stream)
    row = _parse_weekly('legacy.xlsx', stream.getvalue())['rows'][0]
    assert row['split_source'] == 'A'
    assert row['item_no'] == 'FULL'
    assert row['shipping_item_no'] == 'SHIP'


def test_previous_parser_keeps_purchase_links_and_manual_marks():
    from app.services.carton_procurement import _project_item_schedule_rows
    row = dict(template='unified-item', schedule_customer_code='360', contract_no='A',
        source_reference='SO-A', item_no='FULL-OLD', order_type='正单', schedule_section='PENDING',
        order_id='purchase-1', order_no='PO-1', match_status='MATCHED', manual_ordered=True)
    _project_item_schedule_rows('old', dict(parser_version='schedule-item-amendment-v6', rows=[row]))
    assert row['item_no'] == 'FULL-OLD'
    assert row['order_id'] == 'purchase-1'
    assert row['manual_ordered'] is True
    assert row['match_status'] == 'MATCHED'


def test_shipping_matching_preserves_existing_purchase_quantity():
    from app.services.carton_procurement_imports import _parse_weekly, match_carton_import
    from test_carton_item_schedule import MatchingDb, order
    original = order(contract_no='A', item_no='001021884', customer_code='360', product_order_quantity=1000)
    foreign = order(id='foreign', contract_no='B', item_no='001021884', customer_code='DICKIE', product_order_quantity=300)
    parsed = _parse_weekly('schedule.xlsx', schedule())
    rows = match_carton_import(MatchingDb([original, foreign]), 'huaxing', 'WEEKLY_SCHEDULE', parsed,
        dict(customer_code='360', customer_name='360'))['rows']
    assert rows[0]['order_id'] == original.id
    assert rows[0]['match_status'] == 'QUANTITY_MISMATCH'
    assert rows[1]['match_status'] == 'MISSING_ORDER'
    assert original.product_order_quantity == 1000
    assert [row['quantity'] for row in rows] == [700, 300]


def test_workbook_customer_name_cannot_enable_360_mapping():
    from app.services.carton_procurement_imports import _parse_weekly, match_carton_import
    from test_carton_item_schedule import MatchingDb
    parsed = _parse_weekly('360.xlsx', schedule())
    for row in parsed['rows']:
        row['customer_name'] = '360'
    rows = match_carton_import(MatchingDb([]), 'huaxing', 'WEEKLY_SCHEDULE', parsed,
        dict(customer_code='DICKIE', customer_name='Dickie'))['rows']
    assert all(row['item_no'] == '10218840069' for row in rows)
    assert rows[1]['split_source'] == 'A'
