from io import BytesIO
from decimal import Decimal
import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from app.services.carton_opening_preview import parse_rows,options_from_json

OPTIONS={"customer_name":"迪奇","warehouse":"A","snapshot_date":"2026-09-01","dimension_unit":"cm","currency":"CNY"}
HEADERS=["PO","货号","纸品／纸质","长","宽","高","仓位","期初库存数量","单价"]


def workbook(rows,headers=HEADERS):
    wb=Workbook();ws=wb.active;ws.title="期初库存导入"
    ws.append(["期初数据"]);ws.append(headers)
    for row in rows: ws.append(row)
    example=wb.create_sheet("填写示例");example.append(headers);example.append(["不会被导入"])
    stream=BytesIO();wb.save(stream);return stream.getvalue()


def test_original_columns_parse_box_card_and_zero_without_guessing_price():
    content=workbook([["PO-1","000123","A33+B外箱",30,20,15,"A1",100,2.5],
        ["PO-1","000123","B3B内箱",15,10,5,"A1",200,None],
        ["PO-1","000123","H5A平卡",30,20,0,"A1",50,.3],
        ["PO-1","000123","A33+B外箱",30,20,15,"A1",0,None]])
    rows,warnings=parse_rows("stock.xlsx",content,options_from_json(OPTIONS))
    assert len(rows)==4
    assert rows[0]["paper_quality"]=="A33+B" and rows[0]["item_no"]=="000123"
    assert rows[0]["amount"]==Decimal("250.00")
    assert rows[1]["unit_price"] is None and rows[1]["amount"] is None
    assert rows[2]["specification"]=="30 × 20 × 0 cm" and rows[2]["unit"]=="张"
    assert rows[3]["status"]=="ZERO"


@pytest.mark.parametrize("quantity",[None,-1,"NaN","Infinity","wrong"])
def test_invalid_opening_quantity_is_not_sourced_from_inbound_columns(quantity):
    with pytest.raises(HTTPException):
        parse_rows("stock.xlsx",workbook([["PO","ITEM","A33外箱",30,20,15,"A1",quantity,2,999]],HEADERS+["入库箱"]),options_from_json(OPTIONS))


def test_original_amount_is_ignored_but_opening_amount_is_checked():
    rows,_=parse_rows("stock.xlsx",workbook([["PO","ITEM","A33外箱",30,20,15,"A1",10,2,999,"8月1日"]],HEADERS+["入库金额","日期"]),options_from_json(OPTIONS))
    assert rows[0]["amount"]==20 and rows[0]["snapshot_date"]=="2026-09-01"
    assert any("原入库" in warning for warning in rows[0]["warnings"])
    with pytest.raises(HTTPException) as exc:
        parse_rows("stock.xlsx",workbook([["PO","ITEM","A33外箱",30,20,15,"A1",10,2,999]],HEADERS+["原结余金额"]),options_from_json(OPTIONS))
    assert "不一致" in exc.value.detail


def test_eight_column_original_quality_header_is_supported_and_units_required():
    headers=HEADERS[:8];headers[2]="纸质"
    rows,_=parse_rows("stock.xlsx",workbook([["PO","ITEM","A33+B外箱",30,20,15,"A1",10]],headers),options_from_json(OPTIONS))
    assert rows[0]["unit_price"] is None and rows[0]["paper_quality"]=="A33+B"
    with pytest.raises(HTTPException): options_from_json({key:value for key,value in OPTIONS.items() if key!="dimension_unit"})
    with pytest.raises(HTTPException): options_from_json({**OPTIONS,"snapshot_date":"9月1日"})


@pytest.mark.parametrize("field,value",[("客户名称","其他客户"),("仓库","B"),("尺寸单位","in"),("币种","USD"),("盘点日期","2026-08-01")])
def test_batch_settings_cannot_silently_override_explicit_row_fields(field,value):
    with pytest.raises(HTTPException) as exc:
        parse_rows("stock.xlsx",workbook([["PO","I","A33外箱",30,20,15,"A1",10,2,value]],HEADERS+[field]),options_from_json(OPTIONS))
    assert "不一致" in exc.value.detail


def test_published_template_empty_inputs_ignore_examples_and_example_rows_parse():
    from pathlib import Path
    from openpyxl import load_workbook
    template=Path(__file__).resolve().parents[2]/"public/templates/carton-history-inventory-import-template.xlsx"
    with pytest.raises(HTTPException) as exc:
        parse_rows(template.name,template.read_bytes(),options_from_json(OPTIONS))
    assert "未找到可导入数据" in exc.value.detail
    wb=load_workbook(template)
    for target_row,source_row in enumerate(range(6,10),3):
        for col,cell in enumerate(wb["填写示例"][source_row],1):
            wb["期初库存导入"].cell(target_row,col,cell.value)
    stream=BytesIO();wb.save(stream)
    rows,_=parse_rows(template.name,stream.getvalue(),options_from_json(OPTIONS))
    assert len(rows)==4 and sum(row["status"]=="ZERO" for row in rows)==1
    assert sum(row["unit_price"] is None for row in rows if row["status"]!="ZERO")==1
    assert [(row["packaging_type"],row["opening_quantity"]) for row in rows[:3]]==[("外箱",100),("内箱",200),("平卡",50)]
