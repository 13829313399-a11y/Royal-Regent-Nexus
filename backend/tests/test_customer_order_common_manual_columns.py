from io import BytesIO
from copy import deepcopy
import openpyxl
import pytest
from app.services import customer_order_unified as service
from app.services.customer_order_360_carton import ensure_carton_columns
from app.services.customer_order_360_split_source import ensure_split_source_columns
from test_customer_order_unified import _template_bytes, _parsed_row
from test_customer_order_360_carton import snapshot
from test_customer_order_huaxing_unified import template as buzzbee_template
from app.services.customer_order_huaxing_unified import DICKIE_EXTRA

SCOPES=[('huaxing',c) for c in ('buzzbee','dickie','caixing','edu','360','yinhui','seasons','maxx','shushupapa','barter','disney','zuru')]+[
    ('huadeng',c) for c in ('casdon','jakks','simba','spin','goliath')]+[
    ('huakang-a',c) for c in ('360','green-toys','headstart')]+[
    ('huakang-d',c) for c in ('index','jazwares','maxx','strottman','disney','seasons','ubtech')]

@pytest.mark.parametrize('factory,customer',SCOPES)
def test_all_registered_unified_scopes_preserve_data_and_reuse_headers(factory,customer):
    book=openpyxl.load_workbook(BytesIO(_template_bytes()))
    if customer=='buzzbee': book=buzzbee_template()
    if customer=='dickie':
        other=book.copy_worksheet(book['ITEM表']);other.title=DICKIE_EXTRA
    auxiliary=book.create_sheet('辅助计算');auxiliary['A1']='不改'
    before=snapshot(book)
    for fn,label in [(ensure_carton_columns,'纸箱'),(ensure_split_source_columns,'拆单来源')]:
        first=fn(book,factory_id=factory,customer_code=customer)
        assert set(first['added'])==set(book.sheetnames)-{'辅助计算'}
        assert fn(book,factory_id=factory,customer_code=customer)['added']==[]
        for sheet in book:
            if sheet.title=='辅助计算': continue
            assert sum(c.row==3 and c.value==label for c in sheet._cells.values())==1
    after=snapshot(book)
    for name,cells in before.items():
        assert all(after[name][coord]==value for coord,value in cells.items())
    assert not any(c.value=='出货货号' for s in book for c in s._cells.values())

@pytest.mark.parametrize('factory,customer',[('huaxing','seasons'),('huadeng','casdon'),('huakang-a','headstart'),('huakang-d','maxx')])
def test_shared_export_path_appends_two_manual_fields_only(monkeypatch,factory,customer):
    row=_parsed_row();row.update(order_type='正单')
    monkeypatch.setattr(service,'_create_customer_rows',lambda *_:([deepcopy(row)],[],'TEST'))
    output,_,_=service.export_unified_customer_schedule(customer_code=customer,factory_id=factory,
        received_date='2026-10-29',po_files=[('PO.xlsx',b'test')],schedule_file_name='unified.xlsx',schedule_content=_template_bytes())
    book=openpyxl.load_workbook(BytesIO(output))
    for sheet in book:
        for label in ('纸箱','拆单来源'):
            assert sum(c.row==3 and c.value==label for c in sheet._cells.values())==1
        assert not any(c.value=='出货货号' for c in sheet._cells.values())


@pytest.mark.parametrize('factory,customer',[('huaxing','seasons'),('huadeng','casdon'),('huakang-a','headstart'),('huakang-d','maxx')])
def test_new_orders_do_not_inherit_previous_manual_status_or_split_formulas(monkeypatch,factory,customer):
    book=openpyxl.load_workbook(BytesIO(_template_bytes()))
    for sheet in book:
        sheet['AR3']='拆单来源'
        sheet['AS3']='纸箱'
        for number in (4,6,11):
            sheet.cell(number,44,'="SO-OLD"')
            sheet.cell(number,45,'="已下单"')
    source=BytesIO();book.save(source)
    rows=[dict(_parsed_row(index),order_type='正单') for index in range(1,7)]
    monkeypatch.setattr(service,'_create_customer_rows',lambda *_:(deepcopy(rows),[],'TEST'))
    output,_,_=service.export_unified_customer_schedule(customer_code=customer,factory_id=factory,
        received_date='2026-11-04',po_files=[('PO.xlsx',b'test')],schedule_file_name='unified.xlsx',schedule_content=source.getvalue())
    result=openpyxl.load_workbook(BytesIO(output))
    for sheet in result:
        assert sheet['AR4'].value=='="SO-OLD"' and sheet['AS4'].value=='="已下单"'
        reference=5 if sheet.title=='ITEM表' else 4
        new_rows=[c.row for c in sheet._cells.values() if c.column==reference and c.value in {f'SO-{i}' for i in range(1,7)}]
        assert len(new_rows)==6
        # Original reserved formulas are owned by the uploaded template. Rows
        # newly inserted or filled from another order may not inherit them.
        if customer=='casdon':
            # Casdon inserts every new product row, moving the original reserved
            # row 11 down by six; a new row at 11 must not inherit its values.
            assert sheet.cell(17,44).value=='="SO-OLD"'
            assert sheet.cell(17,45).value=='="已下单"'
        for number in new_rows:
            if number==11 and customer!='casdon':
                assert sheet.cell(number,44).value=='="SO-OLD"'
            else:
                assert sheet.cell(number,44).value is None
                assert sheet.cell(number,45).value is None
