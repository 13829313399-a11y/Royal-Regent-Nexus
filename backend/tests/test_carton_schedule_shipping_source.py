"""Customer-specific item identity and customer-independent split provenance."""
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

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


def test_missing_shipping_falls_back_and_split_is_not_an_order_type(monkeypatch):
    from app.services.carton_procurement_imports import _parse_weekly, match_carton_import
    # No database is needed to examine the row contract before reconciliation.
    monkeypatch.setattr('app.services.carton_procurement_imports._match_rows', lambda *args: None)
    parsed = _parse_weekly('schedule.xlsx', schedule(shipping='', source='A拆单', kind='拆单'))
    result = match_carton_import(None, 'huaxing', 'WEEKLY_SCHEDULE', parsed,
        dict(customer_code='360', customer_name='360'))
    assert all(row['item_no'] == row['source_item_no'] == '10218840069' for row in result['rows'])
    assert result['rows'][0].get('match_status') is None
    assert result['rows'][1]['split_source'] == 'A拆单'
    assert result['rows'][1]['order_type'] == '拆单'
    assert result['rows'][1]['match_status'] == 'REVIEW_REQUIRED'
    assert '不计入正单' in result['rows'][1]['suggestion']
    assert result['review_count'] == 1


def _factory_schedule(factory, shipping_column):
    from test_customer_order_huaxing_unified import template as huaxing_template
    from test_customer_order_huakang_a_unified import template as huakang_template
    book = huaxing_template('360') if factory == 'huaxing' else load_workbook(BytesIO(huakang_template('360')))
    sheet = book['ITEM表']
    columns = {cell.value: cell.column for cell in sheet[3] if cell.value}
    shipping_no = sheet.max_column + 1
    if shipping_column:
        sheet.cell(3, shipping_no, '出货货号')
    rows = [
        ('HX-1', '00123456789', '0012345'),
        ('HX-2', '00234567890', '  '),
        ('HX-3', '00345678901', None),
        ('HX-4', None, None),
    ]
    for index, (contract, item, shipping) in enumerate(rows, 4):
        for field, value in zip(HEADERS, source_row(contract=contract, item=item)):
            sheet.cell(index, columns[field]).value = value
        sheet.cell(index, columns['SO#/Reference'], f'RL-{index}')
        if shipping_column:
            sheet.cell(index, shipping_no).value = shipping
    # An order summary can include the same source rows. It must not duplicate demand.
    book['接单表'].cell(4, 1, 'NOT-AN-ITEM-ROW')
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


@pytest.mark.parametrize('factory', ['huaxing', 'huakang-a'])
def test_both_factory_layouts_support_missing_column_and_blank_shipping_cells(monkeypatch, factory):
    from app.services.carton_procurement_imports import SCHEDULE_360_FALLBACK_VERSION
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        created = client.post(BASE + '/customers', json=dict(factory_id=factory, customer_code='LOCAL-360', customer_name='360'))
        assert created.status_code == 201, created.text

        content = _factory_schedule(factory, shipping_column=factory == 'huakang-a')
        for sales in (True, False):
            def upload():
                if sales:
                    return client.post('/api/customer-orders/360/warehouse-schedule',
                        data=dict(factory_id=factory, source_kind='UPLOADED'),
                        files={'schedule_file': ('schedule.xlsx', content)})
                return client.post(BASE + '/weekly-imports', params={'factory_id': factory},
                    data={'customer_code': 'LOCAL-360'}, files={'file': ('schedule.xlsx', content)})

            response = upload()
            assert response.status_code == (200 if sales else 201), response.text
            batch_id = response.json()['batch_id' if sales else 'id']
            summary = client.get(BASE + '/imports/' + batch_id, params={'factory_id': factory}).json()['parse_summary']
            rows = {row['contract_no']: row for row in summary['rows'] if row.get('contract_no')}
            assert set(rows) == {'HX-1', 'HX-2', 'HX-3', 'HX-4'}
            assert rows['HX-1']['item_no'] == ('0012345' if factory == 'huakang-a' else '00123456789')
            assert rows['HX-1']['source_item_no'] == '00123456789'
            assert rows['HX-2']['item_no'] == rows['HX-2']['source_item_no'] == '00234567890'
            assert rows['HX-3']['item_no'] == '00345678901'
            assert rows['HX-4']['item_no'] == '' and rows['HX-4']['match_status'] == 'REVIEW_REQUIRED'
            assert summary['parser_version'] == SCHEDULE_360_FALLBACK_VERSION
            retry = upload()
            assert retry.status_code == (200 if sales else 201), retry.text
            assert retry.json()['duplicate'] is True


