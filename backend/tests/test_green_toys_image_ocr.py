from decimal import Decimal
from io import BytesIO
from pathlib import Path
import os
import subprocess

from PIL import Image, ImageDraw, ImageOps
import pytest

from app.services.huakang_a_order_legacy import green_toys_headstart as parser
from app.services.huakang_a_order_legacy import green_toys_image_ocr as ocr


HEADER = 'Green Toys, Inc\nPO #\n9876\nPO Date\n10/1/2026\nDeliver By Date\n11/10/2026'


def ruled_image(scale=1, padding=20):
    image = Image.new('L', (1000 + 2 * padding, 320), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((padding, 100, padding + 1000, 119), fill=150)
    for y in (150, 180, 210):
        draw.line((padding, y, padding + 1000, y), fill=100)
    for x in (0, 100, 350, 500, 600, 750, 870, 1000):
        draw.line((padding + x, 100, padding + x, 210), fill=100)
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)


def tsv(values, intervals, crop_top):
    lines = ['level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext']
    for n, ((start, end), value) in enumerate(zip(intervals, values), 1):
        if not value:
            continue
        # Different glyph tops on the same line must not reverse text order.
        for i, token in enumerate(value.split()):
            top = int(((start + end) / 2 - crop_top) * 3 + 15) - 5 + i % 2
            lines.append(f'5\t1\t1\t{n}\t{15 + i * 50}\t{top}\t30\t10\t95\t{token}')
    return '\n'.join(lines)


def recognize_mock(tmp_path, monkeypatch, *, scale=1, padding=20, header=HEADER,
                   descriptions=None, quantities=None, prices=None, amounts=None,
                   footer='Total $60.00', items=None, titles=None):
    image = ruled_image(scale, padding)
    path = tmp_path / '20261005144325.png'
    image.save(path)
    _, _, _, intervals = ocr._layout(image)
    crop_top = intervals[0][0]
    payloads = [header] + (titles or ['Description', 'Order Quantity', 'Unit Price', 'Amount'])
    for values in (descriptions or ['Toy One', 'Toy Two', 'Toy Three'],
                   quantities or ['10', '10', '10'], prices or ['1.00', '2.00', '3.00'],
                   amounts or ['10.00', '20.00', '30.00']):
        payloads.append(tsv(values, intervals, crop_top))
    payloads += [footer] + (items or ['AA-1', 'BB-2', 'CC-3'])
    iterator = iter(payloads)
    monkeypatch.setattr(ocr._Reader, 'read', lambda *_args, **_kwargs: next(iterator, ''))
    before = path.read_bytes()
    result = ocr.recognize_green_toys_image(path, 'tesseract')
    assert path.read_bytes() == before
    return result


@pytest.mark.parametrize('scale,padding', [(1, 20), (2, 20), (1, 150)])
def test_layout_is_detected_not_fixed_and_all_rows_roundtrip(tmp_path, monkeypatch, scale, padding):
    text = recognize_mock(tmp_path, monkeypatch, scale=scale, padding=padding)
    rows = parser.parse_green_toys_ocr_text('20261005144325.png', text, verified_image_columns=True)
    assert len(rows) == 3
    assert [r['description'] for r in rows] == ['Toy One', 'Toy Two', 'Toy Three']
    assert all(r['contract_no'] == '9876' and r['parse_ok'] and r['parse_warnings'] for r in rows)
    assert sum(Decimal(str(r['amount_usd'])) for r in rows) == Decimal('60.00')


