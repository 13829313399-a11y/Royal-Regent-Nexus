from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from app.services import customer_order_unified as service
from app.services.huakang_a_order_legacy import schedule_parser, unified_schedule as mapping
from app.services.huakang_a_order_legacy.po_requirements import extract_requirements


@pytest.mark.parametrize('release,expected', [
    ('PO#TBD (Liverpool)', 'Liverpool'),
    ('PO# TBD (Farmers), FC-52899', 'Farmers'),
    ('TBD (TJX AU),FC-53161', 'TJX AU'),
    ('PO#TBA (FC-51966 Palacio Mexico)', 'Palacio Mexico'),
    ("TBD (Marvin's Magic-Amazon),FC-53630", "Marvin's Magic-Amazon"),
    ('PO (Client (DI)), FC-123', 'Client (DI)'),
])
def test_explicit_cinv_customer_parentheses(release, expected):
    assert extract_requirements('', 'CINV', release)['customer_name'] == expected


def test_end_customer_precedence_and_no_guessed_customer():
    assert extract_requirements('End Customer : Explicit (DI)', 'CINV', 'PO (Other)')['customer_name'] == 'Explicit (DI)'
    assert extract_requirements('', 'MSL1', 'PO (Not an identified customer)')['customer_name'] == ''
    assert extract_requirements('', 'CINV', 'FC-123')['customer_name'] == ''


def test_upc_ean_strings_not_itf_sscc_or_price_sticker_code():
    r = extract_requirements('EAN Code : 0012345678901\nITF Code : 10012345678908\nMS SSCC : 12345', 'CINV', '')
    assert r['barcode'] == '0012345678901'
    r = extract_requirements('UPC Code: 001234567890\n-UPC code on price sticker: TBA', 'MSL1', '')
    assert r['barcode'] == '001234567890'
    assert extract_requirements('ITF Code: 123456789\nSCC-14: 12345678', 'MSL1', '')['barcode'] == ''


def test_conflicting_barcodes_stay_blank_and_do_not_inherit():
    r = extract_requirements('UPC Code: 001234567890\nEAN Code: 0098765432101', 'CINV', '')
    assert r['barcode'] == '' and r['_360_barcode_conflict']
    row = {'customer_name': 'Client', 'product_no': 'ITEM', '_360_barcode_conflict': True}
    mapping.enrich_360_requirements(row, [service.UnifiedHistoryRow(row=4, customer_name='Client', product_no='ITEM', extras={'barcode':'111'})])
    assert not row.get('barcode')


def test_instruction_warning_and_conditional_labels_survive_page_header():
    t = '''IM : Spanish Safety Warning + QR : No SW + No QR
Artwork : International Brand Style Guide : MB
Factory Address : Some factory in China
1. IM Type: Spanish IM (no need English IM). NOM IM for battery-operated products.
2. Importer Label: for non-battery items, on product / color box / Spanish IM,
Unremovable and black on
28/F, Harbourside HQ,
8 Lam Chak Street,
PURCHASE ORDER RELEASE (CINV)RL-123-1 - REVISION 0 Kowloon Bay,
Hong Kong
Tel +852 123
PURCHASER: ThreeSixty Sourcing Limited
Page 3 of 5
white
3. NOM Label: Only for battery-operated items, provided by customer
Factory Commit Date History:
'''
    r = extract_requirements(t, 'CINV', 'PO (Client)')
    assert 'IM : Spanish' in r['manual']
    assert 'No SW + No QR' in r['manual']
    assert 'NOM IM for battery-operated products' in r['manual']
    assert 'non-battery items' in r['label']
    assert 'black on white' in r['label']
    assert 'Only for battery-operated items, provided by customer' in r['label']
    assert 'PURCHASE ORDER' not in r['label']
    assert r['standard'] == r['product_packaging'] == ''


def test_yalla_label_scope_and_no_stickers_not_master_carton():
    t = '''Factory Address : Factory
1. Sticker:
- Color box: Just the color box need the GCC QR Code Label.
- product & PP bag: Don't need the QR code after checking with the customer.
- Arabic Warning should be added to the poly bag (if available)
Factory Commit Date History:
'''
    r = extract_requirements(t, 'CINV', '')
    assert "Don't need the QR code" in r['label'] and '(if available)' in r['label']
    r = extract_requirements('Factory Address : Factory\nNo stickers -POE China -SSCC Barcode labeled on master carton\nFactory Commit Date History:', 'MSL1', '')
    assert r['label'] == 'No stickers'
    assert r['customer_label'] == ''  # Dedicated page-aware reader owns SSCC.
    assert 'SSCC' not in r['label']


