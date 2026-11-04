from copy import deepcopy
from io import BytesIO

import openpyxl
import pytest

from app.services import customer_order_unified as service
from app.services.customer_order_360_carton import ensure_carton_columns
from app.services.customer_order_360_split_source import ensure_split_source_columns
from app.services.customer_order_huaxing_unified import BUZZBEE_SHEETS
from test_customer_order_huaxing_unified import template,data
from test_customer_order_360_carton import snapshot
from test_customer_order_unified import _parsed_row,_template_bytes


def apply(book, factory='huaxing', customer='buzzbee'):
    return ensure_split_source_columns(book,factory_id=factory,customer_code=customer)


def test_all_four_buzzbee_categories_and_both_summaries_get_one_manual_origin():
    book=template()
    for sheet in book:
        sheet['AR3']='人工备注'
        sheet['AR4']='用户内容'
        sheet['AS4']='=1+2'
    before=snapshot(book)
    report=apply(book)
    assert set(report['added'])==set((*BUZZBEE_SHEETS,'接单表','正单评审表'))
    for sheet in book:
        assert sheet['AT3'].value=='拆单来源'
        assert sheet['AT3'].alignment.wrap_text
        assert all(snapshot(book)[sheet.title][k]==v for k,v in before[sheet.title].items())
        assert sheet['AT4'].value is None
    assert apply(book)['added']==[]
    assert ensure_carton_columns(book,factory_id='huaxing',customer_code='buzzbee')['applied']


def test_existing_origin_and_plain_three_sheet_buzzbee_template_are_supported():
    book=openpyxl.load_workbook(BytesIO(_template_bytes()))
    for sheet in book:
        sheet['AR3']=' 拆 單 來 源 '
        sheet['AR7']='SC-ORIGINAL'
    before=snapshot(book)
    assert apply(book)['added']==[]
    assert snapshot(book)==before


def test_buzzbee_partial_categories_fail_without_partial_header_mutation():
    book=template()
    del book[BUZZBEE_SHEETS[-1]]
    before=snapshot(book)
    with pytest.raises(service.CustomerOrderUnifiedError,match='缺少'):
        apply(book)
    assert snapshot(book)==before


@pytest.mark.parametrize('factory,customer',[('huakang-a','buzzbee'),('huakang-d','buzzbee'),('huaxing','headstart'),('huakang-a','dickie')])
def test_other_scope_is_not_changed(factory,customer):
    book=template()
    before=snapshot(book)
    assert not apply(book,factory,customer)['applied']
    assert snapshot(book)==before


def test_actual_unified_buzzbee_export_keeps_origin_with_original_order(monkeypatch):
    book=template()
    lane=BUZZBEE_SHEETS[0]
    for sheet in book:
        sheet['AR3']='拆单来源'
        sheet['AR4']='SC-OLD'
    book[lane]['E4'],book[lane]['H4'],book[lane]['K4']='SC-CHILD','ITEM-1',700
    row=_parsed_row()
    row.update(product_no='ITEM-1',reference_no='SC-NEW',contract_no='SC-NEW',customer_name='WMC',
               _huaxing_customer='buzzbee',order_type='正单')
    monkeypatch.setattr(service,'_create_customer_rows',lambda *_:([deepcopy(row)],[],'TEST'))
    output,_,_=service.export_unified_customer_schedule(factory_id='huaxing',customer_code='buzzbee',
        received_date='2026-10-28',po_files=[('PO.xlsx',b'synthetic')],schedule_file_name='BuzzBee.xlsx',schedule_content=data(book))
    result=openpyxl.load_workbook(BytesIO(output))
    assert result[lane]['AR4'].value=='SC-OLD'
    assert result[lane]['K4'].value==700
    assert result[lane]['E4'].value=='SC-CHILD'
    new=next(c.row for c in result[lane]._cells.values() if c.column==5 and c.value=='SC-NEW')
    assert result[lane].cell(new,44).value is None
    assert result[lane].cell(new,2).value=='正式PO'
    for sheet in result:
        assert sum(c.row==3 and c.value=='拆单来源' for c in sheet._cells.values())==1