@pytest.mark.parametrize('changes', [
    {'header': HEADER.replace('PO #\n9876', '')},
    {'header': HEADER + '\nPO # 8765'},
    {'header': HEADER.replace('10/1/2026', '2/30/2026')},
    {'header': HEADER.replace('Green Toys', 'Other Company')},
    {'titles': ['Description', 'Order Quantity', 'Subtotal', 'Amount']},
    {'quantities': ['10', '', '10']},
    {'quantities': ['10', '1O', '10']},
    {'quantities': ['10', '10.5', '10']},
    {'prices': ['1.00', '200', '3.00']},
    {'amounts': ['10.00', '2,000.00', '30.00']},
    {'footer': 'Total $40.00'},
    {'footer': ''},
    {'footer': 'Total $60.00 $40.00'},
    {'items': ['AA-1', '', 'CC-3']},
], ids=['missing-po', 'conflicting-po', 'invalid-date', 'wrong-customer', 'wrong-layout',
        'missing-cell', 'ambiguous-digit', 'fractional-quantity', 'lost-decimal', 'line-amount',
        'partial-total', 'missing-total', 'multiple-totals', 'unreadable-item'])
def test_incomplete_or_inconsistent_image_is_rejected(tmp_path, monkeypatch, changes):
    with pytest.raises(ocr.GreenImageError):
        recognize_mock(tmp_path, monkeypatch, **changes)


@pytest.mark.parametrize('name', ['7848.png', '20261005144325.jpg'])
def test_filename_never_substitutes_for_a_missing_po(name):
    with pytest.raises(parser.HuakangASpecialCustomerError, match='文件名'):
        parser.parse_green_toys_ocr_text(name, 'PO Date 10/1/2026\nAA-1 Toy 10 0 1.00 10.00\nTotal $10.00')


def test_normalized_item_not_silently_discarded():
    text = 'PO # 9876\nPO Date 10/1/2026\nDeliver By Date 11/10/2026\nDTKOIR Toy 10 0 1.00 10.00\nTotal $10.00'
    assert parser.parse_green_toys_ocr_text('timestamp.png', text)[0]['item_no'] == 'DTK01R'


def test_metadata_handles_ocr_equals_label_but_rejects_missing_po():
    assert ocr._metadata(HEADER.replace('PO #', 'PO ='))['po'] == '9876'
    with pytest.raises(ocr.GreenImageError):
        ocr._metadata(HEADER.replace('PO #\n9876', 'Reference 20261005144325'))


@pytest.mark.parametrize('following', ['', '\nMemo-Detail\nTerms', '\nCancel Date\n12/31/2026'])
def test_empty_delivery_image_keeps_every_row_and_pending_dates(tmp_path, monkeypatch, following):
    header = HEADER.replace('\n11/10/2026', '') + following
    text = recognize_mock(tmp_path, monkeypatch, header=header)
    rows = parser.parse_green_toys_ocr_text('timestamp.png', text, verified_image_columns=True)
    assert len(rows) == 3
    assert sum(Decimal(str(r['amount_usd'])) for r in rows) == Decimal('60.00')
    for row in rows:
        assert row['parse_ok'] and row['contract_no'] == '9876'
        assert row['order_date'] == '2026-10-01'
        assert row['factory_commit_date'] == row['planned_inspection_date'] == ''
        issues = parser.issues_for_record('green-toys', 'Green Toys', row, row['customer_po'])
        assert not any(issue['severity'] == 'blocked' for issue in issues)
        assert any(issue['code'] == 'missing_requested_ship_date' and issue['severity'] == 'warning' for issue in issues)


def test_complete_multiword_item_stays_in_its_cell_not_description(tmp_path, monkeypatch):
    text = recognize_mock(tmp_path, monkeypatch, items=['AA-1 Inv It', 'BB-2', 'CC-3'])
    rows = parser.parse_green_toys_ocr_text('timestamp.png', text, verified_image_columns=True)
    assert rows[0]['item_no'] == 'AA-1 Inv It'
    assert rows[0]['description'] == 'Toy One'
    assert rows[0]['quantity'] == 10
    assert parser._reconcile_green_item(rows[0], {'AA1': [{'item_no': 'AA-1', 'description': 'Toy One'}]}) == 'AA-1 Inv It'


