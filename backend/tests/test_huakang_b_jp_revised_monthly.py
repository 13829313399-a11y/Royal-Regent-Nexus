"""Synthetic revised monthly mail, including Foxmail's empty subtotal cells."""
from datetime import date, datetime
from email.message import EmailMessage
from io import BytesIO
import json

import openpyxl
import pytest

from app.services.huakang_b_jp import parser
from test_huakang_b_jp import client, db, engine
from test_huakang_b_jp_mail_tables import render


HEADERS = ['PO#', 'Fty S/D', 'Destination port name', 'Item description',
           'VSK #', 'Revised Qty (Pcs)', 'Revised Total (Pcs)', 'Revised Grand Total (Pcs)']
ROWS = [
    ['0000810001', '2/26', 'Sample port', 'Sample\n\n toy', '71001', '24', '', ''],
    ['0000810002', '2/26', 'Sample port', 'Sample toy', '71001', '36', '60', '60'],
]
STAMP = date(2026, 11, 25)


@pytest.mark.parametrize('kind', ['html', 'tsv', 'pipe', 'vertical-pipe'])
def test_revised_groups_preserve_empty_cells_and_only_take_current_rows(kind):
    second = [[*row[:4], '71002', *row[5:]] for row in ROWS]
    old = [[row[0], '1/22', *row[2:5], '99999', '', '199998'] for row in ROWS]
    marker = '<p>---- Replied Message ----</p>' if kind == 'html' else '\n---- Replied Message ----\n'
    source = render(kind, ROWS, HEADERS) + render(kind, second, HEADERS) + marker + render(kind, old, HEADERS)
    result = parser.parse_order_email(source, 'WM US / monthly order', STAMP)
    rows = result['orders']
    assert result['meta']['table_count'] == 2
    assert [(r['baby_item'], r['customer_po'], r['qty']) for r in rows] == [
        ('71001', '0000810001', '24'), ('71001', '0000810002', '36'),
        ('71002', '0000810001', '24'), ('71002', '0000810002', '36'),
    ]
    assert all(r['cutoff_date'] == '2027/2/26' and r['ship_date'] == '2027/2/19' for r in rows)
    assert all(r['customer'] == 'WM US' and r['country'] == '美国' for r in rows)
    assert sum(int(r['qty']) for r in rows) == 120


@pytest.mark.parametrize('quantity_header', sorted(parser.MONTHLY_REVISED_QTY_HEADERS))
@pytest.mark.parametrize('old_first', [True, False])
def test_unique_revised_quantity_wins_over_old_quantity_and_totals(quantity_header, old_first):
    headers = [*HEADERS[:5], quantity_header, *HEADERS[6:]]
    row = ROWS[0][:]
    position = 5 if old_first else len(headers)
    headers.insert(position, 'Qty (Pcs)')
    row.insert(position, '999')
    parsed = parser.parse_order_email(render('html', [row], headers), 'WM US', STAMP)
    assert [r['qty'] for r in parsed['orders']] == ['24']


def test_empty_revised_quantity_never_falls_back_to_old_or_total():
    row = [*ROWS[0][:5], '', '1234', '5678', '999']
    result = parser.parse_order_email(render('html', [row], [*HEADERS, 'Qty (Pcs)']), 'WM US', STAMP)
    assert len(result['orders']) == 1 and result['orders'][0]['qty'] == ''


@pytest.mark.parametrize('header', ['Revised Total (Pcs)', 'Revised Grand Total (Pcs)', 'Previous Qty (Pcs)'])
def test_totals_and_previous_quantities_cannot_stand_in_for_current_line_quantity(header):
    headers = [*HEADERS[:5], header, *HEADERS[6:]]
    assert not parser.parse_order_email(render('html', ROWS, headers), 'WM US', STAMP)['orders']


def test_two_revised_quantity_columns_are_not_chosen_arbitrarily_even_with_old_qty():
    headers = [*HEADERS, 'Revised Quantity (Pcs)', 'Qty (Pcs)']
    rows = [row + ['200', '999'] for row in ROWS]
    assert not parser.parse_order_email(render('html', rows, headers), 'WM US', STAMP)['orders']


@pytest.mark.parametrize('kind', ['tsv', 'pipe', 'vertical-pipe'])
def test_revised_plain_rows_missing_a_cell_are_not_shifted_or_regrouped(kind):
    assert not parser.parse_order_email(render(kind, [ROWS[0], ROWS[1][:-1]], HEADERS), 'WM US', STAMP)['orders']


def test_vertical_pipe_blank_lines_inside_cells_and_table_footer_stay_separate():
    # Foxmail can add blank paragraphs around cell text, including empty cells.
    rows = [['\n' + value + '\n' for value in row] for row in ROWS]
    source = render('vertical-pipe', rows, HEADERS) + '\nThanks,\nSample sender\n'
    result = parser.parse_order_email(source, 'WM US', STAMP)
    assert [r['qty'] for r in result['orders']] == ['24', '36']
    assert all(r['description'] == 'Sample toy' for r in result['orders'])


@pytest.mark.parametrize('source', ['eml-html', 'eml-text', 'paste-html', 'paste-text'])
def test_revised_mail_and_paste_export_without_reference_or_confirmation(client, source):
    rich = source.endswith('html')
    body = render('html' if rich else 'vertical-pipe', ROWS, HEADERS)
    form = {'factory_id': 'huakang-b', 'received_date': '2026-11-25', 'merchandiser': '合成跟单',
            'subject': 'WM US monthly enquiry'}
    files = []
    if source.startswith('eml'):
        message = EmailMessage()
        message['Subject'] = form['subject']
        message['Date'] = 'Wed, 25 Nov 2026 09:00:00 +0800'
        message.set_content(body, subtype='html' if rich else 'plain')
        files = [('files', ('synthetic-revised.eml', message.as_bytes(), 'message/rfc822'))]
    else:
        form['html'] = body
    base = '/api/huakang-b-jp'
    response = client.post(base + '/preview', data=form, files=files)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert len(preview['rows']) == 2 and not preview['failed_sources']
    response = client.post(base + '/export', data={**form, 'fingerprint': preview['fingerprint'],
        'selected': json.dumps([r['id'] for r in preview['rows']])}, files=files)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['row_count'] == 2
    response = client.get(base + '/exports/' + saved['id'] + '/download', params={'factory_id': 'huakang-b'})
    assert response.status_code == 200
    book = openpyxl.load_workbook(BytesIO(response.content))
    sheet = book.active
    assert (sheet.max_row, sheet.max_column) == (3, 44)
    assert [sheet.cell(r, 3).value for r in (2, 3)] == ['0000810001', '0000810002']
    assert all(sheet.cell(r, 5).value == 'TBA' for r in (2, 3))
    assert [sheet.cell(r, 13).value for r in (2, 3)] == [24, 36]
    assert all(sheet.cell(r, 20).value == datetime(2027, 2, 26) for r in (2, 3))
    book.close()
