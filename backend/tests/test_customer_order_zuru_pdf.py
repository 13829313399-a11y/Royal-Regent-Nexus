"""Synthetic native PDFs exercise physical cells and source version selection."""
from io import BytesIO

import pytest
from reportlab.pdfgen import canvas

from app.services.customer_order_zuru import parse_po, select_versions, create_rows
from app.services.customer_order_zuru_pdf import _revisions


WIDTHS = [28, 45, 100, 165, 35, 75, 75, 50, 50, 60, 45, 85, 55]
UPPER = ['Line', 'SKU', 'SKU-SPEC', 'Name', 'Outer', 'Individual', 'Delivery', 'Price', 'QTY', 'Total', 'Total', 'Customer PO', 'Ship']
LOWER = ['', '', '', '', 'PCS', 'Barcode', 'Date', 'USD', 'PCS', 'USD', 'CTNS', '', 'Type']


def _grid(c, top, rows, heights, widths=WIDTHS):
    y = top
    for values, height in zip(rows, heights):
        x = 10
        for value, width in zip(values, widths):
            c.rect(x, y-height, width, height)
            for i, line in enumerate(str(value).split('\n')):
                c.drawString(x+2, y-10-i*8, line)
            x += width
        y -= height
    return y


def sample_pdf(*, bad_total=False, duplicate_line=False, tail=False, prefix=False, bare_po=False, spec_tail=False,
               title='ZURU PURCHASE ORDER', same_previous_barcode=False, wrong_spec_tail=False,
               extra_after_total=False, revision=0, qty=100):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(1000, 700), invariant=1)
    c.setFont('Helvetica', 7)
    c.drawString(10, 680, title)
    metadata = [['Date:', '2026-10-01'], ['ZURU Inc PO#', '4500999111'],
                ['Customer Name:', 'Synthetic Retail'], ['Shipment Date:', '2026-12-01'],
                ['Destination Country:', 'USA']]
    _grid(c, 660, metadata, [16]*5, [110, 400])
    line1 = ['10', '9560', '9560-S.001', 'Toy first', '4', '0012345678901', '2026-12-01', '2.5000', str(qty), str(qty*2.5), str(qty//4), '000001', 'Shipping']
    line2 = ['10' if duplicate_line else '20', '9560', '9560-S002', 'Toy second', '4', '0012345678902', '2026-12-01', '2.5000', '200', '500', '50', '000002', 'Shipping']
    total = ['Totals'] + ['']*7 + [str(qty+200+(1 if bad_total else 0)), str(qty*2.5+500), str(qty//4+50), '', '']
    if tail or prefix or bare_po or spec_tail:
        fragment = ['']*13
        if prefix:
            fragment[3], fragment[5], fragment[11] = 'Name prefix', line2[5], line2[11]
            if same_previous_barcode:
                fragment[5], fragment[11] = line1[5], line1[11]
            line2[5], line2[11] = '', ''
            _grid(c, 540, [UPPER, LOWER, line1, fragment], [20, 20, 65, 20])
            next_rows = [line2, total]
        else:
            fragment[11] = 'WRONGPO' if bare_po else ''
            fragment[3] = '' if bare_po else 'descriptive continuation'
            if spec_tail:
                line1[2], fragment[2] = '9560-S.00', '77903-S001' if wrong_spec_tail else '1-MB'
                line1[3] = 'S.001-MB-Toy first'
            _grid(c, 540, [UPPER, LOWER, line1], [20, 20, 65])
            next_rows = [fragment, line2, total]
        c.showPage(); c.setFont('Helvetica', 7)
        y = _grid(c, 680, next_rows, [40]*len(next_rows))
    else:
        rows = [UPPER, LOWER, line1, line2, total]
        if extra_after_total: rows.append(line1)
        y = _grid(c, 540, rows, [20, 20] + [65]*(len(rows)-2))
    c.drawString(10, y-20, 'Order Modifiable Records')
    c.drawString(10, y-30, 'Revision # Date: Comment:')
    for i in range(revision):
        c.drawString(10, y-40-i*10, f'{i+1} 2026/10/{i+1:02d} Updated delivery')
    c.drawString(10, y-60-revision*10, 'Special Requirements')
    c.save()
    return output.getvalue()


def test_native_cells_preserve_po_line_full_spec_and_money():
    parsed = parse_po('synthetic.pdf', sample_pdf())
    assert parsed['po'] == '4500999111'
    assert parsed['customer'] == 'Synthetic Retail'
    assert [(r['line'], r['spec'], r['customer_po']) for r in parsed['lines']] == [
        ('10', '9560-S.001', '000001'), ('20', '9560-S002', '000002')]
    assert sum(r['amount'] for r in parsed['lines']) == 750
    assert parsed['revision_history'] == []
    rows, _, template = create_rows([('synthetic.pdf', sample_pdf())], '2026-11-04', [])
    assert template == 'HUAXING_ZURU_PO_V2'
    assert rows[0]['id'] == 'huaxing-zuru-1'
    assert rows[0]['_zuru_customer'] is True and rows[0]['_huaxing_customer'] == 'zuru'
    assert '_huakang_customer' not in rows[0]
    assert '第1页' in rows[0]['lineage']['source']


@pytest.mark.parametrize('option,message', [('bad_total', '总计'), ('duplicate_line', '重复'),
                                          ('bare_po', '归属'), ('extra_after_total', '总计后')])
def test_native_invalid_source_never_returns_partial_file(option, message):
    with pytest.raises(ValueError, match=message):
        parse_po('synthetic.pdf', sample_pdf(**{option: True}))


def test_native_page_break_descriptive_tail_and_leading_fragment():
    parsed = parse_po('tail.pdf', sample_pdf(tail=True))
    assert parsed['lines'][0]['name'] == 'Toy first\ndescriptive continuation'
    assert parsed['lines'][1]['customer_po'] == '000002'
    parsed = parse_po('prefix.pdf', sample_pdf(prefix=True))
    assert parsed['lines'][1]['name'] == 'Name prefix\nToy second'
    assert parsed['lines'][1]['customer_po'] == '000002'
    assert parsed['lines'][0]['customer_po'] == '000001'
    parsed = parse_po('spec-tail.pdf', sample_pdf(spec_tail=True))
    assert parsed['lines'][0]['spec'] == '9560-S.001-MB'


def test_native_leading_fragment_cannot_borrow_previous_customer_po():
    with pytest.raises(ValueError, match='归属不明确'):
        parse_po('ambiguous.pdf', sample_pdf(prefix=True, same_previous_barcode=True))


def test_native_spec_tail_cannot_join_a_different_complete_product():
    with pytest.raises(ValueError, match='不能拼接其他货号'):
        parse_po('different-product.pdf', sample_pdf(spec_tail=True, wrong_spec_tail=True))


def test_revision_selection_uses_document_record_and_whole_po():
    old = parse_po('file-rev99.pdf', sample_pdf(revision=0))
    new = parse_po('file-rev1.pdf', sample_pdf(revision=1, qty=104))
    chosen, notes = select_versions([('file-rev99.pdf', old), ('file-rev1.pdf', new)])
    assert len(chosen) == 1 and chosen[0][0] == 'file-rev1.pdf'
    assert chosen[0][1]['lines'][0]['qty'] == 104
    assert '2026-10-01' in notes[0]
    assert select_versions([('new', new), ('old', old)])[0][0][0] == 'new'


def test_same_revision_different_sources_conflict_even_with_filename_hint():
    a = parse_po('rev1.pdf', sample_pdf(revision=1))
    b = parse_po('rev999.pdf', sample_pdf(revision=1, qty=104))
    with pytest.raises(ValueError, match='同版本'):
        select_versions([('rev1.pdf', a), ('rev999.pdf', b)])
    assert len(select_versions([('one.pdf', a), ('copy.pdf', a)])[0]) == 1


def test_revision_record_must_be_consistent_and_dates_valid():
    with pytest.raises(ValueError, match='矛盾'):
        _revisions('Order Modifiable Records\n1 2026/10/03 A\n2 2026/10/01 B\nSpecial Requirements')


@pytest.mark.parametrize('name,payload', [('fake.pdf', b'not PDF'), ('Cancel.pdf', sample_pdf())])
def test_reject_invalid_or_cancelled_pdf(name, payload):
    with pytest.raises(ValueError):
        parse_po(name, payload)


@pytest.mark.parametrize('title', ['ZURU CANCELLED PURCHASE ORDER', 'ZURU MPO', 'ZURU PALLET PURCHASE ORDER'])
def test_actual_document_title_is_checked_even_with_ordinary_filename(title):
    with pytest.raises(ValueError, match='标题'):
        parse_po('ordinary.pdf', sample_pdf(title=title))