def test_column_aligned_ocr_candidate_stays_visible_until_history_or_manual_review(tmp_path, monkeypatch):
    text = recognize_mock(tmp_path, monkeypatch, items=['ABCOIR', 'BB-2', 'CC-3'])
    rows = parser.parse_green_toys_ocr_text('timestamp.png', text, verified_image_columns=True)
    assert len(rows) == 3 and sum(Decimal(str(r['amount_usd'])) for r in rows) == Decimal('60')
    row = rows[0]
    assert row['item_no'] == row['_ocr_item_no'] == 'ABCOIR'
    issues = parser.issues_for_record('green-toys', 'Green Toys', row, '1')
    issue = next(i for i in issues if i['code'] == 'ocr_product_uncertain')
    assert issue['field'] == 'product_no' and issue['severity'] == 'blocked' and not issue['can_skip']
    row['item_no'] = parser._reconcile_green_item(row, {'ABC01R': [{'item_no': 'ABC01R', 'description': 'Toy One'}]})
    assert row['item_no'] == 'ABC01R' and row['_ocr_item_no'] == 'ABCOIR'
    assert not any(i['code'] == 'ocr_product_uncertain' for i in parser.issues_for_record('green-toys', 'Green Toys', row, '1'))


def test_numeric_cell_retry_requires_two_matching_reads():
    image = ruled_image()
    _, _, columns, intervals = ocr._layout(image)
    class Reader:
        def __init__(self, tokens):
            self.tokens = iter(tokens)
            self.calls = []
        def read(self, _image, **options):
            self.calls.append(options)
            return next(self.tokens)
    reader = Reader(['3,000', '3.35', '10,050.00'] * 2)
    result = ocr._read_row_numbers(['3,000', '3235', '10,050.00'], 1, image, columns, intervals[0], reader)
    assert result == (Decimal('3000'), Decimal('3.35'), Decimal('10050'))
    assert reader.calls == [{'psm': 7, 'scale': 2}] * 3 + [{'psm': 7, 'scale': 3}] * 3
    # Both alternatives pass arithmetic and have the same amount; they still
    # cannot establish a quantity or price when the independent reads disagree.
    reader = Reader(['10', '2', '20.00', '20', '1', '20.00'])
    with pytest.raises(ocr.GreenImageError, match='不一致'):
        ocr._read_row_numbers(['10', '200', '20.00'], 1, image, columns, intervals[0], reader)
    reader = Reader(['10', '2O', '20.00'])
    with pytest.raises(ocr.GreenImageError, match='不会自动猜数'):
        ocr._read_row_numbers(['10', '200', '20.00'], 1, image, columns, intervals[0], reader)


def test_numeric_retry_keeps_existing_deadline_and_skips_valid_rows():
    image = ruled_image()
    _, _, columns, intervals = ocr._layout(image)
    reader = ocr._Reader('unused')
    reader.deadline = 0
    assert ocr._read_row_numbers(['10', '2', '20.00'], 1, image, columns, intervals[0], reader) == (10, 2, 20)
    with pytest.raises(ocr.GreenImageError, match='超时'):
        ocr._read_row_numbers(['10', '200', '20.00'], 1, image, columns, intervals[0], reader)


@pytest.mark.parametrize('price,amount', [('3.533', '10.60'), ('100', '300.00')])
def test_verified_column_price_is_not_rederived_or_scaled(price, amount):
    text = HEADER + f'\nAA-1  Test Item  3  0  {price}  {amount}\nTotal ${amount}'
    row = parser.parse_green_toys_ocr_text('image.png', text, verified_image_columns=True)[0]
    assert Decimal(str(row['unit_price_usd'])) == Decimal(price)
    assert Decimal(str(row['amount_usd'])) == Decimal(amount)


