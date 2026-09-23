from datetime import datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.services.carton_procurement_imports import _parse_weekly, _match_rows


HEADERS = ['订单类型', 'Contract No.', 'SO#/Reference', 'P/O#:', '客名', '产品编号',
           '产品中文名称', '數量', '装箱', '验货日期', '客要求走货期']


def workbook(rows, *, second_rows=None, reverse=False):
    book = Workbook()
    book.active.title = '接单表'
    book.active.append(['合同号', '货号', '数量'])
    book.active.append(['WRONG', 'IGNORE', 999])
    for name, values in [('子弹枪ITEM表', rows), ('水枪ITEM表', second_rows)]:
        if values is None:
            continue
        sheet = book.create_sheet(name)
        sheet.append(['模板说明，不是业务数据'])
        sheet.append(['合同基本信息'])
        sheet.append(HEADERS[::-1] if reverse else HEADERS)
        for row in values:
            sheet.append(row[::-1] if reverse else row)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def source_row(kind='正单', contract='53135', item='0040220-1', qty=360):
    return [kind, contract, '', '0989551378', 'WMU', item, '双支三弹枪', qty, 6,
            datetime(2026, 9, 10), datetime(2026, 9, 17)]


def test_item_sheets_only_by_header_preserve_po_and_nonformal_rows():
    result = _parse_weekly('schedule.xlsx', workbook(
        [source_row(), source_row('备料单', '', qty=0), source_row('正式PO', '53136')],
        second_rows=[source_row(contract='53137')], reverse=True))
    assert len(result['rows']) == 4
    first = result['rows'][0]
    assert first['contract_no'] == first['reference'] == '53135'
    assert first['source_reference'] == ''
    assert first['customer_po'] == '0989551378'
    assert first['item_no'] == '0040220-1'
    assert first['customer_due_date'] == '2026-09-17'
    assert first['inspection_window'] == '2026-09-10'
    assert first['source_row'] == 4
    assert result['review_count'] == 2
    assert result['rows'][1]['quantity'] == 0
    assert result['rows'][1]['contract_no'] == ''
    assert result['field_mappings'][0]['fields']['quantity'] == '數量'


def test_duplicate_formal_rows_and_missing_keys_require_review():
    result = _parse_weekly('schedule.xlsx', workbook([
        source_row(), source_row(), source_row(contract=''),
        source_row(contract='53136', qty=0), source_row(contract='53137', qty=None)]))
    assert all(row['match_status'] == 'REVIEW_REQUIRED' for row in result['rows'])
    assert result['review_count'] == 5


def test_item_rows_not_silently_truncated_at_old_preview_limit():
    result = _parse_weekly('schedule.xlsx', workbook([source_row(contract=str(i)) for i in range(501)]))
    assert len(result['rows']) == 501


def test_missing_required_header_is_explicit_error():
    book = Workbook()
    book.active.title = 'ITEM表'
    book.active.append(['产品编号', '數量'])
    stream = BytesIO()
    book.save(stream)
    with pytest.raises(HTTPException) as error:
        _parse_weekly('schedule.xlsx', stream.getvalue())
    assert error.value.status_code == 422
    assert '缺少' in error.value.detail


def test_duplicate_quantity_headers_are_rejected_instead_of_guessing():
    book = Workbook()
    book.active.title = 'ITEM表'
    book.active.append(HEADERS + ['数量'])
    book.active.append(source_row() + [999])
    stream = BytesIO()
    book.save(stream)
    with pytest.raises(HTTPException) as error:
        _parse_weekly('schedule.xlsx', stream.getvalue())
    assert '重复' in error.value.detail


def test_oversized_item_sheet_fails_instead_of_truncating_demand():
    book = Workbook()
    book.active.title = 'ITEM表'
    book.active.append(HEADERS)
    book.active.cell(5001, 1, '正单')
    stream = BytesIO()
    book.save(stream)
    with pytest.raises(HTTPException) as error:
        _parse_weekly('schedule.xlsx', stream.getvalue())
    assert error.value.status_code == 422
    assert '超过' in error.value.detail


def test_review_rows_do_not_get_automatic_inspection_delivery_reminders():
    from datetime import date
    from app.services.carton_procurement_imports import _apply_inspection_reminders
    rows = _parse_weekly('schedule.xlsx', workbook([source_row('样板单')]))['rows']
    _apply_inspection_reminders(rows, advance_days=3, reference_date=date(2026, 9, 21))
    assert rows[0]['reminder_status'] == 'REVIEW_REQUIRED'
    assert '不计入正单' in rows[0]['suggestion']


class MatchingDb:
    def __init__(self, orders):
        self.orders = orders

    def execute(self, query):
        return SimpleNamespace(all=lambda: [(SimpleNamespace(), order) for order in self.orders])


