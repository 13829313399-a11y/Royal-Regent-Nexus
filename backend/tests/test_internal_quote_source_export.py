import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.services.internal_quote_excel import (
    _append_spreadsheet_attachment_sheets, _build_mold_quote_sheet,
    _rewrite_attachment_formula,
)
from app.services.internal_quote_workbook_view import WorkbookValues
from test_internal_quote_excel_formula_links import _section


def attachment(content, name):
    return SimpleNamespace(file_name=name, content=content, sha256=hashlib.sha256(content).hexdigest())


@pytest.mark.parametrize("enabled", [False, True])
def test_whole_mold_prices_remain_visible_without_multiplying_sets_or_allocating(enabled):
    book = Workbook()
    section = _section("engineering", payload={
        "mold_allocation_enabled": enabled,
        "molds": [{"mold_no": "M1", "item": "高尔夫车", "quantity": 3, "cost_rmb": 12000,
                   "parts": [{"item": "车身"}, {"item": "车轮"}]},
                  {"mold_no": "M2", "item": "底板", "quantity": 2, "cost_rmb": 3000}],
        "production_mold_costs": [{"item": "模具费用", "cost_rmb": 15000}],
    })
    _build_mold_quote_sheet(book, section)
    sheet = book["工模报价"]
    assert sheet.sheet_state == "visible"
    assert sheet["B2"].value == ("已启用" if enabled else "未启用")
    assert sheet["E5"].value == 3
    assert sheet["F5"].value == 12000
    assert WorkbookValues(book).cell(sheet.title, "F7") == 15000
    assert WorkbookValues(book).cell(sheet.title, "C11") == 15000
    book.close()


def test_sources_keep_sheets_styles_links_and_duplicate_names_without_replacing_quote():
    source = Workbook()
    source.active.title = "报价明细"
    source.active["A1"] = "来源"
    source.active["A1"].font = Font(bold=True, color="FF0000")
    source.active.merge_cells("A1:B1")
    source.active.print_area = "A1:D10"
    source.active.print_title_rows = "1:2"
    source.create_sheet("参数")["A1"] = "='报价明细'!A1"
    source["参数"]["A2"] = '=报价明细!A1&"报价明细!A1"'
    source["参数"]["A3"] = "=报价明细!A1"
    source["参数"]["A3"].data_type = "s"
    buffer = BytesIO()
    source.save(buffer)
    source.close()
    item = attachment(buffer.getvalue(), "工模.xlsx")
    book = Workbook()
    book.active.title = "报价明细"
    book.active["A1"] = "系统报价"
    titles = _append_spreadsheet_attachment_sheets(book, [item, item])
    assert titles == ["工模-报价明细", "工模-参数"]
    assert book["报价明细"]["A1"].value == "系统报价"
    assert book[titles[0]]["A1"].font.bold
    assert "A1:B1" in book[titles[0]].merged_cells
    assert book[titles[0]].print_title_rows == "$1:$2"
    assert book[titles[1]]["A1"].value == "='工模-报价明细'!A1"
    assert book[titles[1]]["A2"].value == '=\'工模-报价明细\'!A1&"报价明细!A1"'
    result = BytesIO()
    book.save(result)
    reopened = load_workbook(BytesIO(result.getvalue()))
    assert reopened[titles[1]]["A3"].data_type == "s"
    assert reopened[titles[1]]["A3"].value == "=报价明细!A1"
    assert all(reopened[title].sheet_state == "visible" for title in titles)
    reopened.close()
    book.close()


def test_formula_sheet_renaming_is_simultaneous_and_preserves_strings():
    assert _rewrite_attachment_formula('=A!B1+AA!B1+\'B\'!B1&"A!B1"', {"A": "B", "AA": "C", "B": "D"}) == '=\'B\'!B1+\'C\'!B1+\'D\'!B1&"A!B1"'


def test_legacy_hair_workbook_is_included_with_saved_values():
    import xlrd
    content = (Path(__file__).resolve().parents[1] / "app/data/internal_quote_import_templates/车发部报价单.xls").read_bytes()
    original = xlrd.open_workbook(file_contents=content)
    book = Workbook()
    titles = _append_spreadsheet_attachment_sheets(book, [attachment(content, "车发.xls")])
    assert len(titles) == original.nsheets
    for sheet, title in zip(original.sheets(), titles):
        assert book[title].sheet_state == "visible"
        for row in range(sheet.nrows):
            for col in range(sheet.ncols):
                if sheet.cell_type(row, col) in (xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_TEXT):
                    assert book[title].cell(row + 1, col + 1).value == sheet.cell_value(row, col)
    output = BytesIO()
    book.save(output)
    book.close()
    original.release_resources()


def test_invalid_source_leaves_visible_failure_note_instead_of_disappearing():
    book = Workbook()
    titles = _append_spreadsheet_attachment_sheets(book, [attachment(b"invalid", "broken.xls")])
    assert titles == ["broken-附件异常"]
    assert book[titles[0]]["A1"].value == "上传表格未能嵌入"
    book.close()


@pytest.mark.parametrize("grouped", [False, True])
def test_final_electronic_quick_price_only_converts_fx_in_calculation_and_export(grouped):
    from app.services.internal_quote_calculator import calculate_section
    from app.services.internal_quote_excel import _build_electronic_sheet
    snapshot = {"fx": {"rmb_hkd": ".85"}}
    quick = {"id": "q1", "name": "电子报价1", "quote_mode": "quick",
             "quick_quotes": [{"item": "电子", "unit_price_rmb": .4, "tax_rate_percent": 13}],
             "profit_rate_percent": 10, "bonding_rmb": 200, "labor_hkd": 100,
             "components": [{"item": "保留明细", "quantity": 2, "unit_price_rmb": 999}]}
    payload = {"quote_groups": [quick]} if grouped else quick
    calculation = calculate_section("electronic", payload, snapshot, "final-quick")
    assert calculation["totals"]["total_hkd"] == "0.4706"
    assert calculation["totals"]["total_rmb"] == "0.4000"
    assert calculation["totals"]["tax_payable_rmb"] == "0.0000"
    assert calculation["totals"]["extras_rmb"] == "0.0000"
    book = Workbook()
    _build_electronic_sheet(book, _section("electronic", payload=payload, calculation=calculation), snapshot)
    sheet = book["电子明细1" if grouped else "电子明细"]
    total = next(row for row in sheet.values if row[0] == "最终报价")
    assert total[1:3] == (.4, .4706)
    assert not any(row[0] == "含利润价" for row in sheet.values)
    book.close()


def test_series_keeps_visible_source_and_mold_sheets_but_hides_technical_data():
    from app.services.internal_quote_series_export import combine_series_workbooks
    book = Workbook()
    book.active.title = "报价明细"
    book.create_sheet("工模报价")["A1"] = 12000
    book.create_sheet("工模原表")["A1"] = 12000
    book.create_sheet("结构化数据").sheet_state = "veryHidden"
    output = BytesIO()
    book.save(output)
    book.close()
    merged = load_workbook(BytesIO(combine_series_workbooks([("高尔夫车", output.getvalue())])))
    assert merged["1-工模报价"].sheet_state == "visible"
    assert merged["1-工模原表"].sheet_state == "visible"
    assert merged["1-结构化数据"].sheet_state == "veryHidden"
    merged.close()
