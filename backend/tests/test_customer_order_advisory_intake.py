"""Cross-factory reminder-only intake preserves source rows and prior orders."""
from copy import deepcopy
from io import BytesIO

import openpyxl
import pytest
from sqlalchemy import select, func

from app.services import customer_order_unified as unified
from app.services import customer_order_huaxing_unified as huaxing
from app.services import customer_order_ledger as ledger
from app.models.customer_order_ledger import OrderLedgerLine as Line
from test_customer_order_unified import _parsed_row, _template_bytes
from test_customer_order_ledger import db, engine, ingest, preview as ledger_preview


@pytest.mark.parametrize('factory,customer', [
    ('huaxing', code) for code in ('caixing', 'dickie', 'zuru', 'disney', 'seasons', 'maxx', 'barter')
] + [('huakang-a', 'green-toys'), ('huakang-a', 'headstart'), ('huakang-d', 'maxx'),
     ('huakang-d', 'strottman'), ('huadeng', 'simba'), ('huakang-c', 'maxx')])
def test_quantity_conflicts_and_missing_packaging_export_each_original_row(monkeypatch, factory, customer):
    first = _parsed_row()
    first.update(reference_no='OE-1932886', contract_no='OE-1932886', po_no='OE-1932886', product_no='58174 A', quantity='120', packaging='', item_sheet_name='ITEM表')
    first['issues'] = [dict(severity='blocked', code='missing_packaging', field='packaging',
        message='未从 PO REMARKS 识别到包装要求', can_skip=False)]
    second = {**deepcopy(first), 'id': 'second', 'quantity': '240'}
    if huaxing.enabled(factory, customer):
        for row in (first, second):
            row['_huaxing_customer'] = customer
    monkeypatch.setattr(unified, '_create_customer_rows', lambda *_: ([deepcopy(first), deepcopy(second)], [], 'SYNTHETIC'))
    output, _, result = unified.export_unified_customer_schedule(customer_code=customer, factory_id=factory,
        received_date='2026-11-16', po_files=[('1932886.pdf', b'synthetic')],
        schedule_file_name='schedule.xlsx', schedule_content=_template_bytes())
    assert result['summary']['blocked'] == result['confirmation_count'] == 0
    assert any(i['code'] == 'existing_quantity_conflict' for r in result['rows'] for i in r['issues'])
    assert all(i['severity'] == 'warning' for r in result['rows'] for i in r['issues'])
    book = openpyxl.load_workbook(BytesIO(output))
    item = book['ITEM表']
    added = [r for r in range(4, item.max_row + 1) if item.cell(r, 8).value == '58174 A']
    assert len(added) == 2 and [item.cell(r, 11).value for r in added] == [120, 240]
    for name in ('接单表', '正单评审表'):
        assert sum(book[name].cell(r, 7).value == '58174 A' for r in range(4, book[name].max_row + 1)) == 2
    assert item['E4'].value == 'SO-DEMO-4'
    book.close()


def test_unclassified_rows_are_preserved_without_guessing_a_lane():
    from test_customer_order_huaxing_unified import template
    book = template('buzzbee')
    row = _parsed_row()
    row.update(item_sheet_name='', _huaxing_customer='buzzbee')
    huaxing.export_rows(book, [row])
    assert book['ITEM待补资料']['H4'].value == row['product_no']
    assert book['接单表']['D4'].value == row['reference_no']
    assert "ITEM待补资料" in book['接单表']['J4'].value
    assert all(book[name]['H4'].value is None for name in huaxing.BUZZBEE_SHEETS)


@pytest.mark.parametrize('quantity', ['', '0', '-1', 'NaN'])
def test_missing_identity_and_invalid_quantity_are_saved_as_pending_source_facts(db, quantity):
    payload = ledger_preview(qty=quantity, reference='')
    payload['rows'][0].update(product_no='', po_no='')
    def save():
        return ledger.import_preview(db, preview=payload, files=[('original.pdf', b'original', 'formal')],
            source_kind='formal', actor='test', reason='', controls={})
    result = save(); db.commit()
    stored = db.get(Line, result['items'][0]['id'])
    assert stored.quantity is None and stored.reference_no == stored.product_no == ''
    assert stored.data['quantity'] == quantity and stored.data['intake_notice']
    again = save(); db.commit()
    assert again['items'][0]['id'] == stored.id
    assert db.scalar(select(func.count()).select_from(Line)) == 1


def test_retry_keeps_its_variant_after_the_original_order_is_amended(db):
    from app.schemas.customer_order_ledger import AmendIn
    original = ingest(db, ledger_preview(qty='100'))
    incoming = ledger_preview(qty='200')
    variant = ingest(db, incoming)
    assert variant.id != original.id
    ledger.amend(db, original, AmendIn(expected_revision=original.revision, quantity='200',
        requested_ship_date='2026-10-01', note='', reason='客户后来修改数量'), 'test')
    db.commit()
    assert ingest(db, incoming).id == variant.id
    assert original.version == 2 and variant.version == 1
    assert db.scalar(select(func.count()).select_from(Line)) == 2


def test_retry_keeps_its_variant_after_that_variant_is_explicitly_amended(db):
    from app.schemas.customer_order_ledger import AmendIn
    original = ingest(db, ledger_preview(qty='100'))
    incoming = ledger_preview(qty='200')
    variant = ingest(db, incoming)
    ledger.amend(db, variant, AmendIn(expected_revision=variant.revision, quantity='250',
        requested_ship_date='2026-10-01', note='', reason='客户修订后续数量'), 'test')
    db.commit()
    assert ingest(db, incoming).id == variant.id
    assert variant.quantity == 250 and variant.version == 2
    assert original.quantity == 100 and original.version == 1
    assert db.scalar(select(func.count()).select_from(Line)) == 2


