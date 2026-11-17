from app.services.huakang_b_jp import intake
"""Synthetic monthly enquiry layouts; no private mail or order data in Git."""
from datetime import date, datetime
from io import BytesIO

import openpyxl
import pytest
from fastapi import HTTPException

from app.services.huakang_b_jp import parser, intake
from app.services.huakang_b_jp.annotate import annotate
from app.services.huakang_b_jp.prices import PriceTable
from test_huakang_b_jp import db, engine, install, preview, export, mail
from test_huakang_b_jp_november_feedback import forwarding, table


HEADERS = ['PO#', 'Fty S/D', 'Destination port name', 'Fty', 'Item description', 'VSK #', 'Qty (Pcs)', 'Total (Pcs)']
COUNTS = (6, 2, 3, 5, 4, 3, 3, 7, 6)


def groups(*, old=False):
    tables = []
    for group, count in enumerate(COUNTS):
        rows = [[str(880000000 + index), '1/15' if old else ('1/20' if group < 7 else '3/2'),
                 'PORT STORAGE', 'RR', 'Synthetic toy', str(71000 + group),
                 '999999' if old else str((index + 1) * 10), ''] for index in range(count)]
        rows[-1][-1] = str(sum(int(row[6]) for row in rows))
        tables.append(table(HEADERS, rows))
    return ''.join(tables)


def monthly():
    return forwarding('<p>DDD 11/20,货期请看以下回复.</p>'
        '<p>#71001 production MOQ 5K.</p>'
        '<p>#71002 3L pkg can tag on another order,no MOQ issue.</p>'
        '<p>#71003 all component在12/21送到.</p>'
        '<p>其他 item no MOQ issue.</p>' + groups() + '<p>发件人：历史回复</p>' + groups(old=True))


