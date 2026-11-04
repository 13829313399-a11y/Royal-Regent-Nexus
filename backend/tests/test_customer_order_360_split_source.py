"""Manual split provenance must survive export without creating a split engine."""
from copy import copy
from io import BytesIO

import openpyxl
import pytest
from openpyxl.styles import Font
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table

from app.services import customer_order_unified as service
from app.services.customer_order_360_split_source import SHEETS, ensure_split_source_columns
from app.services.customer_order_360_order_types import ORDER_TYPES
from app.services.customer_order_360_workbook import organize_workbook
from test_customer_order_360_carton import snapshot
from test_customer_order_360_version import kwargs, parsed_row, workbook_bytes
from test_customer_order_huakang_a_unified import template


def apply(workbook, factory="huakang-a", customer="360"):
    return ensure_split_source_columns(workbook, factory_id=factory, customer_code=customer)


def test_headers_only_preserve_cells_and_repeat_without_duplicates():
    book=openpyxl.load_workbook(BytesIO(template("360")))
    for sheet in book:
        sheet["AS3"]="纸箱"
        sheet["AS3"].font=Font(name="Arial",bold=True,color="FFFFFF")
        sheet["AT4"]="用户备注"
        sheet["AU4"]="=K4*2"
    before=snapshot(book)
    report=apply(book)
    after=snapshot(book)
    for sheet in book:
        assert sheet["AV3"].value=="拆单来源"
        assert copy(sheet["AV3"].font)==copy(sheet["AS3"].font)
        assert sheet["AV3"].alignment.wrap_text and sheet.column_dimensions["AV"].width==18
        assert all(after[sheet.title][key]==value for key,value in before[sheet.title].items())
        assert not any(c.value is not None for c in sheet._cells.values() if c.column==48 and c.row!=3)
    assert apply(book)["added"]==[]
    assert set(report["added"])==set(SHEETS)
    assert "拆单" not in ORDER_TYPES


def test_existing_aliases_and_duplicate_manual_columns_are_preserved():
    book=openpyxl.load_workbook(BytesIO(template("360")))
    for sheet in book:
        sheet["AS3"],sheet["AT3"]=" 拆 單 來 源\n","拆单来源"
        sheet["AS4"],sheet["AT4"]="RL-001-1","=D4"
    before=snapshot(book)
    assert apply(book)["added"]==[]
    assert snapshot(book)==before


def test_similar_notes_are_not_a_split_source_header_and_occupied_ranges_are_skipped():
    book=openpyxl.load_workbook(BytesIO(template("360")))
    book["ITEM表"]["AS3"]="拆单来源说明"
    rule=DataValidation(type="list",formula1='"是,否"')
    rule.add("AZ4:AZ12")
    book["ITEM表"].add_data_validation(rule)
    book["接单表"].add_table(Table(displayName="OriginalTable",ref="BA3:BB4"))
    book["正单评审表"]["XFD4"].font=Font(italic=True)
    assert apply(book)["columns"]=={"ITEM表":["BA"],"接单表":["BC"],"正单评审表":["U"]}
    assert book["ITEM表"]["AS3"].value=="拆单来源说明"
    assert str(rule.sqref)=="AZ4:AZ12"


@pytest.mark.parametrize("factory,customer",[("huaxing","headstart"),("huakang-a","maxx"),("huakang-d","360"),("unknown","360")])
def test_other_factory_or_customer_is_unchanged(factory,customer):
    book=openpyxl.load_workbook(BytesIO(template("360")))
    before=snapshot(book)
    assert not apply(book,factory,customer)["applied"]
    assert snapshot(book)==before


@pytest.mark.parametrize("missing",[False,True])
def test_invalid_layout_fails_before_any_header_is_added(missing):
    book=openpyxl.load_workbook(BytesIO(template("360")))
    if missing:
        del book["正单评审表"]
    else:
        book["正单评审表"]["XFD4"]="保留"
    before=snapshot(book)
    with pytest.raises(service.CustomerOrderUnifiedError):
        apply(book)
    assert snapshot(book)==before


