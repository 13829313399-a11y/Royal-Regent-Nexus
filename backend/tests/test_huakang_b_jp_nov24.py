"""Synthetic equivalents of the WMUS inquiry; no private mail committed."""
from datetime import date
from io import BytesIO
import openpyxl

from app.services.huakang_b_jp import parser
from app.services.huakang_b_jp.annotate import annotate
from app.services.huakang_b_jp.prices import PriceTable
from app.services.huakang_b_jp.schedule import ScheduleRef
from app.services.huakang_b_jp.clipboard import export_clipboard
from test_huakang_b_jp_clipboard import document, fields


def inquiry():
    return '''<table><tr><td>Customer Name</td><td>Customer PO No.</td><td>Main Item No.</td><td>No.</td><td>Description</td><td>Quantity</td><td>Requested S/D</td></tr>
    <tr><td>Wal-Mart Store Inc.</td><td>0012345678</td><td>77780</td><td>77780-000-2A-006-PTQ</td><td>Mail product description</td><td>6,912</td><td>1/31/2027</td></tr>
    <tr><td></td><td></td><td></td><td></td><td>Total:</td><td>6,912</td><td></td></tr></table>'''


def history(tmp_path, variants=('2A',)):
    book = openpyxl.Workbook(); sheet = book.active; sheet.title = '华康B'
    for _ in range(3): sheet.append(['header'])
    for i, variant in enumerate(variants):
        sheet.append([f'0126-{10000+i}', 'WM US', '00999999', '', 'OLD', '77780-'+variant,
                      '77791/77792/77796', '', '历史中文品名', 'AC' if variant == '2A' else 'EU', 100, '', 6, '美国'])
    path = tmp_path/'history.xlsx'; book.save(path); book.close()
    ref = ScheduleRef(); ref.load(path)
    return ref


def test_wmus_underscore_and_summary_row():
    result = parser.parse_order_email(inquiry(), 'Fw: WMUS_ Exploratory_item#77780 new order inquiry', date(2026, 11, 23))
    assert len(result['orders']) == 1
    assert result['orders'][0]['country'] == '美国'
    assert result['orders'][0]['customer_po'] == '0012345678'
    assert parser.pick_country('Wal-Mart Store Inc.') == ''
    assert parser.pick_country('XWMUSCODE') == ''


def test_exact_long_code_variant_fills_children_and_version_but_mail_name_wins(tmp_path):
    result = parser.parse_order_email(inquiry(), 'WMUS_', date(2026, 11, 23))
    annotate(result, history(tmp_path, ('2A', '2F')), PriceTable())
    row = result['orders'][0]
    assert row['item_t'] == '77780-2A'
    assert row['sub_item_t'] == '77791/77792/77796'
    assert row['product_t'] == 'Mail product description'
    assert row['pkg'] == 'AC' and row['pkg_from_ref']
    assert row['carton_t'] == '6'
    row['description'] = ''
    annotate(result, history(tmp_path), PriceTable())
    assert row['product_t'] == '历史中文品名'


def test_no_history_never_invents_child_items_or_ac_version():
    result = parser.parse_order_email(inquiry(), 'WMUS_', date(2026, 11, 23))
    annotate(result, ScheduleRef(), PriceTable())
    row = result['orders'][0]
    assert row['sub_item_t'] == '' and row['pkg'] == ''
    assert row['product_t'] == 'Mail product description'


def test_other_variant_cannot_be_used_as_reference(tmp_path):
    ref = history(tmp_path)
    assert ref.get_item_detail('77780', '77780-000-2F-006-PTQ') is None
    assert not ref.check_row('WM US', '00999999', '77780', '100', '77780-000-2F-006-PTQ')[0]


def test_clipboard_text_and_html_preserve_identifiers_without_added_quote():
    values = [''] * 44
    values[0], values[2], values[5], values[27] = '0126-00123', '001234567890123456789', '77780', '<img src=x onerror=alert(1)>'
    result = export_clipboard(document(values))
    row = fields(result['text'])[0]
    assert row[2] == values[2] and row[5] == '77780'
    assert 'mso-number-format:\\@' in result['html'] and 'x:str' in result['html']
    assert "'001234567890123456789" not in result['html'] and "'77780" not in result['html']
    assert '<img' not in result['html'] and '&lt;img' in result['html']
