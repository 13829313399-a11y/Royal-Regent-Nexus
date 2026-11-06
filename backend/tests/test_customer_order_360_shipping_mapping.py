from copy import deepcopy
from io import BytesIO
import os
from pathlib import Path

import openpyxl
import pytest

from app.services import customer_order_unified as unified
from app.services.customer_order_360_shipping_item import prepare_shipping_item,backfill_shipping_items,ShippingItemError
from app.services.customer_order_360_shipping_mapping import (SHEET,HEADERS,ShippingMappingError,
    read_mapping,read_mapping_from_content,reference_records,records_as_history,embed_reference_mapping)
from test_customer_order_360_shipping_item import _history,_workbook,_row
from test_customer_order_360_version import kwargs,parsed_row,workbook_bytes
from test_customer_order_huakang_a_unified import template


def record(ref='RL-123456-1',product='76543220069',shipping='7654999'):
    return dict(reference=ref,product=product,shipping=shipping,file='source.xlsx',sheet='360客排期表',row=8,note='原排期')


def test_explicit_map_overrides_format_rule_but_not_same_order_manual_history():
    row=_row(product='76543220069',reference='RL-123456-1')
    records=records_as_history([record(shipping='7654999、7654888')])
    prepare_shipping_item(row,[],records)
    assert row['shipping_item']=='7654999、7654888'
    assert '映射表' in row['lineage']['shipping_item']
    prepare_shipping_item(row,[_history(row['product_no'],'手工货号',row['reference_no'])],records)
    assert row['shipping_item']=='手工货号'


def test_conflicting_map_values_never_fall_back_to_an_arbitrary_first_or_rule():
    row=_row(product='76543220069',reference='RL-123456-1')
    mapping=records_as_history([record(shipping='A'),record(shipping='B')])
    prepare_shipping_item(row,[],mapping)
    assert row['shipping_item']=='' and '不一致' in row['lineage']['shipping_item']
    prepare_shipping_item(row,[],records_as_history([record(ref='RL-123456-2',shipping='A')]))
    assert row['shipping_item']=='A'  # Unique complete-product evidence only.
    prepare_shipping_item(row,[],records_as_history([record(product='7654322',shipping='OTHER')]))
    assert row['shipping_item']=='7654322'  # Prefix is never a product-key match.


def test_map_is_display_only_and_never_becomes_a_business_order(monkeypatch):
    book=openpyxl.load_workbook(BytesIO(template('360')))
    row=parsed_row();row.update(product_no='76543220069',reference_no='RL-123456-1',contract_no='RL-123456-1')
    embed_reference_mapping(book,[record()])
    source=workbook_bytes(book)
    history=unified.read_unified_history(source,factory_id='huakang-a',customer_code='360')
    assert not any(h.reference_no=='RL-123456-1' for h in history)
    monkeypatch.setattr(unified,'_parse_huakang_a_rows',lambda *_:([deepcopy(row)],[],'TEST'))
    preview=unified.create_unified_customer_preview(**kwargs(source))
    assert preview['rows'][0]['shipping_item']=='7654999'
    assert not any('duplicate' in i['code'] for i in preview['rows'][0]['issues'])
    output,_,_=unified.export_unified_customer_schedule(**kwargs(source))
    restored=openpyxl.load_workbook(BytesIO(output))
    assert restored.sheetnames[-1]==SHEET
    assert read_mapping(restored)[0]['extras']['shipping_item']=='7654999'


def test_organizer_preserves_map_and_uses_same_order_before_other_order_values():
    book=_workbook()
    # Product history has a different order; explicit map matches the current one.
    mapping=records_as_history([record(ref='RL-100-4',product='00123456789',shipping='特别出货号')])
    backfill_shipping_items(book,shipping_map=mapping)
    assert book['ITEM表']['AM4'].value=='特别出货号'


def test_mapping_schema_and_formulas_fail_before_shipping_headers_or_values_change():
    book=_workbook();sheet=book.create_sheet(SHEET);sheet.append(HEADERS)
    sheet.append(['RL-100-4','00123456789','=1+2'])
    with pytest.raises(ShippingItemError,match='含公式'):
        backfill_shipping_items(book)
    assert book['ITEM表']['AM3'].value is None
    sheet['C2'].data_type='s'
    assert read_mapping(book)[0]['extras']['shipping_item']=='=1+2'
    sheet['A1']='错误表头'
    with pytest.raises(ShippingMappingError,match='表头'):
        read_mapping(book)