@pytest.mark.parametrize('line', [
    'AA-1  Test Item  5,000|  0  2.788  13,945.00',
    'AA-1  Test Item  5,000  0  2.788  13,945.00',
    'AA-1  Test Item  3,000  0  441  13,27',
    'AA-1 Test Item 5000 0 2.788 13945.00',
], ids=['noisy-number', 'contradictory-price', 'lost-decimal', 'lost-columns'])
def test_image_adapter_never_falls_back_to_legacy_numeric_inference(monkeypatch, line):
    # Historical text OCR tolerates these artifacts. An image reader output
    # must never regain those transformations, even if its shape is broken.
    text = 'PO # 9876\nPO Date 10/1/2026\nDeliver By Date\n' + line + '\nTotal $13,945.00'
    monkeypatch.setattr(parser, '_ocr_green_toys_image', lambda _path: text)
    with pytest.raises(parser.HuakangASpecialCustomerError):
        parser.parse_green_toys_po('actual.png', b'local mock image')


@pytest.mark.parametrize('replacement', ['', 'Deliver By Date\n2/30/2026',
    'Deliver By Date\n1O/10/2026', 'Deliver By Date\nnot-readable',
    'Deliver By Date 11/10/2026\n12/10/2026\nMemo-Detail',
    'Deliver By Date 11/10/2026\nnot-readable\nTerms',
    'Deliver By Date 11/10/2026\nDeliver By Date 12/10/2026'])
def test_delivery_missing_label_invalid_or_conflicting_is_not_a_blank(replacement):
    with pytest.raises(ocr.GreenImageError):
        ocr._metadata(HEADER.replace('Deliver By Date\n11/10/2026', replacement))


def test_cell_coordinates_preserve_wrapped_description_and_missing_row():
    intervals = [(10, 40), (41, 70), (71, 100)]
    source = tsv(['First Item', '', 'Third Item'], intervals, 10)
    assert ocr._column_rows(source, intervals, 10) == ['First Item', '', 'Third Item']
    outside = source.replace('\ttop\t', '\tunknown\t')
    with pytest.raises(ocr.GreenImageError):
        ocr._column_rows(outside, intervals, 10)


def test_bad_layout_and_oversized_image_are_rejected(tmp_path):
    with pytest.raises(ocr.GreenImageError):
        ocr._layout(Image.new('L', (400, 200), 'white'))
    path = tmp_path / 'oversized.png'
    Image.new('L', (3000, 3000), 'white').save(path)
    with pytest.raises(ocr.GreenImageError, match='过大'):
        ocr.recognize_green_toys_image(path, 'unused')


def test_empty_region_and_truncated_footer_are_rejected():
    with pytest.raises(ocr.GreenImageError, match='为空'):
        ocr._Reader('unused').read(Image.new('L', (20, 0)))
    image = ruled_image().crop((0, 0, 1040, 211))
    with pytest.raises(ocr.GreenImageError, match='截断'):
        ocr._layout(image)