def test_explicit_standard_packaging_not_artwork():
    r = extract_requirements('Factory Address : X\nQuality Standard: EU Standard Quality\nPackaging: International Standard Packaging; QR code and SW required\nFactory Commit Date History:', 'CINV', '')
    assert r['standard'] == 'EU Standard Quality'
    assert r['product_packaging'] == 'International Standard Packaging'
    r = extract_requirements('Package Type : Open Tray\nArtwork : Window Box', 'MSL1', '')
    assert r['product_packaging'] == 'Open Tray' and r['standard'] == ''


def test_numbered_carton_only_labels_not_product_and_no_sticker_exceptions_kept():
    r = extract_requirements('Factory Address : X\n1. Importer label on master carton, provided by customer\nFactory Commit Date History:', 'MSL1', '')
    assert r['label'] == ''
    assert r['customer_label'] == 'Importer label on master carton, provided by customer'
    r = extract_requirements('Factory Address : X\nNo stickers except a price tag if supplied by customer\nFactory Commit Date History:', 'MSL1', '')
    assert 'except a price tag if supplied by customer' in r['label']


def test_same_customer_history_only_no_cross_market_or_progress():
    history = [service.UnifiedHistoryRow(row=4, customer_name='Client', product_no='ITEM', standard='EU', packaging='Box',
        extras={'manual':'English', 'barcode':'00123', 'label':'欠价贴'}),
        service.UnifiedHistoryRow(row=5, customer_name='Other', product_no='ITEM', standard='US', packaging='Tray', extras={'manual':'Spanish','barcode':'999'})]
    row = {'customer_name':'Client', 'product_no':'ITEM', 'issues':[]}
    mapping.enrich_360_requirements(row, history)
    assert [row[x] for x in ('standard','packaging','manual','barcode')] == ['EU','Box','English','00123']
    assert not row.get('label')
    assert '第4行' in row['lineage']['manual']
    row = {'customer_name':'Unknown', 'product_no':'ITEM', 'issues':[]}
    mapping.enrich_360_requirements(row, history[:1])
    assert not any(row.get(x) for x in ('standard','packaging','manual','barcode'))


def test_source_wins_and_conflicting_history_stays_blank():
    h = [service.UnifiedHistoryRow(row=4, customer_name='Client', product_no='ITEM', standard='EU', packaging='Box', extras={'manual':'EN'}),
         service.UnifiedHistoryRow(row=5, customer_name='Client', product_no='ITEM', standard='US', packaging='Tray', extras={'manual':'JP'})]
    row = {'customer_name':'Client','product_no':'ITEM','packaging':'Source tray','issues':[]}
    mapping.enrich_360_requirements(row, h)
    assert row['packaging'] == 'Source tray'
    assert not row.get('standard') and not row.get('manual')
    assert {i['code'] for i in row['issues']} == {'360_standard_history_conflict','360_manual_history_conflict'}


def test_default_threesixty_name_is_not_evidence_for_a_shared_end_customer():
    row = {'product_no': 'ITEM', 'issues': []}
    mapping.map_record(row, {'customer_name': '', 'contract_no': 'RL-123-1'}, '360')
    history = [service.UnifiedHistoryRow(row=4, customer_name='ThreeSixty', product_no='ITEM',
        standard='US', packaging='Box', extras={'manual': 'English', 'barcode': '123'})]
    mapping.enrich_360_requirements(row, history)
    assert not any(row.get(field) for field in ('standard', 'packaging', 'manual', 'barcode'))


