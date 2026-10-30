"""Print covers preserve value units without opening a business database."""
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.services import cutting_export_workbook as workbooks


@pytest.mark.parametrize('currency,amount', [('CNY', '12.30'), ('HKD', '0.00')])
def test_settlement_print_cover_keeps_currency_only_on_amounts(currency, amount):
    report = dict(kind='settlement', month='2026-10', token='synthetic-print-basis',
                  captured_at='2026-10-26', metadata=[['使用状态', '当前有效冻结版本']], sheets=[dict(
        name='结算汇总',
        headers=['加工厂', '结算月份', '统计截止日期', '验收结算套数', '币种', '含税应付金额', '外厂确认凭据'],
        rows=[['合成加工厂', '2026-10', '2026-10-21', 7, currency, amount, '合成确认凭据']])])
    original = deepcopy(report)
    content, extension = workbooks.package(report, SimpleNamespace(display_name='合成验收', id='synthetic'),
        lambda value, user: workbooks.render_workbook(value, user, '外发结算冻结单'))
    assert extension == 'xlsx' and report == original
    book = load_workbook(BytesIO(content))
    try:
        cover = {row[0]: row[1:] for row in list(book['打印摘要'].values)[2:]}
        assert cover == {
            '加工厂': (None, '合成加工厂'),
            '结算月份': (None, '2026-10'),
            '统计截止日期': (None, '2026-10-21'),
            '验收结算套数': (None, 7),
            '币种': (None, currency),
            '含税应付金额': (currency, amount),
        }
        assert list(book['结算汇总'].values)[2] == tuple(original['sheets'][0]['rows'][0])
        assert book['打印摘要'].print_title_rows == '$1:$2'
        assert book['打印摘要'].page_setup.fitToWidth == 1
    finally:
        book.close()


@pytest.mark.parametrize('kind', ['period', 'payments'])
def test_monetary_covers_keep_separate_currencies_and_explicit_zero(kind):
    report = dict(kind=kind, sheets=[dict(name='费用汇总', headers=['币种', '正常费用', '损耗费用'],
        rows=[['CNY', '10.00', '0.00'], ['HKD', '0.00', '0.00']])])
    original = deepcopy(report)
    assert workbooks.print_summary(report)['rows'] == [
        ['正常费用', 'CNY', '10.00'], ['损耗费用', 'CNY', '0.00'],
        ['正常费用', 'HKD', '0.00'], ['损耗费用', 'HKD', '0.00'],
    ]
    assert report == original