def test_ocr_has_bounded_deadline_and_single_thread(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, b'text', b'')
    monkeypatch.setattr(ocr.subprocess, 'run', run)
    reader = ocr._Reader('tesseract')
    assert reader.read(Image.new('L', (10, 10), 'white')) == 'text'
    assert calls[0][1]['env']['OMP_THREAD_LIMIT'] == '1'
    assert 0 < calls[0][1]['timeout'] <= 15
    assert calls[0][0][-3:] == ['eng', '--psm', '6']
    reader.deadline = 0
    with pytest.raises(ocr.GreenImageError, match='超时'):
        reader.read(Image.new('L', (10, 10), 'white'))
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['timeout', 'unavailable', 'failed'])
def test_engine_errors_fail_closed(monkeypatch, failure):
    def run(args, **_kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(args, 1)
        if failure == 'unavailable':
            raise FileNotFoundError('not installed')
        return subprocess.CompletedProcess(args, 1, b'', b'private document/path')
    monkeypatch.setattr(ocr.subprocess, 'run', run)
    with pytest.raises(ocr.GreenImageError) as error:
        ocr._Reader('tesseract').read(Image.new('L', (10, 10), 'white'))
    assert 'private' not in str(error.value)


def test_real_tesseract_upload_matches_original_html_and_exports_all_rows():
    """Opt-in local evidence: customer files are never stored in this repository."""
    if not all(os.environ.get(key) for key in ('TESSERACT_CMD', 'GREEN_TOYS_REAL_IMAGE', 'GREEN_TOYS_REAL_HTML')):
        pytest.skip('Set local Tesseract and original image/HTML paths to run real OCR verification')
    from test_green_toys_po_integrity import recovery_template
    from app.services import customer_order_unified as service
    import openpyxl

    image = Path(os.environ['GREEN_TOYS_REAL_IMAGE']).read_bytes()
    native = Path(os.environ['GREEN_TOYS_REAL_HTML']).read_bytes()
    expected = parser.parse_green_toys_po('original.html', native)
    actual = parser.parse_green_toys_po('20261005144325.png', image)
    fields = ('contract_no', 'customer_po', 'item_no', 'description', 'quantity', 'unit_price_usd',
              'amount_usd', 'order_date', 'factory_commit_date', 'planned_inspection_date')
    assert [[r[k] for k in fields] for r in actual] == [[r[k] for k in fields] for r in expected]
    args = dict(customer_code='green-toys', factory_id='huakang-a', received_date='2026-10-06',
                po_files=[('20261005144325.png', image)], schedule_file_name='Green Toys.xlsx',
                schedule_content=recovery_template())
    preview = service.create_unified_customer_preview(**args)
    assert preview['summary']['total'] == 8 and preview['summary']['blocked'] == 0
    refs = {r['product_no']: r['po_no'] for r in preview['rows']}
    assert refs['HELB-1060'] == '7848-5'  # historic suffix, not OCR line number
    output, _, _ = service.export_unified_customer_schedule(**args)
    book = openpyxl.load_workbook(BytesIO(output))
    item = book[service.ITEM_SHEET]
    details = {r[7].value: r[0].row for r in item if r[3].value == '7848'}
    assert set(details) == {r['item_no'] for r in expected}
    assert item['F4'].value == '7816-14-1'
    for name in (service.ORDER_SHEET, service.REVIEW_SHEET):
        summary = [r for r in book[name] if r[2].value == '7848']
        assert len(summary) == 8
        assert book[name]['N4'].value == book[name]['N5'].value == 99
        for row in summary:
            detail = details[row[6].value]
            assert row[9].value == f'=IF(LEN(\'ITEM表\'!K{detail})=0,"",\'ITEM表\'!K{detail})'
    book.close()


@pytest.mark.parametrize('variant', ['white-padding', 'jpeg', 'double-resolution'])
def test_real_image_variants_preserve_every_field(variant):
    if not all(os.environ.get(key) for key in ('TESSERACT_CMD', 'GREEN_TOYS_REAL_IMAGE', 'GREEN_TOYS_REAL_HTML')):
        pytest.skip('Local original image/HTML and Tesseract are required')
    with Image.open(os.environ['GREEN_TOYS_REAL_IMAGE']) as source:
        image = source.convert('RGB')
    if variant == 'white-padding':
        image = ImageOps.expand(image, 40, 'white')
    elif variant == 'double-resolution':
        image = image.resize((image.width * 2, image.height * 2))
    buffer = BytesIO()
    image.save(buffer, format='JPEG' if variant == 'jpeg' else 'PNG')
    actual = parser.parse_green_toys_po('timestamp.jpg' if variant == 'jpeg' else 'timestamp.png', buffer.getvalue())
    expected = parser.parse_green_toys_po('original.html', Path(os.environ['GREEN_TOYS_REAL_HTML']).read_bytes())
    fields = ('contract_no', 'item_no', 'description', 'quantity', 'unit_price_usd', 'amount_usd',
              'order_date', 'factory_commit_date')
    assert [[row[key] for key in fields] for row in actual] == [[row[key] for key in fields] for row in expected]
