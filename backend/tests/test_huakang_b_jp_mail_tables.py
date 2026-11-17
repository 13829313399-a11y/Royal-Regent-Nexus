"""Synthetic clipboard/mail-table contracts; no customer mail is stored here."""
import csv
from datetime import date
from io import StringIO

import pytest

from app.services.huakang_b_jp import parser
from test_huakang_b_jp_november_feedback import table


HEADERS = ['Customer Name', 'Customer PO No.', 'Sales Order No.', 'Vendor Name',
           'No.', 'Description', 'Pkg & IC', 'Quantity', 'Original Req.Delivery Date']
ROWS = [
    ['Sample Retail Canada', '0000001234', 'SCHK-26-10001', 'Synthetic Vendor',
     '81001-000-1A-006-BOX', 'Sample Toy A', 'E/F PACKAGING', '1,200.00', '1/20/2027'],
    ['Sample Retail Canada', '0000005678', 'SCHK-26-10002', 'Synthetic Vendor',
     '81002-INT-2E-002-BAG', 'Sample Toy B', '8L packaging\nsound only IC', '50.00', '1/20/2027'],
]
SUBJECT = 'Fw: Re: (11/9/26) WM CA - inquiry #81001 81002 _ RR'
STAMP = date(2026, 11, 10)


def render(kind, rows, headers=HEADERS):
    values = [headers, *rows] if headers else rows
    if kind == 'html':
        return table(headers, rows)
    if kind == 'tsv':
        out = StringIO()
        csv.writer(out, delimiter='\t', lineterminator='\n').writerows(values)
        return out.getvalue()
    if kind == 'vertical-pipe':
        return '\n'.join('|\n' + '\n|\n'.join(row) + '\n|' for row in values) + '\n'
    if kind == 'pipe':
        return '\n'.join('| ' + ' | '.join(cell.replace('\n', ' ') for cell in row) + ' |' for row in values) + '\n'
    raise AssertionError(kind)


@pytest.mark.parametrize('kind', ['html', 'tsv', 'vertical-pipe', 'pipe'])
def test_current_body_customer_and_requested_delivery_win_over_subject_and_history(kind):
    old = [ROWS[0][:-1] + ['1/5/2027'], ROWS[1]]
    prefix = 'Dear colleague,\nDDD/11/16 货期如下！\nNO MOQ ISSUE\nNO Shipment surcharge\n\n'
    marker = '\n---- Replied Message ----\n\n'
    if kind == 'html':
        prefix = '<p>' + prefix.replace('\n', '<br>') + '</p>'
        marker = '<p>---- Replied Message ----</p>'
    source = prefix + render(kind, ROWS) + marker + render(kind, old)
    result = parser.parse_order_email(source, SUBJECT, STAMP, 'synthetic')
    rows = result['orders']
    assert len(rows) == 2 and result['meta']['table_count'] == 1
    assert [row['baby_item'] for row in rows] == ['81001', '81002']
    assert [row['customer_po'] for row in rows] == ['0000001234', '0000005678']
    assert [row['qty'] for row in rows] == ['1200.00', '50.00']
    assert all(row['customer'] == 'Sample Retail Canada' and row['country'] == '加拿大' for row in rows)
    assert all(row['cutoff_date'] == '2027/1/20' and row['ship_date'] == '2027/1/12' for row in rows)
    assert rows[1]['pkg'] == '8L packaging sound only IC'
    assert result['meta']['customer'] == 'Sample Retail Canada'
    assert result['meta']['country'] == '加拿大' and result['meta']['ddd'] == 'DDD 11/16'
    assert result['meta']['global_note'] == 'NO Shipment surcharge'


def test_subject_date_is_not_a_customer_and_only_fills_missing_table_names():
    html = table(['Item', 'Qty'], [['81001-000-1A-006-BOX', '12']])
    result = parser.parse_order_email(html, SUBJECT, STAMP)
    assert result['orders'][0]['customer'] == result['meta']['customer'] == 'WM CA'
    assert result['orders'][0]['cutoff_date'] == ''  # Subject date and DDD are not delivery dates.
    assert parser.customer_from_subject('Fw: [2026-11-09] Example Ltd / Canada') == 'Example Ltd'
    assert parser.customer_from_subject('Fw: Example (CA) / inquiry') == 'Example (CA)'


def test_explicit_customers_are_kept_per_row_without_collapsing_into_subject_customer():
    other = ['Other Retail Australia', *ROWS[1][1:]]
    result = parser.parse_order_email(table(HEADERS, [ROWS[0], other]), 'Wrong Customer / US', STAMP)
    assert [row['customer'] for row in result['orders']] == ['Sample Retail Canada', 'Other Retail Australia']
    assert [row['country'] for row in result['orders']] == ['加拿大', '澳大利亚']
    assert result['meta']['customer'] == result['meta']['country'] == ''


@pytest.mark.parametrize('header,value', [
    ('Original Req.Delivery Date', ''),
    ('Original Req.Delivery Date', '2/30/2027'),
    ('Original Req.Delivery Date', 'unconfirmed'),
    ('Order Date', '1/20/2027'),
    ('Previous Original Req.Delivery Date', '1/20/2027'),
])
def test_only_the_explicit_valid_delivery_header_provides_the_cutoff(header, value):
    result = parser.parse_order_email('<p>DDD 11/16</p>' + table(
        [*HEADERS[:-1], header], [[*ROWS[0][:-1], value]]), SUBJECT, STAMP)
    assert result['orders'][0]['cutoff_date'] == result['orders'][0]['ship_date'] == ''