def test_green_conflicting_lines_cannot_share_recovered_summary_slots(monkeypatch):
    book = openpyxl.load_workbook(BytesIO(_template_bytes()))
    for name in ('接单表', '正单评审表'):
        for col, value in enumerate(('7855', '7855-1', '7855-1', 'GT', 'P1'), 3):
            book[name].cell(7, col).value = value
    buffer = BytesIO(); book.save(buffer); book.close()
    rows = []
    for index, qty in enumerate(('120', '240')):
        row = _parsed_row(index + 1)
        row.update(contract_no='7855', reference_no='7855', po_no='7855', product_no='P1', quantity=qty)
        rows.append(row)
    monkeypatch.setattr(unified, '_create_customer_rows', lambda *_: (deepcopy(rows), [], 'SYNTHETIC'))
    output, _, result = unified.export_unified_customer_schedule(customer_code='green-toys', factory_id='huakang-a',
        received_date='2026-11-16', po_files=[('7855.pdf', b'synthetic')],
        schedule_file_name='schedule.xlsx', schedule_content=buffer.getvalue())
    book = openpyxl.load_workbook(BytesIO(output))
    for name in ('接单表', '正单评审表'):
        sheet = book[name]
        assert sheet.cell(7, 4).value == '7855-1'
        added = [r for r in range(8, sheet.max_row + 1) if sheet.cell(r, 7).value == 'P1']
        assert len(added) == 2
        assert sheet.cell(added[0], 10).value != sheet.cell(added[1], 10).value
    assert result['summary']['blocked'] == 0
    assert any(i['code'] == 'green_summary_difference' for r in result['rows'] for i in r['issues'])
    book.close()


@pytest.mark.parametrize('qf_qty,po_qty,expected', [(None, 50, (None, 50, None)), (100, None, (100, None, None)), ('', 50, (None, 50, None)), (100, 'NaN', (100, None, None))])
def test_seasons_pending_quantity_remains_unknown_in_derived_totals(qf_qty, po_qty, expected):
    from app.services.huaxing_order_legacy import shixin_schedule as seasons
    qf = dict(item_no='P1', oqf_no='QF1', quantity=qf_qty, unit_price=None, amount=None)
    po = dict(item_no='P1', oqf_no='QF1', po_no='PO1', quantity=po_qty, unit_price=None, amount=None)
    records = [seasons.add_state(r, preserve_missing=True) for r in (qf, po)]
    assert records[0]['quantity'] == qf_qty and records[1]['quantity'] == po_qty
    assert all(r['unit_price'] is None and r['amount'] is None for r in records)
    result = seasons.reconcile_documents([dict(records=records)], [], preserve_differences=True)
    for row in result['records']:
        assert tuple(row[key] for key in ('qf_quantity', 'po_total', 'remaining_qf')) == expected


def test_seasons_recognized_missing_fields_and_conflicting_sources_are_retained(monkeypatch):
    from app.services.huaxing_order_legacy import shixin_schedule as seasons
    monkeypatch.setattr(seasons, '_pdf_text', lambda _: ('ORDER', 1))
    monkeypatch.setattr(seasons, '_document_header', lambda *_: {})
    monkeypatch.setattr(seasons, '_parse_document_lines', lambda *_: [dict(item_no='P1', po_no='P1', quantity=None)])
    parsed = seasons.parse_order_documents(b'original', 'PO.pdf', allow_pending=True)
    assert len(parsed['records']) == 1 and parsed['records'][0]['quantity'] is None
    assert parsed['warnings'] and not parsed['rejected_records']
    first = dict(item_no='P1', po_no='PO1', oqf_no='QF1', quantity=100)
    second = dict(first, quantity=200)
    result = seasons.reconcile_documents([dict(records=[first, second])], [], preserve_differences=True)
    assert [r['quantity'] for r in result['records']] == [100, 200]
    assert all(r['remaining_qf'] is None for r in result['records'])


@pytest.mark.parametrize('adapter', ['huakang_c', 'huadeng', 'huaxing', 'disney', '360'])
def test_same_revision_different_source_quantities_are_never_selected_by_filename(adapter):
    from app.services import customer_order_huakang_c as hc, customer_order_huadeng as hd, customer_order_huaxing as hx
    from app.services.huaxing_order_legacy import disney_schedule as disney, three_sixty_po_parser as threesixty
    rows = [dict(po_number='PO1', customer_code='test', filename=f'{name}.pdf', revision=0,
        rows=[dict(quantity=qty)], lines=[dict(qty=qty)]) for name, qty in [('A', 100), ('B', 200)]]
    if adapter == 'huakang_c':
        kept, _ = hc._deduplicate(rows)
    elif adapter == 'huadeng':
        kept, _ = hd._dedupe_revision_orders(rows, quality_fields=())
    elif adapter == 'huaxing':
        kept, _ = hx._dedupe_multi_orders(rows)
    elif adapter == 'disney':
        kept, _ = disney.merge_revisions(rows)
    else:
        kept = threesixty.merge_po_results([dict(document_type='release', rows=[dict(production_no='RL1',
            release_revision=0, item_no='P1', quantity=qty)]) for qty in (100, 200)])
    assert len(kept) == 2