def test_requirement_history_rechecks_identity_and_keeps_manual_or_source_values():
    history = [service.UnifiedHistoryRow(row=4, customer_name='Client', product_no='OLD',
        standard='US', packaging='Box', extras={'manual': 'English', 'barcode': '123'}),
        service.UnifiedHistoryRow(row=5, customer_name='Client', product_no='NEW',
        standard='EU', packaging='Tray', extras={'manual': 'Spanish', 'barcode': '#REF!'})]
    row = {'customer_name': 'Client', 'product_no': 'OLD', 'port': 'Source port', 'issues': []}
    mapping.enrich_360_requirements(row, history)
    assert row['standard'] == 'US' and row['barcode'] == '123'
    row.update(product_no='NEW', packaging='Manual packaging')
    mapping.enrich_360_requirements(row, history, protected_fields={'packaging'})
    assert [row.get(field) for field in ('standard', 'packaging', 'manual', 'barcode', 'port')] == [
        'EU', 'Manual packaging', 'Spanish', '', 'Source port',
    ]
    assert len(row['issues']) == 2
    row['customer_name'] = 'Other'
    mapping.enrich_360_requirements(row, history, protected_fields={'packaging'})
    assert not row['standard'] and not row['manual']
    assert row['packaging'] == 'Manual packaging' and row['port'] == 'Source port'
    assert not row['issues']


def template():
    w = openpyxl.Workbook()
    w.remove(w.active)
    for name in service.SHEETS:
        s = w.create_sheet(name)
        headers = service.ITEM_HEADERS[:29] + mapping.ITEM_TAILS['360'] if name == service.ITEM_SHEET else service.ORDER_HEADERS
        for col, value in enumerate(headers, 1):
            s.cell(3, col, value)
        s.cell(4, 8 if name == service.ITEM_SHEET else 7, 'OLD')
        s.cell(4, 20 if name == service.ITEM_SHEET else 14, 'User data')
        s.cell(20, 1, '取消单')
        s.cell(22, 1, '已走货订单')
    b = BytesIO()
    w.save(b)
    return b.getvalue()


def test_actual_parse_to_three_sheet_export(monkeypatch, tmp_path):
    text = '''PURCHASE ORDER RELEASE (CINV)RL-123-1 - REVISION 0
Customer PO Number : 000123
Customer Release No. : PO#TBA (FC-51966 Palacio Mexico)
1 1423020051.36 Each 152
Toy DIY Bionic Hand Set
EAN Code : 0012345678901
IM : Spanish Safety Warning + QR : No SW + No QR
Master Carton Qty : 4
Planned Inspection Date : 8-Dec-2026 Factory Commit Date : 8-Dec-2026
Factory Address : Some factory
1. NOM Label: Only for battery-operated products, on color box, provided by customer
Factory Commit Date History:
'''
    path = tmp_path / 'po.pdf'
    path.write_bytes(b'synthetic')
    monkeypatch.setattr(schedule_parser, '_extract_pdf', lambda *_: (text, 3))
    source = template()
    output, _, p = service.export_unified_customer_schedule(customer_code='360',factory_id='huakang-a',received_date='2026-10-08',
        po_files=[('po.pdf',b'synthetic')],schedule_file_name='test.xlsx',schedule_content=source)
    row = p['rows'][0]
    assert row['customer_name'] == 'Palacio Mexico'
    assert 'Customer Release' in row['lineage']['customer_country']
    w = openpyxl.load_workbook(BytesIO(output))
    item = w[service.ITEM_SHEET]
    assert item['G5'].value == 'Palacio Mexico'
    assert item['O5'].value == row['manual']
    assert item['P5'].value == row['label'] and 'Only for battery-operated' in item['P5'].value
    assert item['AD5'].value == '0012345678901' and item['AD5'].data_type == 's'
    assert item['N5'].value is None and item['T5'].value is None
    assert item['T4'].value == 'User data'
    for name in (service.ORDER_SHEET, service.REVIEW_SHEET):
        assert [w[name].cell(5,c).value for c in range(3,8)] == [item.cell(5,c).value for c in range(4,9)]
        assert w[name]['N4'].value == 'User data'
        assert w[name]['J5'].value == '=IF(LEN(\'ITEM表\'!K5)=0,"",\'ITEM表\'!K5)'


def test_unified_generic_history_does_not_restore_other_market_requirements():
    row = {'id':'r','_huakang_customer':'360','customer_name':'Unknown','product_no':'ITEM','reference_no':'NEW',
        'quantity':'1','issues':[], 'standard':'','packaging':''}
    service._enrich_row(row, [service.UnifiedHistoryRow(row=4,customer_name='Other',product_no='ITEM',standard='US',packaging='Box')], '360')
    assert row['standard'] == row['packaging'] == ''