def test_canonical_360_review_uses_effective_identity_and_keeps_contract_validation(monkeypatch):
    from app.services.carton_procurement_imports import _parse_weekly, match_carton_import
    monkeypatch.setattr('app.services.carton_procurement_imports._match_rows', lambda *args: None)
    book = Workbook()
    book.active.title = 'ITEM表'
    book.active.append(HEADERS + ['出货货号'])
    for contract, item, shipping in [
        ('SAME', 'ORIGINAL', 'EFFECTIVE'), ('SAME', 'EFFECTIVE', ''),
        ('OTHER', 'SAME-ORIGINAL', 'SHIP-A'), ('OTHER', 'SAME-ORIGINAL', 'SHIP-B'),
        ('SHIP-ONLY', '', 'SHIP-ONLY'), ('', 'ORIGINAL', 'SHIP'),
    ]:
        book.active.append(source_row(contract=contract, item=item) + [shipping])
    stream = BytesIO()
    book.save(stream)
    parsed = _parse_weekly('schedule.xlsx', stream.getvalue())
    result = match_carton_import(None, 'huaxing', 'WEEKLY_SCHEDULE', parsed,
        dict(customer_code='WAREHOUSE-ALIAS', customer_name='Vendor 360', business_customer_code='360'))
    assert [row['item_no'] for row in result['rows']] == ['EFFECTIVE', 'EFFECTIVE', 'SHIP-A', 'SHIP-B', 'SHIP-ONLY', 'SHIP']
    assert all('SO#/Reference 相同' in row['suggestion'] for row in result['rows'][:2])
    assert all(row.get('match_status') is None for row in result['rows'][2:5])
    assert '缺少合同号' in result['rows'][5]['suggestion']


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


def test_same_360_file_can_be_reimported_after_mapping_changes(monkeypatch):
    with make_client(monkeypatch) as client:
        from app.services import carton_procurement as carton, carton_procurement_imports as imports
        login_as(client, 'admin')
        created = client.post(BASE + '/customers', json=dict(factory_id='huaxing', customer_code='360', customer_name='360'))
        assert created.status_code == 201, created.text
        content = schedule(shipping='')

        def upload():
            return client.post(BASE + '/weekly-imports', params={'factory_id': 'huaxing'},
                data={'customer_code': '360'}, files={'file': ('schedule.xlsx', content)})

        def summary(batch_id):
            return client.get(BASE + '/imports/' + batch_id, params={'factory_id': 'huaxing'}).json()['parse_summary']

        real_match = imports.match_carton_import

        def legacy_match(*args, **kwargs):
            parsed = real_match(*args, **kwargs)
            for row in parsed['rows']:
                row.update(item_no='', match_status='REVIEW_REQUIRED', suggestion='请补齐原表“出货货号”')
            return parsed

        with monkeypatch.context() as legacy:
            legacy.setattr(carton, 'weekly_schedule_parser_version', lambda *_: imports.SCHEDULE_IMPORT_PARSER_VERSION)
            legacy.setattr(imports, 'match_carton_import', legacy_match)
            old = upload()
        assert old.status_code == 201, old.text
        old_id = old.json()['id']
        before = summary(old_id)
        assert before['parser_version'] == imports.SCHEDULE_IMPORT_PARSER_VERSION
        assert all(not row['item_no'] for row in before['rows'])

        fresh = upload()
        assert fresh.status_code == 201, fresh.text
        assert not fresh.json()['duplicate'] and fresh.json()['id'] != old_id
        after = summary(fresh.json()['id'])
        assert all(row['item_no'] == '10218840069' for row in after['rows'])
        assert after['parser_version'] == imports.SCHEDULE_360_FALLBACK_VERSION
        assert summary(old_id) == before
        assert upload().json()['id'] == fresh.json()['id']


@pytest.mark.parametrize('shipping,matched_item', [('001021884', '001021884'), ('', '10218840069')])
def test_shipping_matching_preserves_existing_purchase_quantity(monkeypatch, shipping, matched_item):
    from app.services.carton_procurement_imports import _parse_weekly, match_carton_import
    from app.services import carton_schedule_order_matching as po_matching
    from test_carton_item_schedule import MatchingDb, order
    monkeypatch.setattr('app.services.carton_schedule_quantity_matching.read_matches', lambda *args, **kwargs: {})
    monkeypatch.setattr(po_matching, 'read_matches', lambda db, factory, incoming_rows:
        po_matching.solve(incoming_rows, [vars(order) for order in db.orders], {}, factory_id=factory))
    original = order(contract_no='A', item_no=matched_item, customer_code='360', product_order_quantity=1000)
    foreign = order(id='foreign', contract_no='B', item_no=matched_item, customer_code='DICKIE', product_order_quantity=300)
    parsed = _parse_weekly('schedule.xlsx', schedule(shipping=shipping))
    rows = match_carton_import(MatchingDb([original, foreign]), 'huaxing', 'WEEKLY_SCHEDULE', parsed,
        dict(customer_code='360', customer_name='360'))['rows']
    assert rows[0]['order_id'] == original.id
    assert rows[0]['match_status'] == 'QUANTITY_MISMATCH'
    assert rows[1]['match_status'] == 'MISSING_ORDER'
    assert original.product_order_quantity == 1000
    assert [row['quantity'] for row in rows] == [700, 300]


def test_workbook_customer_name_cannot_enable_360_mapping(monkeypatch):
    from app.services.carton_procurement_imports import _parse_weekly, match_carton_import
    monkeypatch.setattr('app.services.carton_procurement_imports._match_rows', lambda *args: None)
    parsed = _parse_weekly('360.xlsx', schedule())
    for row in parsed['rows']:
        row['customer_name'] = '360'
    rows = match_carton_import(None, 'huaxing', 'WEEKLY_SCHEDULE', parsed,
        dict(customer_code='DICKIE', customer_name='360', business_customer_code='dickie'))['rows']
    assert all(row['item_no'] == '10218840069' for row in rows)
    assert rows[1]['split_source'] == 'A'