def test_short_vsk_monthly_tables_keep_all_current_groups_and_exclude_history_totals():
    result = parser.parse_order_email(monthly(), 'Fw: RR - WM US / monthly order', date(2026, 11, 5))
    rows = result['orders']
    assert len(rows) == sum(COUNTS) == 39
    assert result['meta']['forwarded_enquiry'] and result['meta']['table_count'] == 9
    assert sum(int(row['qty']) for row in rows) == sum(n * (n + 1) // 2 * 10 for n in COUNTS)
    assert len({(row['customer_po'], row['long_code']) for row in rows}) == 39
    assert [row['cutoff_date'] for row in rows].count('2027/1/20') == 26
    assert [row['cutoff_date'] for row in rows].count('2027/3/2') == 13
    assert all(row['long_code'] == row['baby_item'] for row in rows)
    assert all(row['customer'] == 'WM US' and row['country'] == '美国' for row in rows)
    assert all(row['pkg'] == ('3L' if row['baby_item'] == '71002' else '') for row in rows)
    assert result['meta']['ddd'] == 'DDD 11/20'
    assert '其他 item no MOQ issue' in result['meta']['global_note']
    assert all('production MOQ 5K' in row['item_note'] for row in rows if row['baby_item'] == '71001')
    assert all('散件12/21送到' in row['item_note'] for row in rows if row['baby_item'] == '71003')
    assert any('缺少长货号/规格' in warning for warning in result['warnings'])


@pytest.mark.parametrize('cover', ['FYI', '取消此单，请查看以下问单'])
def test_short_vsk_tables_cannot_revive_cancelled_or_reference_forwarding(cover):
    result = parser.parse_order_email(forwarding(groups(), cover), 'Fw: WM US', date(2026, 11, 5))
    assert not result['orders']


def test_explicit_update_still_reuses_only_nearest_quoted_vsk_table():
    result = parser.parse_order_email('<p>S/D 2/10. 8L pkg.</p><p>发件人：历史回复</p>' + groups(),
                                      'WM US', date(2026, 11, 5))
    assert len(result['orders']) == COUNTS[0]
    assert all(row['cutoff_date'] == '2027/2/10' and row['pkg'] == '8L' for row in result['orders'])
    assert all(row['quoted_original']['cutoff_date'] == '2027/1/20' for row in result['orders'])


@pytest.mark.parametrize('missing', ['VSK #', 'PO#', 'Fty S/D', 'Qty (Pcs)'])
def test_short_numbers_need_explicit_unambiguous_monthly_headers(missing):
    headers = [value if value != missing else 'Unspecified' for value in HEADERS]
    html = table(headers, [['880000001', '1/20', 'PORT STORAGE', 'RR', 'Toy', '71000', '20', '20']])
    assert not parser.parse_order_email(html, 'WM US', date(2026, 11, 5))['orders']


def test_monthly_total_rows_are_not_orders_and_other_numbers_do_not_become_items():
    html = table(HEADERS, [
        ['880000001', '1/20', 'PORT', 'RR', 'Toy', '71000', '20', '20'],
        ['880000002', '1/20', 'PORT 54321', 'RR', 'Toy', 'unknown', '30', '30'],
        ['Total', '', '', '', '', '', '50', '50'],
    ])
    rows = parser.parse_order_email(html, 'WM US', date(2026, 11, 5))['orders']
    assert len(rows) == 2
    assert rows[0]['baby_item'] == '71000'
    assert rows[1]['baby_item'] == '' and rows[1]['qty'] == '30'


def test_item_package_directive_does_not_apply_to_siblings_or_override_current_table():
    html = '<p>#71000 3L pkg.</p><p>8L pkg.</p>' + table(
        HEADERS + ['Pkg'], [
            ['880000001', '1/20', 'PORT', 'RR', 'Toy', '71000', '20', '20', '6L'],
            ['880000001', '1/20', 'PORT', 'RR', 'Toy', '71001', '30', '30', ''],
        ])
    result = parser.parse_order_email(html, 'WM US', date(2026, 11, 5))
    assert [row['pkg'] for row in result['orders']] == ['6L', '8L']
    assert any('客人表格是 6L' in warning and '3L' in warning for warning in result['warnings'])


@pytest.mark.parametrize(('instruction', 'expected_package', 'conflict'), [
    ('#71000 3L pkg or 8L pkg.', '', True),
    ('#71000 3L pkg.', '3L', False),
])
def test_current_item_package_update_preserves_quoted_original_without_reusing_conflicts(
        instruction, expected_package, conflict):
    html = '<p>S/D 2/10.</p><p>' + instruction + '</p><p>发件人：历史回复</p>' + table(
        HEADERS + ['Pkg'], [
            ['880000001', '1/20', 'PORT', 'RR', 'Toy', '71000', '20', '20', '6L'],
            ['880000001', '1/20', 'PORT', 'RR', 'Toy', '71001', '30', '30', '6L'],
        ])
    result = parser.parse_order_email(html, 'WM US', date(2026, 11, 5))
    rows = result['orders']
    assert [row['pkg'] for row in rows] == [expected_package, '6L']
    assert bool(rows[0].get('reply_package_conflict')) is conflict
    assert all(row['quoted_original']['pkg'] == '6L' for row in rows)
    assert all(row['cutoff_date'] == '2027/2/10' for row in rows)
    if conflict:
        assert any('3L / 8L' in warning and '请人工核对' in warning for warning in result['warnings'])


@pytest.mark.parametrize('instructions', [
    '<p>#71000 3L pkg; #71001 8L pkg.</p>',
    '<p>#71000 #71001 3L pkg or 8L pkg.</p>',
    '<p>#71000 #71001 3L pkg.</p><p>#71000 #71001 8L pkg.</p>',
])
def test_multiple_item_packages_stay_unresolved_and_do_not_fall_back_to_global_or_history(instructions):
    html = instructions + '<p>6L pkg.</p>' + table(HEADERS, [
        ['880000001', '1/20', 'PORT', 'RR', 'Toy', '71000', '20', '20'],
        ['880000001', '1/20', 'PORT', 'RR', 'Toy', '71001', '30', '30'],
        ['880000001', '1/20', 'PORT', 'RR', 'Toy', '71002', '40', '40'],
    ])
    result = parser.parse_order_email(html, 'WM US', date(2026, 11, 5))
    assert [row['pkg'] for row in result['orders']] == ['', '', '6L']
    assert all(row.get('reply_package_conflict') for row in result['orders'][:2])
    assert any('3L / 8L' in warning and '请人工核对' in warning for warning in result['warnings'])

    class History:
        loaded = True
        def get_item_detail(self, _item):
            return {'装箱数': '2'}
        def check_row(self, *_args):
            return False, True, '美国', '12L'

    annotate(result, History(), PriceTable())
    assert [row['pkg'] for row in result['orders']] == ['', '', '6L']
    assert not any(row.get('pkg_from_ref') for row in result['orders'])


def test_monthly_missing_commercial_fields_are_optional_in_44_column_output(db):
    install(db)
    files = [('synthetic-monthly.eml', mail(monthly(), 'WM US monthly enquiry'))]
    parsed = preview(db, files)
    assert len(parsed['rows']) == 39 and parsed['failed_sources'] == []
    assert all(row['sub_item_t'] == row['baby_item'] for row in parsed['rows'])
    assert all(not row['carton_t'] and not row['price_t'] for row in parsed['rows'])
    pending = intake.resolve_rows(parsed, [row['id'] for row in parsed['rows']], [])
    assert all(row['generation_reminders'] for row in pending)
    changes = [{'id': row['id'], 'field': field, 'value': value} for row in parsed['rows']
               for field, value in [('carton_t', '2'), ('price_t', '3'), ('factory_price_t', '2.5')]]
    result = export(db, parsed, overrides=changes, files=files)
    sheet = openpyxl.load_workbook(BytesIO(result.content)).active
    assert (sheet.max_row, sheet.max_column) == (40, 44)
    assert sum(sheet.cell(row, 13).value for row in range(2, 41)) == sum(int(row['qty']) for row in parsed['rows'])
    assert sheet.cell(2, 3).value == '880000000' and sheet.cell(2, 11).value == '71000'
    assert sheet.cell(2, 20).value == datetime(2027, 1, 20)
    assert sheet.cell(40, 20).value == datetime(2027, 3, 2)
    assert all(row['review_status'] == 'pending' for row in result.data['rows'])
    assert export(db, parsed, overrides=changes, files=files).id == result.id