def test_export_and_organize_keep_manual_origin_with_its_order_without_changing_quantity(monkeypatch,tmp_path):
    row=parsed_row()
    row['order_type']='正单'
    monkeypatch.setattr(service,'_parse_huakang_a_rows',lambda *_:([row],[],'TEST'))
    output,_,_=service.export_unified_customer_schedule(**kwargs(template("360")))
    book=openpyxl.load_workbook(BytesIO(output))
    for sheet in book:
        column,=[c.column for c in sheet[3] if c.value=="拆单来源"]
        ref_column=5 if sheet.title=="ITEM表" else 4
        row=next(c.row for c in sheet._cells.values() if c.column==ref_column and c.value=="RL-765431-23")
        assert sheet.cell(row,column).value is None
        assert sheet.cell(row,2).value=="正单" or sheet.cell(row,2).data_type=="f"
        sheet.cell(row,column,"RL-765431-20")
    initial=workbook_bytes(book)
    organized,_,report,_=organize_workbook("360.xlsx",initial)
    assert report["split_source_columns"]["added"]==[]
    second,_,_,_=organize_workbook("360.xlsx",organized)
    result=openpyxl.load_workbook(BytesIO(second))
    first=openpyxl.load_workbook(BytesIO(organized))
    assert snapshot(first)==snapshot(result)
    for sheet in result:
        column,=[c.column for c in sheet[3] if c.value=="拆单来源"]
        cells=[c for c in sheet._cells.values() if c.column==column and c.value=="RL-765431-20"]
        assert len(cells)==1
        ref_column=5 if sheet.title=="ITEM表" else 4
        assert sheet.cell(cells[0].row,ref_column).value=="RL-765431-23"
    again=openpyxl.load_workbook(BytesIO(initial))
    for sheet in again:
        quantity_column=11 if sheet.title=="ITEM表" else 10
        assert sum(c.value for c in sheet._cells.values() if c.column==quantity_column and isinstance(c.value,(int,float)))==sum(
            c.value for c in result[sheet.title]._cells.values() if c.column==quantity_column and isinstance(c.value,(int,float)))
    (tmp_path/"360-split-source.xlsx").write_bytes(second)


def test_manual_split_example_keeps_origin_and_total_through_real_date_moves():
    book=openpyxl.load_workbook(BytesIO(template("360")))
    report=apply(book)
    for sheet in book:
        origin=openpyxl.utils.column_index_from_string(report['columns'][sheet.title][0])
        ref,product,qty,inspection=(5,8,11,25) if sheet.title=='ITEM表' else (4,7,10,18)
        # Old-date A and future-date B deliberately start in unfinished order.
        for row,number,quantity,day in [(4,'RL-123456-1',700,'2020-01-01'),(5,'RL-123456-2',300,'2099-01-01')]:
            sheet.cell(row,ref,number)
            sheet.cell(row,product,'76543210001')
            sheet.cell(row,qty,quantity)
            sheet.cell(row,inspection,day)
            sheet.cell(row,2,'正单')
        sheet.cell(5,origin,'RL-123456-1')
    output,_,_,_=organize_workbook('manual-split.xlsx',workbook_bytes(book))
    result=openpyxl.load_workbook(BytesIO(output))
    for sheet in result:
        origin,=[c.column for c in sheet[3] if c.value=='拆单来源']
        ref,qty=(5,11) if sheet.title=='ITEM表' else (4,10)
        rows={c.value:c.row for c in sheet._cells.values() if c.column==ref and c.value in ('RL-123456-1','RL-123456-2')}
        a,b=rows['RL-123456-1'],rows['RL-123456-2']
        assert b<a and sheet.cell(a,qty).value==700 and sheet.cell(b,qty).value==300
        assert sheet.cell(a,qty).value+sheet.cell(b,qty).value==1000
        assert sheet.cell(a,origin).value is None
        assert sheet.cell(b,origin).value=='RL-123456-1'
        assert sheet.cell(a,2).value==sheet.cell(b,2).value=='正单'