@pytest.mark.parametrize('instruction,expected', [
    ('No SSCC Barcode labeled on master carton', ''),
    ('Optional: SSCC labels on master carton', ''),
    ('1. SSCC labels on master carton are not required', ''),
    ('SSCC Barcode labeled on\fmaster carton', ''),
    ('SSCC Barcode labeled on master carton', 'SSCC Barcode labeled on master carton'),
    ('1. SSCC labels on shipping carton', 'SSCC labels on shipping carton'),
    ('1. SSCC labels on master cartons', 'SSCC labels on master cartons'),
    ('1. No SSCC labels on shipping cartons', ''),
    ('1. Optional: SSCC labels on master cartons', ''),
])
def test_broad_requirements_cannot_override_sscc_negation_or_page_evidence(tmp_path, instruction, expected):
    path = tmp_path / 'source.pdf'
    path.write_bytes(b'synthetic')
    text = 'PURCHASE ORDER RELEASE (CINV)RL-123-1 - REVISION 0\n'
    text += 'Customer PO Number : 000123\nCustomer Release No. : PO (Client)\n'
    text += '1 1423020051.36 Each 152\nToy\nFactory Address : Example\n'
    text += instruction + '\nFactory Commit Date History:'
    record = schedule_parser._parse_po_text(path, text, 2)
    assert record['customer_label'] == record['outer_carton_sticker'] == expected
    assert record['label'] == ''  # Outer-carton requirements never become product labels.
    row = {'source_po_file_name': 'original.pdf', 'issues': []}
    mapping.map_record(row, record, '360')
    if expected:
        assert '第1页' in row['lineage']['customer_label']
    else:
        assert not row['lineage'].get('customer_label')
    assert (row['contract_no'], row['reference_no'], row['po_no'], row['production_no'], row['order_type']) == (
        'RL-123-1', 'RL-123-1', '000123', 'PO (Client)', '正单',
    )


def test_other_carton_clause_and_sscc_keep_both_sources(tmp_path):
    path = tmp_path / 'source.pdf'
    path.write_bytes(b'synthetic')
    text = ('PURCHASE ORDER RELEASE (MSL1)RL-123-1 - REVISION 0\n'
            '1 1423020051.36 Each 152\nToy\nFactory Address : Example\n'
            '1. Importer label on master carton, provided by customer\n'
            '2. SSCC Barcode labeled on master carton\nFactory Commit Date History:')
    record = schedule_parser._parse_po_text(path, text, 1)
    assert record['customer_label'].splitlines() == [
        'Importer label on master carton, provided by customer', 'SSCC Barcode labeled on master carton',
    ]
    row = {'issues': []}
    mapping.map_record(row, record, '360')
    assert '明确外箱/内箱' in row['lineage']['customer_label']
    assert 'source.pdf · 第1页 · SSCC' in row['lineage']['customer_label']


@pytest.mark.parametrize('current, historical', [
    ('1234567890.1', '12345678901'),
    ('1234567890-A', '1234567890A'),
    ('0012345', '12345'),
])
def test_requirement_history_preserves_complete_product_identity(current, historical):
    row = {'customer_name': 'Client', 'product_no': current, 'issues': []}
    history = [service.UnifiedHistoryRow(row=4, customer_name='Client', product_no=historical,
        standard='Other standard', packaging='Other box',
        extras={'manual': 'Other manual', 'barcode': '00123', 'port': 'Other port'})]
    mapping.enrich_360_requirements(row, history)
    assert not any(row.get(field) for field in ('standard', 'packaging', 'manual', 'barcode', 'port'))


@pytest.mark.parametrize('customer, other_customer', [
    ('Client-A', 'ClientA'), ('客户甲', '客户乙'),
])
def test_requirement_history_preserves_customer_punctuation_and_unicode(customer, other_customer):
    row = {'customer_name': customer, 'product_no': '1234567890.1', 'issues': []}
    other = service.UnifiedHistoryRow(row=4, customer_name=other_customer, product_no='1234567890.1',
        standard='Other standard', extras={'manual': 'Other manual'})
    mapping.enrich_360_requirements(row, [other])
    assert not row.get('standard') and not row.get('manual')
    matching = service.UnifiedHistoryRow(row=5, customer_name=customer, product_no='1234567890.1',
        standard='Matched standard', extras={'manual': 'Matched manual'})
    mapping.enrich_360_requirements(row, [other, matching])
    assert row['standard'] == 'Matched standard' and row['manual'] == 'Matched manual'