def test_embedding_keeps_text_and_only_aliases_observed_numeric_display_zeroes():
    book=_workbook();item=book['ITEM表']
    item['E5'],item['H5']='RL-123456-1','8765432109.30'
    before=(item['E5'].value,item['H5'].value)
    report=embed_reference_mapping(book,[record(product='8765432109.3',shipping='0012345')])
    assert report['aliases']==1
    values=read_mapping(book)
    assert {r['product_no'] for r in values}=={'8765432109.3','8765432109.30'}
    assert {r['extras']['shipping_item'] for r in values}=={'0012345'}
    assert before==(item['E5'].value,item['H5'].value)
    with pytest.raises(ShippingMappingError,match='不能未经核对覆盖'):
        embed_reference_mapping(book,[record()])


def test_alias_uses_the_same_literal_po_fallback_as_shipping_backfill():
    book=_workbook();item=book['ITEM表']
    item['E5'],item['D5'],item['F5'],item['H5']=None,'CONTRACT-OTHER','RL-123456-1','8765432109.30'
    report=embed_reference_mapping(book,[record(product='8765432109.3',shipping='SPECIAL-ORIGINAL')])
    assert report['aliases']==1
    backfill_shipping_items(book)
    assert item['AM5'].value=='SPECIAL-ORIGINAL'
    assert item['H5'].value=='8765432109.30'


@pytest.mark.parametrize('column',['E','F','G'])
def test_reference_excel_error_cells_are_not_accepted_as_mapping_evidence(column):
    book=openpyxl.Workbook();s=book.active;s.title='360客排期表'
    s['E3'],s['F3'],s['G3']='正单合同号','产品货号','出货货号'
    s['E4'],s['F4'],s['G4']='RL-123456-1','76543220069','7654999'
    s[f'{column}4']='#REF!'
    with pytest.raises(ShippingMappingError,match='Excel错误'):
        reference_records(workbook_bytes(book),'source.xlsx')


@pytest.mark.parametrize('column',['A','B','C'])
def test_embedded_mapping_errors_are_rejected_instead_of_used_as_shipping_codes(column):
    book=_workbook();s=book.create_sheet(SHEET);s.append(HEADERS)
    s.append(['RL-100-4','00123456789','0012345']);s[f'{column}2']='#N/A'
    with pytest.raises(ShippingMappingError,match='Excel错误'):
        read_mapping(book)


def test_partial_mapping_does_not_silently_fall_back_to_a_guessed_shipping_code():
    book=_workbook();s=book.create_sheet(SHEET);s.append(HEADERS)
    s.append(['RL-100-4','00123456789',None])
    with pytest.raises(ShippingMappingError,match='缺少'):
        read_mapping(book)


def test_reference_parser_uses_confirmed_headers_and_rejects_wrong_or_truncated_ranges():
    book=openpyxl.Workbook();s=book.active;s.title='360客排期表'
    s['E3'],s['F3'],s['G3']='正单合同号','产品货号','出货货号'
    s['E4'],s['F4'],s['G4']='RL-123456-1','76543220069','7654999'
    result=reference_records(workbook_bytes(book),'source.xlsx')
    assert result[0]['shipping']=='7654999'
    book=openpyxl.Workbook();s=book.active;s.title='360客排期表'
    s['F3'],s['G3']='产品货号','出货货号';s['A10005']='不得截断的后续内容'
    with pytest.raises(ShippingMappingError,match='未截断'):
        reference_records(workbook_bytes(book),'source.xlsx')


def test_private_supplied_current_pair_preserves_all_current_full_ids():
    current,reference=os.getenv('CUSTOMER_ORDER_360_CURRENT_UNIFIED'),os.getenv('CUSTOMER_ORDER_360_REFERENCE')
    if not current or not reference:
        pytest.skip('Set private current/reference files outside Git')
    raw=Path(current).read_bytes();ref=Path(reference).read_bytes()
    book=openpyxl.load_workbook(BytesIO(raw))
    originals={(s.title,c.coordinate):(c.value,c.data_type) for s in book for c in s._cells.values() if c.value is not None}
    records=reference_records(ref,Path(reference).name)
    embed_reference_mapping(book,records)
    result=backfill_shipping_items(book)
    assert result['filled']==69 and not result['unresolved']
    assert all((book[s][cell].value,book[s][cell].data_type)==expected for (s,cell),expected in originals.items())
    assert Path(current).read_bytes()==raw and Path(reference).read_bytes()==ref