def order(**updates):
    fields = dict(id='o1', order_no='CO1', customer_po='0989551378', contract_no='53135',
                  item_no='0040220-1', customer_code='BUZZBEE', customer_name='BUZZ BEE',
                  product_order_quantity=360, customer_due_date='2026-09-17', status='PENDING_SUPPLIER')
    return SimpleNamespace(**(fields | updates))


def test_unified_matching_never_falls_back_to_only_contract_or_only_item():
    rows = _parse_weekly('schedule.xlsx', workbook([source_row()]))['rows']
    _match_rows(MatchingDb([order(contract_no='OTHER')]), 'huaxing', 'WEEKLY_SCHEDULE', rows)
    assert rows[0]['match_status'] == 'MISSING_ORDER'
    assert rows[0]['procurement_state'] == 'NEEDS_ORDER'
    _match_rows(MatchingDb([order(item_no='OTHER')]), 'huaxing', 'WEEKLY_SCHEDULE', rows)
    assert rows[0]['match_status'] == 'MISSING_ORDER'


@pytest.mark.parametrize('status,quantity,state', [
    ('CONFIRMED', 360, 'NEEDS_ORDER'), ('PENDING_SUPPLIER', 360, 'ORDERED'),
    ('COMPLETED', 360, 'COMPLETED'), ('COMPLETED', 350, 'NEEDS_ORDER'),
])
def test_procurement_status_and_quantity_gap(status, quantity, state):
    rows = _parse_weekly('schedule.xlsx', workbook([source_row()]))['rows']
    _match_rows(MatchingDb([order(status=status, product_order_quantity=quantity)]), 'huaxing', 'WEEKLY_SCHEDULE', rows)
    assert rows[0]['procurement_state'] == state
    assert rows[0]['match_status'] == ('MATCHED' if quantity == 360 else 'QUANTITY_MISMATCH')


def test_customer_deadline_difference_and_nonformal_exclusion():
    rows = _parse_weekly('schedule.xlsx', workbook([source_row(), source_row('样板单')]))['rows']
    _match_rows(MatchingDb([order(customer_due_date='2026-09-15')]), 'huaxing', 'WEEKLY_SCHEDULE', rows)
    assert rows[0]['match_status'] == 'DATE_MISMATCH'
    assert rows[0]['date_difference']['business_date'] == '2026-09-17'
    assert rows[1]['match_status'] == 'REVIEW_REQUIRED'
    assert 'order_id' not in rows[1]


@pytest.mark.parametrize('raw', ['9/1-10% 9/14-100%', '9/21', '2026/9/1-10% 2026/9/14-100%', '2026-02-30'])
@pytest.mark.parametrize('column,field,source', [
    (9, 'inspection_window', 'source_inspection_window'),
    (10, 'customer_due_date', 'source_customer_due_date'),
])
def test_uncertain_item_dates_preserve_evidence_without_guessing(raw, column, field, source):
    from datetime import date
    from app.services.carton_procurement_imports import _apply_inspection_reminders
    values = source_row()
    values[column] = raw
    parsed = _parse_weekly('schedule.xlsx', workbook([values]))
    row = parsed['rows'][0]
    assert row[source] == raw
    assert row[field] == ''
    assert row['date_review_required'] is True
    assert parsed['review_count'] == 1
    _match_rows(MatchingDb([order()]), 'huaxing', 'WEEKLY_SCHEDULE', [row])
    assert row['order_id'] == 'o1'
    assert row['procurement_state'] == 'ORDERED'
    assert row['match_status'] == 'REVIEW_REQUIRED'
    _apply_inspection_reminders([row], advance_days=3, reference_date=date(2026, 9, 21))
    assert row['reminder_status'] == 'REVIEW_REQUIRED'
    assert not row.get('required_delivery_date')
    assert row[source] == raw


def test_import_api_persists_review_and_is_idempotent_without_writing_orders(monkeypatch):
    from test_molding_sample_api import make_client, login_as
    with make_client(monkeypatch) as client:
        login_as(client, 'warehouse_keeper')
        content = workbook([source_row(), source_row('样板单')])
        kwargs = dict(params={'factory_id': 'huaxing'}, files={'file': ('unified.xlsx', content)})
        response = client.post('/api/carton-procurement/weekly-imports', **kwargs)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body['parse_summary']['review_count'] == 1
        assert [row['match_status'] for row in body['parse_summary']['rows']] == ['MISSING_ORDER', 'REVIEW_REQUIRED']
        repeat = client.post('/api/carton-procurement/weekly-imports', **kwargs)
        assert repeat.status_code == 201, repeat.text
        assert repeat.json()['id'] == body['id']
        assert repeat.json()['duplicate'] is True
        exceptions = client.get('/api/carton-procurement/exceptions', params={'factory_id': 'huaxing'}).json()
        assert {row['category'] for row in exceptions['items']} == {'MISSING_ORDER', 'SCHEDULE_REVIEW_REQUIRED'}
        assert exceptions['total'] == 2
        assert client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['total'] == 0
        assert client.get('/api/carton-procurement/receipts', params={'factory_id': 'huaxing'}).json()['total'] == 0