def test_duplicate_requested_delivery_columns_are_not_arbitrarily_selected():
    result = parser.parse_order_email(table([*HEADERS, HEADERS[-1]], [[*ROWS[0], '1/21/2027']]), SUBJECT, STAMP)
    assert not result['orders'][0]['cutoff_date']
    assert any('列不唯一' in warning for warning in result['warnings'])


@pytest.mark.parametrize('kind', ['tsv', 'vertical-pipe', 'pipe'])
@pytest.mark.parametrize('cover', ['FYI', 'Cancel this order'])
def test_plain_tables_do_not_revive_quoted_or_cancelled_enquiries(kind, cover):
    result = parser.parse_order_email(cover + '\n---- Replied Message ----\n' + render(kind, ROWS), SUBJECT, STAMP)
    assert result['orders'] == []


@pytest.mark.parametrize('kind', ['tsv', 'vertical-pipe', 'pipe'])
def test_plain_current_update_reuses_only_the_nearest_quoted_table(kind):
    result = parser.parse_order_email('S/D 2/10. 3L pkg.\n---- Replied Message ----\n' + render(kind, ROWS[:1])
        + '\n---- Original Message ----\n' + render(kind, ROWS[1:]), SUBJECT, STAMP)
    assert len(result['orders']) == 1
    row = result['orders'][0]
    assert row['baby_item'] == '81001' and row['pkg'] == '3L'
    assert row['cutoff_date'] == '2027/2/10'
    assert row['quoted_original']['cutoff_date'] == '2027/1/20'


@pytest.mark.parametrize('kind', ['tsv', 'vertical-pipe', 'pipe'])
def test_incomplete_delimited_rows_are_not_regrouped_or_inferred(kind):
    invalid = [ROWS[0], ROWS[1][:-1]]
    result = parser.parse_order_email(render(kind, invalid), SUBJECT, STAMP)
    assert result['orders'] == []


def test_bare_whitespace_is_not_a_table_and_headerless_numeric_ambiguity_still_needs_selection():
    assert not parser.parse_order_email('\n'.join(' '.join(row) for row in [HEADERS, *ROWS]), SUBJECT, STAMP)['orders']
    source = render('tsv', [['81001-000-1A-006-BOX', '1200', '6'], ['81002-INT-2E-002-BAG', '50', '2']], headers=None)
    with pytest.raises(parser.QuantityColumnRequired) as error:
        parser.parse_order_email(source, SUBJECT, STAMP)
    assert error.value.table_index == 0
    result = parser.parse_order_email(source, SUBJECT, STAMP, quantity_columns={0: 1})
    assert [row['qty'] for row in result['orders']] == ['1200', '50']


def test_markdown_separator_and_angle_brackets_stay_data_without_inserting_markup():
    rows = [ROWS[0][:5] + ['Toy <img src="ignored"> & accessory', *ROWS[0][6:]]]
    source = render('pipe', rows)
    header, rest = source.split('\n', 1)
    source = header + '\n|' + '|'.join(['---'] * len(HEADERS)) + '|\n' + rest
    converted, count = parser._structured_plaintext_html(source)
    assert count == 1 and '<img' not in converted and '&lt;img' in converted
    result = parser.parse_order_email(source, SUBJECT, STAMP)
    assert result['orders'][0]['description'] == 'Toy <img src="ignored"> & accessory'


@pytest.mark.parametrize('kind', ['tsv', 'pipe', 'vertical-pipe'])
@pytest.mark.parametrize('marker', ['Original Message', 'Replied Message', '发件人：历史邮件'])
def test_inline_delimited_mail_boundary_stays_outside_the_current_table(kind, marker):
    headers = ['Item', 'Qty', 'Customer PO']
    source = render(kind, [
        ['81001-000-1A-006-BOX', '1200', '0000001234'],
        [marker, '', ''],
        headers,
        ['81002-INT-2E-002-BAG', '999', '0000005678'],
    ], headers=headers)
    result = parser.parse_order_email(source, SUBJECT, STAMP)
    assert [(row['baby_item'], row['qty']) for row in result['orders']] == [('81001', '1200')]
    assert result['meta']['table_count'] == 1


@pytest.mark.parametrize('kind', ['tsv', 'pipe', 'vertical-pipe'])
def test_repeated_plain_headers_create_separate_tables_not_pseudo_orders(kind):
    source = render(kind, [
        ['81001-000-1A-006-BOX', '1200', '0000001234'],
        ['Item', 'Customer PO', 'Qty'],
        ['81002-INT-2E-002-BAG', '0000005678', '50'],
    ], headers=['Item', 'Qty', 'Customer PO'])
    result = parser.parse_order_email(source, SUBJECT, STAMP)
    assert result['meta']['table_count'] == 2
    assert [(row['baby_item'], row['qty']) for row in result['orders']] == [('81001', '1200')]
    assert any('2 个订单表格' in warning for warning in result['warnings'])
